import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Body, Depends, Request, Response, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, get_owned_trip
from app.clients import AppClients
from app.db import get_session
from app.errors import GeminiError
from app.models import Trip, User
from app.plan_jobs import (
    enqueue_plan_generation,
    latest_plan_generation,
)
from app.planner import latest_itinerary
from app.schemas import (
    ChatRequest,
    ItineraryResponse,
    PlanGenerationResponse,
    TripCreate,
    TripResponse,
    TripListItemResponse,
    TripUpdate,
)
from app.trips import (
    append_assistant_message,
    append_user_message,
    build_chat_context,
    create_trip,
    delete_trip,
    list_trips,
    rename_trip,
)


router = APIRouter(prefix="/api/trips", tags=["trips"])


def _stream_event(event_type: str, **payload: object) -> bytes:
    event = {"type": event_type, **payload}
    line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    return f"{line}\n".encode("utf-8")


@router.post("", response_model=TripResponse, status_code=status.HTTP_201_CREATED)
async def create(
    request: TripCreate = Body(default_factory=TripCreate),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TripResponse:
    trip = await create_trip(session, current_user=current_user, title=request.title)
    return _trip_response(trip)


@router.get("", response_model=list[TripListItemResponse])
async def index(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[Trip]:
    return await list_trips(session, current_user=current_user)


@router.get("/{trip_id}", response_model=TripResponse)
async def show(
    trip_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TripResponse:
    trip = await get_owned_trip(session, trip_id=trip_id, current_user=current_user)
    itinerary = await latest_itinerary(session, trip.id)
    generation = await latest_plan_generation(session, trip.id)
    return _trip_response(
        trip,
        itinerary=itinerary,
        generation=generation,
    )


@router.patch("/{trip_id}", response_model=TripResponse)
async def update(
    trip_id: str,
    request: TripUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TripResponse:
    trip = await rename_trip(
        session,
        trip_id=trip_id,
        current_user=current_user,
        title=request.title,
    )
    itinerary = await latest_itinerary(session, trip.id)
    generation = await latest_plan_generation(session, trip.id)
    return _trip_response(
        trip,
        itinerary=itinerary,
        generation=generation,
    )


@router.delete("/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
async def destroy(
    trip_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    await delete_trip(session, trip_id=trip_id, current_user=current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{trip_id}/chat")
async def chat(
    trip_id: str,
    chat_request: ChatRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    trip, _user_message = await append_user_message(
        session,
        trip_id=trip_id,
        current_user=current_user,
        content=chat_request.content,
    )
    clients: AppClients = request.app.state.clients
    gemini_stream = clients.gemini.stream_text(build_chat_context(trip))
    try:
        first_chunk = await anext(gemini_stream)
    except BaseException:
        await gemini_stream.aclose()
        raise

    async def response_body() -> AsyncGenerator[bytes, None]:
        assistant_parts = [first_chunk]
        try:
            yield _stream_event("chunk", content=first_chunk)
            async for chunk in gemini_stream:
                assistant_parts.append(chunk)
                yield _stream_event("chunk", content=chunk)

            updated_trip, assistant_message = await append_assistant_message(
                session,
                trip=trip,
                content="".join(assistant_parts),
            )
            yield _stream_event(
                "done",
                message=assistant_message.model_dump(mode="json"),
                trip_updated_at=updated_trip.updated_at.isoformat(),
            )
        except GeminiError as error:
            yield _stream_event("error", detail=error.detail())
        finally:
            await gemini_stream.aclose()

    return StreamingResponse(
        response_body(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post(
    "/{trip_id}/plan",
    response_model=PlanGenerationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def plan(
    trip_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> PlanGenerationResponse:
    trip = await get_owned_trip(
        session,
        trip_id=trip_id,
        current_user=current_user,
    )
    generation = await enqueue_plan_generation(session, trip=trip)
    request.app.state.plan_generations.notify()
    return PlanGenerationResponse.model_validate(generation)


def _trip_response(
    trip: Trip,
    *,
    itinerary: object | None = None,
    generation: object | None = None,
) -> TripResponse:
    response = TripResponse.model_validate(trip)
    updates: dict[str, object] = {}
    if itinerary is not None:
        updates["latest_itinerary"] = ItineraryResponse.model_validate(itinerary)
    if generation is not None:
        updates["plan_generation"] = PlanGenerationResponse.model_validate(
            generation
        )
    return response.model_copy(update=updates)

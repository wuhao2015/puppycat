from fastapi import APIRouter, Body, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user, get_owned_trip
from app.db import get_session
from app.models import Trip, User
from app.schemas import (
    ChatDevelopmentResponse,
    ChatRequest,
    TripCreate,
    TripResponse,
    TripListItemResponse,
    TripUpdate,
)
from app.trips import (
    append_user_message,
    create_trip,
    delete_trip,
    list_trips,
    rename_trip,
)


router = APIRouter(prefix="/api/trips", tags=["trips"])


@router.post("", response_model=TripResponse, status_code=status.HTTP_201_CREATED)
async def create(
    request: TripCreate = Body(default_factory=TripCreate),
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Trip:
    return await create_trip(session, current_user=current_user, title=request.title)


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
) -> Trip:
    return await get_owned_trip(session, trip_id=trip_id, current_user=current_user)


@router.patch("/{trip_id}", response_model=TripResponse)
async def update(
    trip_id: str,
    request: TripUpdate,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Trip:
    return await rename_trip(
        session,
        trip_id=trip_id,
        current_user=current_user,
        title=request.title,
    )


@router.delete("/{trip_id}", status_code=status.HTTP_204_NO_CONTENT)
async def destroy(
    trip_id: str,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> Response:
    await delete_trip(session, trip_id=trip_id, current_user=current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{trip_id}/chat",
    response_model=ChatDevelopmentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def chat(
    trip_id: str,
    request: ChatRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ChatDevelopmentResponse:
    trip, message = await append_user_message(
        session,
        trip_id=trip_id,
        current_user=current_user,
        content=request.content,
    )
    return ChatDevelopmentResponse(message=message, trip_updated_at=trip.updated_at)

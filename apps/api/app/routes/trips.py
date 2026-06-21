from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import SessionLocal, get_session
from app.deps import Deps, UnauthorizedError, get_current_user, get_deps
from app.errors import PuppycatError
from app.llm import ModelTier
from app.models import Itinerary as ItineraryModel
from app.models import Trip, User
from app.pipeline import extract_trip_request, generate_itinerary, revise_itinerary
from app.pipeline.visa import build_visa_notice
from app.routes.chat import _SYSTEM, _build_context
from app.schemas import (
    ChatMessageOut,
    ChatTurnRequest,
    Itinerary,
    ItineraryResponse,
    SummaryDay,
    SummaryItinerary,
    TripDetail,
    TripRenameRequest,
    TripSummary,
    TripVisaNotices,
)

router = APIRouter(prefix="/api/trips", tags=["trips"])


class NotFoundError(PuppycatError):
    status_code = 404


class BadRequestError(PuppycatError):
    status_code = 400


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _owned_trip(trip_id: str, user: User, session: AsyncSession) -> Trip:
    trip = await session.get(Trip, trip_id)
    if trip is None or trip.user_id != user.id:
        # Don't reveal existence of other users' trips.
        raise NotFoundError("Trip not found.")
    return trip


async def _latest_itinerary(trip_id: str, session: AsyncSession) -> ItineraryModel | None:
    return await session.scalar(
        select(ItineraryModel)
        .where(ItineraryModel.trip_id == trip_id)
        .order_by(ItineraryModel.created_at.desc())
        .limit(1)
    )


def _append_message(trip: Trip, role: str, content: str) -> None:
    # Reassign (not mutate) so SQLAlchemy detects the JSONB change.
    trip.messages = [*(trip.messages or []), {"role": role, "content": content, "ts": _now_iso()}]


def _derive_title(trip: Trip) -> str | None:
    if trip.destination:
        return f"Trip to {trip.destination}"
    for m in trip.messages or []:
        if m.get("role") == "user" and (m.get("content") or "").strip():
            snippet = m["content"].strip().replace("\n", " ")
            return snippet[:48] + ("..." if len(snippet) > 48 else "")
    return None


def _to_summary(trip: Trip, itinerary_id: str | None) -> TripSummary:
    return TripSummary(
        trip_id=trip.id,
        title=trip.title or _derive_title(trip),
        destination=trip.destination,
        start_date=trip.start_date,
        end_date=trip.end_date,
        created_at=trip.created_at.isoformat(),
        updated_at=trip.updated_at.isoformat() if trip.updated_at else None,
        itinerary_id=itinerary_id,
    )


# --- Session CRUD -----------------------------------------------------------


@router.post("", response_model=TripDetail)
async def create_trip(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TripDetail:
    trip = Trip(user_id=user.id, title=None, messages=[], params={})
    session.add(trip)
    await session.commit()
    await session.refresh(trip)
    return TripDetail(
        trip_id=trip.id,
        title=trip.title,
        destination=trip.destination,
        start_date=trip.start_date,
        end_date=trip.end_date,
        created_at=trip.created_at.isoformat(),
        updated_at=trip.updated_at.isoformat() if trip.updated_at else None,
        messages=[],
        itinerary_id=None,
        itinerary=None,
    )


@router.get("", response_model=list[TripSummary])
async def list_trips(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[TripSummary]:
    trips = (
        await session.scalars(
            select(Trip).where(Trip.user_id == user.id).order_by(Trip.updated_at.desc())
        )
    ).all()
    summaries: list[TripSummary] = []
    for trip in trips:
        latest = await session.scalar(
            select(ItineraryModel.id)
            .where(ItineraryModel.trip_id == trip.id)
            .order_by(ItineraryModel.created_at.desc())
            .limit(1)
        )
        summaries.append(_to_summary(trip, latest))
    return summaries


@router.get("/{trip_id}", response_model=TripDetail)
async def get_trip(
    trip_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TripDetail:
    trip = await _owned_trip(trip_id, user, session)
    latest = await _latest_itinerary(trip_id, session)
    return TripDetail(
        trip_id=trip.id,
        title=trip.title or _derive_title(trip),
        destination=trip.destination,
        start_date=trip.start_date,
        end_date=trip.end_date,
        created_at=trip.created_at.isoformat(),
        updated_at=trip.updated_at.isoformat() if trip.updated_at else None,
        messages=[ChatMessageOut(**m) for m in (trip.messages or [])],
        itinerary_id=latest.id if latest else None,
        itinerary=Itinerary.model_validate(latest.data) if latest else None,
    )


@router.patch("/{trip_id}", response_model=TripSummary)
async def rename_trip(
    trip_id: str,
    req: TripRenameRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> TripSummary:
    trip = await _owned_trip(trip_id, user, session)
    trip.title = req.title.strip() or trip.title
    await session.commit()
    latest = await _latest_itinerary(trip_id, session)
    return _to_summary(trip, latest.id if latest else None)


@router.delete("/{trip_id}")
async def delete_trip(
    trip_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    trip = await _owned_trip(trip_id, user, session)
    # Remove child itineraries first (no cascade configured).
    itineraries = (
        await session.scalars(
            select(ItineraryModel).where(ItineraryModel.trip_id == trip.id)
        )
    ).all()
    for it in itineraries:
        await session.delete(it)
    await session.delete(trip)
    await session.commit()
    return {"status": "deleted"}


# --- Chat (persisted, streaming) -------------------------------------------


async def _chat_context(trip: Trip, user: User, last_user: str, deps: Deps) -> str:
    blocks = [await _build_context(last_user, deps)]
    if trip.destination:
        blocks.append(f"TRIP destination={trip.destination} | dates {trip.start_date}–{trip.end_date}")
    if user.passport_countries:
        blocks.append(
            "TRAVELLER passports=" + ", ".join(user.passport_countries) + ". When asked about "
            "visas, give brief reminders only and point to official sources."
        )
    return "\n".join(b for b in blocks if b)


@router.post("/{trip_id}/chat")
async def chat_turn(
    trip_id: str,
    req: ChatTurnRequest,
    user: User = Depends(get_current_user),
    deps: Deps = Depends(get_deps),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    trip = await _owned_trip(trip_id, user, session)

    content = req.content.strip()
    if not content:
        raise BadRequestError("Message cannot be empty.")

    _append_message(trip, "user", content)
    if not trip.title:
        trip.title = _derive_title(trip)
    history = list(trip.messages)
    await session.commit()

    context = await _chat_context(trip, user, content, deps)
    llm_messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "system", "content": f"Context retrieved for this turn:\n{context}"},
    ]
    llm_messages += [{"role": m["role"], "content": m["content"]} for m in history]

    async def token_stream() -> AsyncIterator[str]:
        parts: list[str] = []
        async for chunk in deps.llm.stream(llm_messages, tier=ModelTier.CHEAP):
            parts.append(chunk)
            yield chunk
        # Persist the assistant reply in a fresh session once streaming completes.
        reply = "".join(parts)
        async with SessionLocal() as persist:
            fresh = await persist.get(Trip, trip_id)
            if fresh is not None:
                fresh.messages = [
                    *(fresh.messages or []),
                    {"role": "assistant", "content": reply, "ts": _now_iso()},
                ]
                await persist.commit()

    return StreamingResponse(token_stream(), media_type="text/plain; charset=utf-8")


# --- Plan (Update plan button) ---------------------------------------------


@router.post("/{trip_id}/plan", response_model=ItineraryResponse)
async def update_plan(
    trip_id: str,
    user: User = Depends(get_current_user),
    deps: Deps = Depends(get_deps),
    session: AsyncSession = Depends(get_session),
) -> ItineraryResponse:
    trip = await _owned_trip(trip_id, user, session)
    if not trip.messages:
        raise BadRequestError("Tell Puppycat about your trip before updating the plan.")

    existing_record = await _latest_itinerary(trip_id, session)
    req = await extract_trip_request(list(trip.messages), deps, existing=trip.params or None)

    missing = [
        label
        for label, value in (
            ("destination", req.destination),
            ("start date", req.start_date),
            ("end date", req.end_date),
        )
        if not value
    ]
    if missing:
        raise BadRequestError(
            "I still need your " + ", ".join(missing) + ". Mention them in the chat, then "
            "press Update plan again."
        )

    if existing_record is None:
        itinerary = await generate_itinerary(req, deps)
    else:
        existing = Itinerary.model_validate(existing_record.data)
        itinerary = await revise_itinerary(existing, list(trip.messages), req, deps)

    record = ItineraryModel(
        trip_id=trip.id,
        data=itinerary.model_dump(mode="json"),
        warnings=[w.model_dump(mode="json") for w in itinerary.warnings],
    )
    session.add(record)

    trip.destination = req.destination
    trip.start_date = req.start_date
    trip.end_date = req.end_date
    trip.params = req.model_dump(mode="json")
    if not trip.title or trip.title.startswith("Trip to") or len(trip.messages) <= 2:
        trip.title = f"Trip to {req.destination}"
    await session.commit()

    return ItineraryResponse(trip_id=trip.id, itinerary_id=record.id, itinerary=itinerary)


# --- Concise summary (deterministic) ---------------------------------------


def _derive_summary(it: Itinerary) -> SummaryItinerary:
    days: list[SummaryDay] = []
    for d in it.days:
        transport = [i.name for i in d.items if (i.category or "").lower() == "transport"]
        activities = [i.name for i in d.items if (i.category or "").lower() != "transport"]
        days.append(
            SummaryDay(
                date=d.date,
                destination=it.destination,
                transport=transport,
                activities=activities,
                accommodation=d.accommodation,
            )
        )
    return SummaryItinerary(
        destination=it.destination,
        start_date=it.start_date,
        end_date=it.end_date,
        days=days,
    )


@router.get("/{trip_id}/summary", response_model=SummaryItinerary)
async def trip_summary(
    trip_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> SummaryItinerary:
    await _owned_trip(trip_id, user, session)
    latest = await _latest_itinerary(trip_id, session)
    if latest is None:
        raise NotFoundError("No itinerary to summarise yet.")
    return _derive_summary(Itinerary.model_validate(latest.data))


# --- Visa notices (skill) ---------------------------------------------------


@router.get("/{trip_id}/visa-notice", response_model=TripVisaNotices)
async def trip_visa_notice(
    trip_id: str,
    user: User = Depends(get_current_user),
    deps: Deps = Depends(get_deps),
    session: AsyncSession = Depends(get_session),
) -> TripVisaNotices:
    trip = await _owned_trip(trip_id, user, session)
    if not trip.destination or not user.passport_countries:
        return TripVisaNotices(destination=trip.destination, notices=[])

    duration = 14
    notices = await asyncio.gather(
        *(
            build_visa_notice(
                passport,
                trip.destination,
                deps,
                duration_days=duration,
            )
            for passport in user.passport_countries
        )
    )
    return TripVisaNotices(destination=trip.destination, notices=list(notices))

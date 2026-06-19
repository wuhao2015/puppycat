from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.deps import Deps, UnauthorizedError, get_current_user, get_deps
from app.errors import PuppycatError
from app.models import Itinerary as ItineraryModel
from app.models import Trip, User
from app.pipeline import generate_itinerary
from app.schemas import Itinerary, ItineraryResponse, TripRequest, TripSummary

router = APIRouter(prefix="/api", tags=["itinerary"])


class NotFoundError(PuppycatError):
    status_code = 404


@router.post("/itinerary", response_model=ItineraryResponse)
async def create_itinerary(
    req: TripRequest,
    user: User = Depends(get_current_user),
    deps: Deps = Depends(get_deps),
    session: AsyncSession = Depends(get_session),
) -> ItineraryResponse:
    itinerary = await generate_itinerary(req, deps)

    trip = Trip(
        user_id=user.id,
        destination=req.destination,
        start_date=req.start_date,
        end_date=req.end_date,
        params=req.model_dump(mode="json"),
    )
    session.add(trip)
    await session.flush()

    record = ItineraryModel(
        trip_id=trip.id,
        data=itinerary.model_dump(mode="json"),
        warnings=[w.model_dump(mode="json") for w in itinerary.warnings],
    )
    session.add(record)
    await session.commit()

    return ItineraryResponse(trip_id=trip.id, itinerary_id=record.id, itinerary=itinerary)


@router.get("/trips", response_model=list[TripSummary])
async def list_trips(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[TripSummary]:
    """All trips owned by the authed user, newest first, with their latest itinerary."""
    trips = (
        await session.scalars(
            select(Trip).where(Trip.user_id == user.id).order_by(Trip.created_at.desc())
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
        summaries.append(
            TripSummary(
                trip_id=trip.id,
                destination=trip.destination,
                start_date=trip.start_date,
                end_date=trip.end_date,
                created_at=trip.created_at.isoformat(),
                itinerary_id=latest,
            )
        )
    return summaries


@router.get("/itineraries/{itinerary_id}", response_model=ItineraryResponse)
async def get_itinerary(
    itinerary_id: str,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> ItineraryResponse:
    record = await session.get(ItineraryModel, itinerary_id)
    if record is None:
        raise NotFoundError("Itinerary not found.")

    trip = await session.get(Trip, record.trip_id)
    if trip is None or trip.user_id != user.id:
        # Don't reveal existence of other users' itineraries.
        raise UnauthorizedError("You do not have access to this itinerary.")

    return ItineraryResponse(
        trip_id=trip.id,
        itinerary_id=record.id,
        itinerary=Itinerary.model_validate(record.data),
    )

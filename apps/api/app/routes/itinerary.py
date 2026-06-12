from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import Deps, get_deps, require_api_key
from app.db import get_session
from app.models import Itinerary as ItineraryModel
from app.models import Trip, User
from app.pipeline import generate_itinerary
from app.schemas import ItineraryResponse, TripRequest

router = APIRouter(prefix="/api", tags=["itinerary"])

_DEFAULT_EMAIL = "local@puppycat.app"


async def _get_or_create_default_user(session: AsyncSession) -> User:
    """v1 single-user helper. Multi-user replaces this with the authed user."""
    result = await session.execute(select(User).where(User.email == _DEFAULT_EMAIL))
    user = result.scalar_one_or_none()
    if user is None:
        user = User(email=_DEFAULT_EMAIL, display_name="Local User")
        session.add(user)
        await session.flush()
    return user


@router.post("/itinerary", response_model=ItineraryResponse, dependencies=[Depends(require_api_key)])
async def create_itinerary(
    req: TripRequest,
    deps: Deps = Depends(get_deps),
    session: AsyncSession = Depends(get_session),
) -> ItineraryResponse:
    itinerary = await generate_itinerary(req, deps)

    user = await _get_or_create_default_user(session)
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

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_owned_trip
from app.models import Trip, User
from app.schemas import ChatMessage


async def create_trip(
    session: AsyncSession, *, current_user: User, title: str
) -> Trip:
    trip = Trip(user_id=current_user.id, title=title)
    session.add(trip)
    await session.commit()
    await session.refresh(trip)
    return trip


async def list_trips(session: AsyncSession, *, current_user: User) -> list[Trip]:
    trips = await session.scalars(
        select(Trip)
        .where(Trip.user_id == current_user.id)
        .order_by(Trip.updated_at.desc(), Trip.created_at.desc(), Trip.id.desc())
    )
    return list(trips)


async def rename_trip(
    session: AsyncSession,
    *,
    trip_id: str,
    current_user: User,
    title: str,
) -> Trip:
    trip = await get_owned_trip(session, trip_id=trip_id, current_user=current_user)
    trip.title = title
    await session.commit()
    await session.refresh(trip)
    return trip


async def delete_trip(
    session: AsyncSession, *, trip_id: str, current_user: User
) -> None:
    trip = await get_owned_trip(session, trip_id=trip_id, current_user=current_user)
    await session.delete(trip)
    await session.commit()


async def append_user_message(
    session: AsyncSession,
    *,
    trip_id: str,
    current_user: User,
    content: str,
) -> tuple[Trip, ChatMessage]:
    trip = await get_owned_trip(session, trip_id=trip_id, current_user=current_user)
    message = ChatMessage(
        role="user",
        content=content,
        ts=datetime.now(timezone.utc),
    )

    # JSONB mutations are persisted reliably when the whole value is reassigned.
    trip.chat_messages = [
        *(trip.chat_messages or []),
        message.model_dump(mode="json"),
    ]
    await session.commit()
    await session.refresh(trip)
    return trip, message

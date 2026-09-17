import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_owned_trip
from app.gemini import GeminiMessage
from app.models import Trip, User
from app.schemas import ChatMessage


CHAT_CONTEXT_MESSAGE_LIMIT = 20
CHAT_SYSTEM_PROMPT = """You are Puppycat, a friendly travel planning assistant.
Use this conversation to understand the traveller's destination, dates, budget,
interests, group size, pace, and constraints. Ask focused follow-up questions when
important information is missing. Keep answers concise and practical. Do not claim
that current prices, opening hours, availability, weather, or other live facts have
been verified unless verified source data is included in the conversation context."""


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


async def append_assistant_message(
    session: AsyncSession,
    *,
    trip: Trip,
    content: str,
) -> tuple[Trip, ChatMessage]:
    await session.refresh(trip, attribute_names=["chat_messages"])
    message = ChatMessage(
        role="assistant",
        content=content,
        ts=datetime.now(timezone.utc),
    )
    trip.chat_messages = [
        *(trip.chat_messages or []),
        message.model_dump(mode="json"),
    ]
    await session.commit()
    await session.refresh(trip)
    return trip, message


def build_chat_context(trip: Trip) -> list[GeminiMessage]:
    trip_data = {
        "title": trip.title,
        "destination": trip.destination,
        "start_date": trip.start_date.isoformat() if trip.start_date else None,
        "end_date": trip.end_date.isoformat() if trip.end_date else None,
        "preferences": trip.preferences or {},
    }
    messages = [
        GeminiMessage(role="system", content=CHAT_SYSTEM_PROMPT),
        GeminiMessage(
            role="system",
            content=(
                "Known trip data (treat null or empty values as not provided):\n"
                f"{json.dumps(trip_data, ensure_ascii=False, sort_keys=True)}"
            ),
        ),
    ]
    for payload in (trip.chat_messages or [])[-CHAT_CONTEXT_MESSAGE_LIMIT:]:
        message = ChatMessage.model_validate(payload)
        messages.append(GeminiMessage(role=message.role, content=message.content))
    return messages

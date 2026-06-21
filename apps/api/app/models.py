from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    """A user of the app. v1 has a single local user, but every owned row
    carries `user_id` so multi-user is additive rather than a migration."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    email: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    display_name: Mapped[str | None] = mapped_column(String, nullable=True)
    # bcrypt hash. Nullable so the seeded local user (no password) stays valid.
    password_hash: Mapped[str | None] = mapped_column(String, nullable=True)
    # Nationalities the user holds, as ISO country codes, used to ground visa advice.
    passport_countries: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    home_country: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    trips: Mapped[list["Trip"]] = relationship(back_populates="user")


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    # Short label for the chat session / trip, shown in the sidebar.
    title: Mapped[str | None] = mapped_column(String, nullable=True)
    # Nullable: a fresh chat session has no destination/dates until the plan is built.
    destination: Mapped[str | None] = mapped_column(String, nullable=True)
    start_date: Mapped[str | None] = mapped_column(String, nullable=True)  # ISO date
    end_date: Mapped[str | None] = mapped_column(String, nullable=True)  # ISO date
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # Persisted chat history: list of {"role", "content", "ts"}.
    messages: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=_now
    )

    user: Mapped[User] = relationship(back_populates="trips")
    itineraries: Mapped[list["Itinerary"]] = relationship(back_populates="trip")


class Itinerary(Base):
    __tablename__ = "itineraries"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    trip_id: Mapped[str] = mapped_column(ForeignKey("trips.id"), index=True)
    # Full validated itinerary document (days, items, reservation links).
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
    # Freshness warnings surfaced by the verification pass.
    warnings: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    trip: Mapped[Trip] = relationship(back_populates="itineraries")


class ApiCache(Base):
    """Durable cache for external API responses, keyed by (source, query, date)."""

    __tablename__ = "api_cache"

    key: Mapped[str] = mapped_column(String, primary_key=True)
    payload: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

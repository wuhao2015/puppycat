from collections.abc import AsyncGenerator
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session


async def cache_get(key: str) -> Any | None:
    from app.models import ApiCache

    async with SessionLocal() as session:
        row = await session.get(ApiCache, key)
        if row is None:
            return None

        if row.expires_at is not None and row.expires_at <= datetime.now(timezone.utc):
            await session.delete(row)
            await session.commit()
            return None

        return row.payload


async def cache_set(key: str, payload: Any, ttl_seconds: int | None = None) -> None:
    from app.models import ApiCache

    expires_at = (
        datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        if ttl_seconds is not None
        else None
    )
    statement = insert(ApiCache).values(
        key=key,
        payload=payload,
        expires_at=expires_at,
    )
    statement = statement.on_conflict_do_update(
        index_elements=[ApiCache.key],
        set_={"payload": payload, "expires_at": expires_at},
    )

    async with SessionLocal() as session:
        await session.execute(statement)
        await session.commit()

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, select

from app.db import SessionLocal


class CacheBackend(ABC):
    """Pluggable cache. v1 ships in-memory + Postgres implementations;
    a Redis implementation can be dropped in later without touching callers."""

    @abstractmethod
    async def get(self, key: str) -> Any | None: ...

    @abstractmethod
    async def set(self, key: str, value: Any, ttl_seconds: int) -> None: ...


class InMemoryCache(CacheBackend):
    """Process-local cache. Good for tests and single-process dev."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[float, Any]] = {}

    async def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if expires_at < time.time():
            self._store.pop(key, None)
            return None
        return value

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        self._store[key] = (time.time() + ttl_seconds, value)


class PostgresCache(CacheBackend):
    """Durable cache backed by the `api_cache` table.

    Survives restarts and is shared across processes, which matters once the
    app runs more than one worker. JSON-serialisable payloads only.
    """

    async def get(self, key: str) -> Any | None:
        from app.models import ApiCache

        async with SessionLocal() as session:
            row = await session.get(ApiCache, key)
            if row is None:
                return None
            if row.expires_at < datetime.now(timezone.utc):
                await session.execute(delete(ApiCache).where(ApiCache.key == key))
                await session.commit()
                return None
            return json.loads(row.payload)

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        from app.models import ApiCache

        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        payload = json.dumps(value)
        async with SessionLocal() as session:
            existing = await session.get(ApiCache, key)
            if existing is None:
                session.add(ApiCache(key=key, payload=payload, expires_at=expires_at))
            else:
                existing.payload = payload
                existing.expires_at = expires_at
            await session.commit()


def build_cache(backend: str = "postgres") -> CacheBackend:
    return InMemoryCache() if backend == "memory" else PostgresCache()

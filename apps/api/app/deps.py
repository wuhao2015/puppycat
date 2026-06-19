from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import CacheBackend, build_cache
from app.config import Settings, get_settings
from app.datasources import PlacesClient, WeatherClient, WebSearchClient
from app.db import get_session
from app.errors import PuppycatError
from app.llm import LLMProvider, build_llm_provider
from app.models import User
from app.security import decode_access_token


class UnauthorizedError(PuppycatError):
    status_code = 401


@dataclass
class Deps:
    """Container of shared services handed to the pipeline and routes."""

    settings: Settings
    cache: CacheBackend
    places: PlacesClient
    web_search: WebSearchClient
    weather: WeatherClient
    llm: LLMProvider


@lru_cache
def get_deps() -> Deps:
    settings = get_settings()
    cache = build_cache("postgres")
    return Deps(
        settings=settings,
        cache=cache,
        places=PlacesClient(cache, settings),
        web_search=WebSearchClient(cache, settings),
        weather=WeatherClient(cache, settings),
        llm=build_llm_provider(settings),
    )


async def get_current_user(
    authorization: str | None = Header(default=None),
    session: AsyncSession = Depends(get_session),
) -> User:
    """Resolve the authenticated user from a `Authorization: Bearer <jwt>` header."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UnauthorizedError("Missing or malformed Authorization header.")
    token = authorization.split(" ", 1)[1].strip()
    try:
        user_id = decode_access_token(token, get_settings())
    except jwt.PyJWTError:
        raise UnauthorizedError("Invalid or expired token.")
    user = await session.get(User, user_id)
    if user is None:
        raise UnauthorizedError("User no longer exists.")
    return user

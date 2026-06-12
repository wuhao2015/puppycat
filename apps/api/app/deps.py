from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from fastapi import Header

from app.cache import CacheBackend, build_cache
from app.config import Settings, get_settings
from app.datasources import PlacesClient, WeatherClient, WebSearchClient
from app.errors import PuppycatError
from app.llm import LLMProvider, build_llm_provider


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


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Single-user auth for v1. Replace with real auth when going multi-user."""
    settings = get_settings()
    if x_api_key != settings.app_api_key:
        raise UnauthorizedError("Invalid or missing X-API-Key header.")

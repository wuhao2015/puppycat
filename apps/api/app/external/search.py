import logging
from collections.abc import Sequence
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.db import cache_get, cache_set
from app.external import build_cache_key


logger = logging.getLogger(__name__)

SEARCH_CACHE_TTL_SECONDS = 6 * 60 * 60
_SEARCH_URL = "https://api.tavily.com/search"

SearchTopic = Literal["general", "news"]
SearchTimeRange = Literal["day", "week", "month", "year"]
SearchUnavailableReason = Literal[
    "not_configured",
    "request_failed",
    "invalid_response",
]


class SearchItem(BaseModel):
    title: str
    url: str
    content: str
    score: float | None = None
    published_date: str | None = None


class SearchResult(BaseModel):
    source: Literal["tavily"] = "tavily"
    status: Literal["available", "unavailable"]
    results: list[SearchItem] = Field(default_factory=list)
    unavailable_reason: SearchUnavailableReason | None = None


class _TavilyItem(BaseModel):
    title: str
    url: str
    content: str
    score: float | None = None
    published_date: str | None = None


class _TavilyResponse(BaseModel):
    results: list[_TavilyItem]


class SearchClient:
    def __init__(self, http: httpx.AsyncClient, *, api_key: str) -> None:
        self._http = http
        self._api_key = api_key

    async def search(
        self,
        query: str,
        *,
        topic: SearchTopic = "general",
        time_range: SearchTimeRange | None = None,
        max_results: int = 5,
        include_domains: Sequence[str] = (),
    ) -> SearchResult:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("Search query cannot be empty")
        if not 1 <= max_results <= 20:
            raise ValueError("max_results must be between 1 and 20")

        domains = sorted(
            {
                domain.strip().lower()
                for domain in include_domains
                if domain.strip()
            }
        )
        cache_key = build_cache_key(
            "search:tavily",
            {
                "query": normalized_query,
                "topic": topic,
                "time_range": time_range,
                "max_results": max_results,
                "include_domains": domains,
            },
        )
        cached = await self._cached(cache_key)
        if cached is not None:
            return cached
        if not self._api_key:
            return SearchResult(
                status="unavailable",
                unavailable_reason="not_configured",
            )

        body: dict[str, object] = {
            "query": normalized_query,
            "topic": topic,
            "search_depth": "basic",
            "max_results": max_results,
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
            "include_published_date": True,
            "safe_search": True,
        }
        if time_range:
            body["time_range"] = time_range
        if domains:
            body["include_domains"] = domains

        try:
            response = await self._http.post(
                _SEARCH_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=body,
            )
            response.raise_for_status()
            upstream = _TavilyResponse.model_validate(response.json())
            result = SearchResult(
                status="available",
                results=[
                    SearchItem(
                        title=item.title,
                        url=item.url,
                        content=item.content,
                        score=item.score,
                        published_date=item.published_date,
                    )
                    for item in upstream.results
                ],
            )
        except httpx.HTTPError as error:
            status = (
                error.response.status_code
                if isinstance(error, httpx.HTTPStatusError)
                else None
            )
            logger.warning(
                "Tavily search failed (status=%s)",
                status or "network_error",
            )
            return SearchResult(
                status="unavailable",
                unavailable_reason="request_failed",
            )
        except (ValueError, ValidationError):
            logger.warning("Tavily search returned an invalid response")
            return SearchResult(
                status="unavailable",
                unavailable_reason="invalid_response",
            )

        try:
            await cache_set(
                cache_key,
                result.model_dump(mode="json"),
                ttl_seconds=SEARCH_CACHE_TTL_SECONDS,
            )
        except SQLAlchemyError:
            logger.warning("Could not persist Tavily search cache entry")
        return result

    async def _cached(self, key: str) -> SearchResult | None:
        try:
            payload = await cache_get(key)
            return (
                SearchResult.model_validate(payload)
                if payload is not None
                else None
            )
        except (SQLAlchemyError, ValidationError):
            logger.warning("Ignoring unavailable or invalid Tavily cache entry")
            return None

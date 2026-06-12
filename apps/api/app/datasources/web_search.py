from __future__ import annotations

import hashlib

import httpx
from pydantic import BaseModel

from app.cache import CacheBackend
from app.config import Settings, get_settings


class SearchResult(BaseModel):
    title: str
    url: str
    content: str = ""


class WebSearchClient:
    """Freshness layer. Catches things no structured API knows: one-off
    closures, strikes, public-holiday hours, local events, safety advisories.

    Provider is pluggable ("tavily" default, "brave" alternative). Results are
    cached on a short TTL since freshness is the whole point.
    """

    name = "web_search"

    def __init__(self, cache: CacheBackend, settings: Settings | None = None) -> None:
        self._cache = cache
        self._settings = settings or get_settings()

    @property
    def provider(self) -> str:
        return self._settings.web_search_provider

    def is_configured(self) -> bool:
        if self.provider == "brave":
            return bool(self._settings.brave_search_api_key)
        return bool(self._settings.tavily_api_key)

    @staticmethod
    def _cache_key(provider: str, query: str, recency_days: int | None) -> str:
        digest = hashlib.sha256(f"{provider}|{query}|{recency_days}".encode()).hexdigest()[:32]
        return f"websearch:{digest}"

    async def search(
        self, query: str, *, max_results: int = 5, recency_days: int | None = None
    ) -> list[SearchResult]:
        key = self._cache_key(self.provider, query, recency_days)
        cached = await self._cache.get(key)
        if cached is not None:
            return [SearchResult.model_validate(r) for r in cached]

        if self.provider == "brave":
            results = await self._search_brave(query, max_results)
        else:
            results = await self._search_tavily(query, max_results, recency_days)

        await self._cache.set(
            key,
            [r.model_dump(mode="json") for r in results],
            self._settings.cache_ttl_web_search,
        )
        return results

    async def _search_tavily(
        self, query: str, max_results: int, recency_days: int | None
    ) -> list[SearchResult]:
        payload = {
            "api_key": self._settings.tavily_api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": "basic",
            "topic": "news" if recency_days else "general",
        }
        if recency_days:
            payload["days"] = recency_days

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post("https://api.tavily.com/search", json=payload)
            resp.raise_for_status()
            data = resp.json()

        return [
            SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                content=r.get("content", ""),
            )
            for r in data.get("results", [])
        ]

    async def _search_brave(self, query: str, max_results: int) -> list[SearchResult]:
        headers = {"X-Subscription-Token": self._settings.brave_search_api_key}
        params = {"q": query, "count": max_results}
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                "https://api.search.brave.com/res/v1/web/search",
                headers=headers,
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()

        results = (data.get("web") or {}).get("results", [])
        return [
            SearchResult(
                title=r.get("title", ""),
                url=r.get("url", ""),
                content=r.get("description", ""),
            )
            for r in results[:max_results]
        ]

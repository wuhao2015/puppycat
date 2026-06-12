from __future__ import annotations

import hashlib
from typing import Any

import httpx

from app.cache import CacheBackend
from app.config import Settings, get_settings
from app.schemas import BusinessStatus, GeoPoint, Place

_BASE_URL = "https://places.googleapis.com/v1"

# Field mask shared by search + details. Requesting only what we use keeps the
# Places bill down (the API charges by the SKUs implied by requested fields).
_PLACE_FIELDS = [
    "id",
    "displayName",
    "formattedAddress",
    "location",
    "businessStatus",
    "rating",
    "userRatingCount",
    "websiteUri",
    "googleMapsUri",
    "types",
    "regularOpeningHours.weekdayDescriptions",
    "currentOpeningHours.openNow",
]


def _search_mask() -> str:
    return ",".join(f"places.{f}" for f in _PLACE_FIELDS)


class PlacesClient:
    """Google Places API (New) client. Implements the DataSource protocol.

    Results are normalised to `Place` and cached so repeated planning over the
    same destination does not re-bill the Places API.
    """

    name = "google_places"

    def __init__(self, cache: CacheBackend, settings: Settings | None = None) -> None:
        self._cache = cache
        self._settings = settings or get_settings()

    def is_configured(self) -> bool:
        return bool(self._settings.google_places_api_key)

    def _headers(self, field_mask: str) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self._settings.google_places_api_key,
            "X-Goog-FieldMask": field_mask,
        }

    @staticmethod
    def _cache_key(*parts: Any) -> str:
        raw = "|".join(str(p) for p in parts)
        digest = hashlib.sha256(raw.encode()).hexdigest()[:32]
        return f"places:{digest}"

    async def text_search(self, query: str, *, max_results: int = 15) -> list[Place]:
        key = self._cache_key("text", query, max_results)
        cached = await self._cache.get(key)
        if cached is not None:
            return [Place.model_validate(p) for p in cached]

        payload = {"textQuery": query, "maxResultCount": max_results}
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{_BASE_URL}/places:searchText",
                headers=self._headers(_search_mask()),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        places = [self._normalise(p) for p in data.get("places", [])]
        await self._cache.set(
            key, [p.model_dump(mode="json") for p in places], self._settings.cache_ttl_places
        )
        return places

    async def nearby_search(
        self,
        location: GeoPoint,
        *,
        radius_m: float = 2000,
        included_types: list[str] | None = None,
        max_results: int = 15,
    ) -> list[Place]:
        key = self._cache_key("nearby", location.lat, location.lng, radius_m, included_types)
        cached = await self._cache.get(key)
        if cached is not None:
            return [Place.model_validate(p) for p in cached]

        payload: dict[str, Any] = {
            "maxResultCount": max_results,
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": location.lat, "longitude": location.lng},
                    "radius": radius_m,
                }
            },
        }
        if included_types:
            payload["includedTypes"] = included_types

        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.post(
                f"{_BASE_URL}/places:searchNearby",
                headers=self._headers(_search_mask()),
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        places = [self._normalise(p) for p in data.get("places", [])]
        await self._cache.set(
            key, [p.model_dump(mode="json") for p in places], self._settings.cache_ttl_places
        )
        return places

    async def get_details(self, place_id: str) -> Place | None:
        key = self._cache_key("details", place_id)
        cached = await self._cache.get(key)
        if cached is not None:
            return Place.model_validate(cached)

        mask = ",".join(_PLACE_FIELDS)
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(
                f"{_BASE_URL}/places/{place_id}", headers=self._headers(mask)
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()

        place = self._normalise(data)
        await self._cache.set(
            key, place.model_dump(mode="json"), self._settings.cache_ttl_places
        )
        return place

    @staticmethod
    def _normalise(raw: dict[str, Any]) -> Place:
        loc = raw.get("location") or {}
        location = (
            GeoPoint(lat=loc["latitude"], lng=loc["longitude"])
            if "latitude" in loc and "longitude" in loc
            else None
        )

        opening_hours: dict[str, str] = {}
        descriptions = (raw.get("regularOpeningHours") or {}).get("weekdayDescriptions", [])
        for line in descriptions:
            if ": " in line:
                day, hours = line.split(": ", 1)
                opening_hours[day] = hours

        try:
            status = BusinessStatus(raw.get("businessStatus", "UNKNOWN"))
        except ValueError:
            status = BusinessStatus.UNKNOWN

        return Place(
            place_id=raw.get("id", ""),
            name=(raw.get("displayName") or {}).get("text", "Unknown"),
            address=raw.get("formattedAddress"),
            location=location,
            business_status=status,
            rating=raw.get("rating"),
            user_rating_count=raw.get("userRatingCount"),
            website=raw.get("websiteUri"),
            google_maps_uri=raw.get("googleMapsUri"),
            types=raw.get("types", []),
            opening_hours=opening_hours,
            open_now=(raw.get("currentOpeningHours") or {}).get("openNow"),
        )

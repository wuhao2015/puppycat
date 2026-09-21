import logging
from typing import Literal
from urllib.parse import quote

import httpx
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.db import cache_get, cache_set
from app.external import build_cache_key


logger = logging.getLogger(__name__)

PLACES_CACHE_TTL_SECONDS = 24 * 60 * 60
_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
_PLACE_DETAILS_URL = "https://places.googleapis.com/v1/places/{place_id}"
_SEARCH_FIELD_MASK = ",".join(
    (
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.types",
        "places.primaryType",
        "places.addressComponents",
        "places.businessStatus",
        "places.googleMapsUri",
    )
)
_DETAILS_FIELD_MASK = ",".join(
    (
        "id",
        "displayName",
        "formattedAddress",
        "location",
        "types",
        "primaryType",
        "addressComponents",
        "businessStatus",
        "googleMapsUri",
        "websiteUri",
        "regularOpeningHours",
    )
)

PlacesUnavailableReason = Literal[
    "not_configured",
    "request_failed",
    "invalid_response",
]


class PlaceCoordinate(BaseModel):
    latitude: float
    longitude: float


class PlaceOpeningTime(BaseModel):
    # Google Places numbers Sunday as 0 through Saturday as 6.
    day: int = Field(ge=0, le=6)
    hour: int = Field(ge=0, le=23)
    minute: int = Field(ge=0, le=59)


class PlaceOpeningPeriod(BaseModel):
    opens_at: PlaceOpeningTime
    closes_at: PlaceOpeningTime | None = None


class PlaceOpeningHours(BaseModel):
    periods: list[PlaceOpeningPeriod]
    weekday_descriptions: list[str]


class Place(BaseModel):
    place_id: str
    name: str
    address: str | None = None
    location: PlaceCoordinate | None = None
    types: list[str] = Field(default_factory=list)
    primary_type: str | None = None
    country_code: str | None = None
    country_name: str | None = None
    business_status: str | None = None
    google_maps_uri: str | None = None
    website_uri: str | None = None
    opening_hours: PlaceOpeningHours | None = None


class PlacesSearchResult(BaseModel):
    source: Literal["google_places"] = "google_places"
    status: Literal["available", "unavailable"]
    places: list[Place] = Field(default_factory=list)
    unavailable_reason: PlacesUnavailableReason | None = None


class PlaceDetailsResult(BaseModel):
    source: Literal["google_places"] = "google_places"
    status: Literal["available", "not_found", "unavailable"]
    place: Place | None = None
    unavailable_reason: PlacesUnavailableReason | None = None


class _GoogleText(BaseModel):
    text: str


class _GoogleCoordinate(BaseModel):
    latitude: float
    longitude: float


class _GoogleAddressComponent(BaseModel):
    short_text: str = Field(alias="shortText")
    long_text: str | None = Field(default=None, alias="longText")
    types: list[str] = Field(default_factory=list)


class _GoogleOpeningTime(BaseModel):
    # Protobuf JSON omits numeric fields whose value is zero.
    day: int = 0
    hour: int = 0
    minute: int = 0


class _GoogleOpeningPeriod(BaseModel):
    open: _GoogleOpeningTime
    close: _GoogleOpeningTime | None = None


class _GoogleOpeningHours(BaseModel):
    periods: list[_GoogleOpeningPeriod] = Field(default_factory=list)
    weekday_descriptions: list[str] = Field(
        default_factory=list,
        alias="weekdayDescriptions",
    )


class _GooglePlace(BaseModel):
    id: str
    display_name: _GoogleText = Field(alias="displayName")
    formatted_address: str | None = Field(default=None, alias="formattedAddress")
    location: _GoogleCoordinate | None = None
    types: list[str] = Field(default_factory=list)
    primary_type: str | None = Field(default=None, alias="primaryType")
    address_components: list[_GoogleAddressComponent] = Field(
        default_factory=list,
        alias="addressComponents",
    )
    business_status: str | None = Field(default=None, alias="businessStatus")
    google_maps_uri: str | None = Field(default=None, alias="googleMapsUri")
    website_uri: str | None = Field(default=None, alias="websiteUri")
    regular_opening_hours: _GoogleOpeningHours | None = Field(
        default=None,
        alias="regularOpeningHours",
    )


class _GoogleSearchResponse(BaseModel):
    places: list[_GooglePlace] = Field(default_factory=list)


class PlacesClient:
    def __init__(self, http: httpx.AsyncClient, *, api_key: str) -> None:
        self._http = http
        self._api_key = api_key

    async def search_text(
        self,
        query: str,
        *,
        max_results: int = 10,
        language_code: str | None = None,
        region_code: str | None = None,
    ) -> PlacesSearchResult:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("Place search query cannot be empty")
        if not 1 <= max_results <= 20:
            raise ValueError("max_results must be between 1 and 20")

        language_code = language_code.strip() if language_code else None
        region_code = region_code.strip().upper() if region_code else None
        cache_key = build_cache_key(
            "places:search",
            {
                "query": normalized_query,
                "max_results": max_results,
                "language_code": language_code,
                "region_code": region_code,
            },
        )
        cached = await self._cached_search(cache_key)
        if cached is not None:
            return cached
        if not self._api_key:
            return PlacesSearchResult(
                status="unavailable",
                unavailable_reason="not_configured",
            )

        body: dict[str, object] = {
            "textQuery": normalized_query,
            "pageSize": max_results,
        }
        if language_code:
            body["languageCode"] = language_code
        if region_code:
            body["regionCode"] = region_code

        try:
            response = await self._http.post(
                _TEXT_SEARCH_URL,
                headers={
                    "X-Goog-Api-Key": self._api_key,
                    "X-Goog-FieldMask": _SEARCH_FIELD_MASK,
                },
                json=body,
            )
            response.raise_for_status()
            upstream = _GoogleSearchResponse.model_validate(response.json())
            result = PlacesSearchResult(
                status="available",
                places=[_normalize_place(place) for place in upstream.places],
            )
        except httpx.HTTPError as error:
            _log_http_failure("Google Places text search", error)
            return PlacesSearchResult(
                status="unavailable",
                unavailable_reason="request_failed",
            )
        except (ValueError, ValidationError):
            logger.warning("Google Places text search returned an invalid response")
            return PlacesSearchResult(
                status="unavailable",
                unavailable_reason="invalid_response",
            )

        await _cache_result(cache_key, result, PLACES_CACHE_TTL_SECONDS)
        return result

    async def details(
        self,
        place_id: str,
        *,
        language_code: str | None = None,
        region_code: str | None = None,
    ) -> PlaceDetailsResult:
        normalized_place_id = place_id.strip()
        if not normalized_place_id:
            raise ValueError("place_id cannot be empty")

        language_code = language_code.strip() if language_code else None
        region_code = region_code.strip().upper() if region_code else None
        cache_key = build_cache_key(
            "places:details",
            {
                "place_id": normalized_place_id,
                "language_code": language_code,
                "region_code": region_code,
            },
        )
        cached = await self._cached_details(cache_key)
        if cached is not None:
            return cached
        if not self._api_key:
            return PlaceDetailsResult(
                status="unavailable",
                unavailable_reason="not_configured",
            )

        params: dict[str, str] = {}
        if language_code:
            params["languageCode"] = language_code
        if region_code:
            params["regionCode"] = region_code

        try:
            response = await self._http.get(
                _PLACE_DETAILS_URL.format(
                    place_id=quote(normalized_place_id, safe="")
                ),
                headers={
                    "X-Goog-Api-Key": self._api_key,
                    "X-Goog-FieldMask": _DETAILS_FIELD_MASK,
                },
                params=params,
            )
            response.raise_for_status()
            result = PlaceDetailsResult(
                status="available",
                place=_normalize_place(_GooglePlace.model_validate(response.json())),
            )
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 404:
                result = PlaceDetailsResult(status="not_found")
                await _cache_result(
                    cache_key,
                    result,
                    PLACES_CACHE_TTL_SECONDS,
                )
                return result
            _log_http_failure("Google Places details", error)
            return PlaceDetailsResult(
                status="unavailable",
                unavailable_reason="request_failed",
            )
        except httpx.HTTPError as error:
            _log_http_failure("Google Places details", error)
            return PlaceDetailsResult(
                status="unavailable",
                unavailable_reason="request_failed",
            )
        except (ValueError, ValidationError):
            logger.warning("Google Places details returned an invalid response")
            return PlaceDetailsResult(
                status="unavailable",
                unavailable_reason="invalid_response",
            )

        await _cache_result(cache_key, result, PLACES_CACHE_TTL_SECONDS)
        return result

    async def _cached_search(self, key: str) -> PlacesSearchResult | None:
        try:
            payload = await cache_get(key)
            return (
                PlacesSearchResult.model_validate(payload)
                if payload is not None
                else None
            )
        except (SQLAlchemyError, ValidationError):
            logger.warning("Ignoring unavailable or invalid Places search cache entry")
            return None

    async def _cached_details(self, key: str) -> PlaceDetailsResult | None:
        try:
            payload = await cache_get(key)
            return (
                PlaceDetailsResult.model_validate(payload)
                if payload is not None
                else None
            )
        except (SQLAlchemyError, ValidationError):
            logger.warning("Ignoring unavailable or invalid Places details cache entry")
            return None


def _normalize_place(place: _GooglePlace) -> Place:
    country_component = next(
        (component for component in place.address_components if "country" in component.types),
        None,
    )
    opening_hours = None
    if place.regular_opening_hours is not None:
        opening_hours = PlaceOpeningHours(
            periods=[
                PlaceOpeningPeriod(
                    opens_at=PlaceOpeningTime(
                        day=period.open.day,
                        hour=period.open.hour,
                        minute=period.open.minute,
                    ),
                    closes_at=(
                        PlaceOpeningTime(
                            day=period.close.day,
                            hour=period.close.hour,
                            minute=period.close.minute,
                        )
                        if period.close is not None
                        else None
                    ),
                )
                for period in place.regular_opening_hours.periods
            ],
            weekday_descriptions=place.regular_opening_hours.weekday_descriptions,
        )

    return Place(
        place_id=place.id,
        name=place.display_name.text,
        address=place.formatted_address,
        location=(
            PlaceCoordinate(
                latitude=place.location.latitude,
                longitude=place.location.longitude,
            )
            if place.location is not None
            else None
        ),
        types=place.types,
        primary_type=place.primary_type,
        country_code=(
            country_component.short_text.upper() if country_component is not None else None
        ),
        country_name=(country_component.long_text if country_component is not None else None),
        business_status=place.business_status,
        google_maps_uri=place.google_maps_uri,
        website_uri=place.website_uri,
        opening_hours=opening_hours,
    )


async def _cache_result(
    key: str,
    result: BaseModel,
    ttl_seconds: int,
) -> None:
    try:
        await cache_set(key, result.model_dump(mode="json"), ttl_seconds=ttl_seconds)
    except SQLAlchemyError:
        logger.warning("Could not persist Google Places cache entry")


def _log_http_failure(action: str, error: httpx.HTTPError) -> None:
    status = (
        error.response.status_code
        if isinstance(error, httpx.HTTPStatusError)
        else None
    )
    logger.warning("%s failed (status=%s)", action, status or "network_error")

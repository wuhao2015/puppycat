from __future__ import annotations

import asyncio
from dataclasses import dataclass

from app.clients import AppClients
from app.external.places import Place
from app.external.search import SearchResult
from app.external.weather import WeatherResult
from app.schemas import Itinerary, Warning


@dataclass(frozen=True)
class VerificationResult:
    itinerary: Itinerary
    blocker_place_ids: set[str]


async def verify_itinerary(
    itinerary: Itinerary,
    *,
    clients: AppClients,
    places_available: bool,
    known_places: dict[str, Place] | None = None,
    reuse_global_from: Itinerary | None = None,
) -> VerificationResult:
    """Verify a draft while reusing already verified places on revisions."""

    verified = itinerary.model_copy(deep=True)
    known = known_places or {}
    place_ids = list(
        dict.fromkeys(
            item.place_id
            for day in verified.days
            for item in day.items
            if item.kind == "place" and item.place_id is not None
        )
    )
    new_place_ids = [place_id for place_id in place_ids if place_id not in known]

    if reuse_global_from is None:
        detail_results, weather, search = await asyncio.gather(
            asyncio.gather(
                *(clients.places.details(place_id) for place_id in new_place_ids)
            ),
            (
                clients.weather.forecast(
                    latitude=verified.destination_location.latitude,
                    longitude=verified.destination_location.longitude,
                    start_date=verified.start_date,
                    end_date=verified.end_date,
                )
                if verified.destination_location is not None
                else _weather_without_coordinates()
            ),
            clients.search.search(
                f"{verified.destination} travel closures strikes protests warnings",
                max_results=5,
            ),
        )
        global_warnings = _global_warnings(weather, search)
        weather_days = weather.days if weather.status == "available" else []
        weather_available = weather.status == "available"
        search_available = search.status == "available"
    else:
        detail_results = await asyncio.gather(
            *(clients.places.details(place_id) for place_id in new_place_ids)
        )
        global_warnings = list(reuse_global_from.warnings)
        weather_days = list(reuse_global_from.weather)
        weather_available = "open_meteo" in reuse_global_from.verified_sources
        search_available = "tavily" in reuse_global_from.verified_sources

    places_by_id = dict(known)
    result_by_id = dict(zip(new_place_ids, detail_results, strict=True))
    blockers: set[str] = set()
    place_unavailable = not places_available

    for place_id, result in result_by_id.items():
        if result.status == "available" and result.place is not None:
            places_by_id[place_id] = result.place
            if result.place.business_status in {
                "CLOSED_PERMANENTLY",
                "CLOSED_TEMPORARILY",
            }:
                blockers.add(place_id)
        elif result.status == "not_found":
            blockers.add(place_id)
        else:
            place_unavailable = True

    for day in verified.days:
        for item in day.items:
            item.place = places_by_id.get(item.place_id or "")
            item.warnings = []
            if item.place_id in blockers:
                item.warnings.append(
                    Warning(
                        level="blocker",
                        code="place_closed_or_missing",
                        message=f"{item.title} is closed or no longer available.",
                        source="google_places",
                        item_id=item.id,
                    )
                )
            elif item.kind == "place" and item.place is None:
                item.warnings.append(
                    Warning(
                        level="caution",
                        code="place_verification_unavailable",
                        message=f"Live details for {item.title} could not be verified.",
                        source="google_places",
                        item_id=item.id,
                    )
                )

    verified.weather = weather_days
    source_available = {
        "google_places": not place_unavailable,
        "open_meteo": weather_available,
        "tavily": search_available,
    }
    verified.verified_sources = [
        source for source, available in source_available.items() if available
    ]
    verified.unavailable_sources = [
        source for source, available in source_available.items() if not available
    ]
    if not verified.unavailable_sources:
        verified.verification_status = "verified"
    elif not verified.verified_sources:
        verified.verification_status = "unavailable"
    else:
        verified.verification_status = "partial"
    verified.warnings = global_warnings
    return VerificationResult(itinerary=verified, blocker_place_ids=blockers)


async def _weather_without_coordinates() -> WeatherResult:
    return WeatherResult(status="unavailable", unavailable_reason="invalid_response")


def _search_warnings(search: SearchResult) -> list[Warning]:
    risk_terms = ("closed", "closure", "strike", "protest", "warning")
    warnings: list[Warning] = []
    if search.status != "available":
        return warnings
    for result in search.results:
        text = f"{result.title} {result.content}".lower()
        if any(term in text for term in risk_terms):
            warnings.append(
                Warning(
                    level="caution",
                    code="recent_travel_notice",
                    message=result.title,
                    source="tavily",
                    source_url=result.url,
                )
            )
    return warnings


def _global_warnings(
    weather: WeatherResult,
    search: SearchResult,
) -> list[Warning]:
    warnings: list[Warning] = []
    if weather.status != "available":
        warnings.append(
            Warning(
                level="caution",
                code="weather_not_available",
                message=(
                    "Weather is not available for these dates yet."
                    if weather.status == "not_available_for_date"
                    else "Weather could not be verified."
                ),
                source="open_meteo",
            )
        )
    warnings.extend(_search_warnings(search))
    if search.status != "available":
        warnings.append(
            Warning(
                level="caution",
                code="travel_search_unavailable",
                message="Recent travel notices could not be checked.",
                source="tavily",
            )
        )
    return warnings


def known_places(itinerary: Itinerary) -> dict[str, Place]:
    return {
        item.place_id: item.place
        for day in itinerary.days
        for item in day.items
        if item.place_id is not None and item.place is not None
    }

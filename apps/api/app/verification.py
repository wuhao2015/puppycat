from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, time
from typing import Literal

from app.clients import AppClients
from app.external.places import Place, PlaceOpeningHours
from app.external.search import SearchResult
from app.external.weather import DailyWeather, WeatherResult
from app.schemas import Item, Itinerary, Warning


_WEEK_MINUTES = 7 * 24 * 60
_HIGH_RISK_PLACE_TYPES = {
    "airport",
    "amusement_park",
    "museum",
    "national_park",
    "stadium",
    "tourist_attraction",
    "train_station",
    "transit_station",
}
_HIGH_RISK_NAME_TERMS = (
    "airport",
    "museum",
    "park",
    "station",
    "stadium",
    "temple",
    "theme park",
    "zoo",
)
_OUTDOOR_PLACE_TYPES = {
    "beach",
    "campground",
    "garden",
    "hiking_area",
    "national_park",
    "park",
}
_OUTDOOR_TERMS = (
    "beach",
    "bike",
    "cycling",
    "garden",
    "hike",
    "hiking",
    "outdoor",
    "park",
    "picnic",
    "walking tour",
)
_SEVERE_WEATHER_CODES = {65, 66, 67, 75, 77, 82, 85, 86, 95, 96, 99}


@dataclass(frozen=True)
class VerificationResult:
    itinerary: Itinerary
    blocker_place_ids: set[str]


@dataclass(frozen=True)
class _SearchCheck:
    result: SearchResult
    item_id: str | None = None


async def verify_itinerary(
    itinerary: Itinerary,
    *,
    clients: AppClients,
    places_available: bool,
    known_places: dict[str, Place] | None = None,
    reuse_global_from: Itinerary | None = None,
) -> VerificationResult:
    """Verify itinerary facts and preserve explicit unavailable states."""

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
        detail_results, weather = await asyncio.gather(
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
        )
        weather_days = weather.days if weather.status == "available" else []
        weather_available = weather.status == "available"
        global_warnings = _weather_warnings(weather)
    else:
        detail_results = await asyncio.gather(
            *(clients.places.details(place_id) for place_id in new_place_ids)
        )
        weather_days = list(reuse_global_from.weather)
        weather_available = "open_meteo" in reuse_global_from.verified_sources
        current_item_ids = {
            item.id for day in verified.days for item in day.items
        }
        global_warnings = [
            warning
            for warning in reuse_global_from.warnings
            if warning.item_id is None or warning.item_id in current_item_ids
        ]

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

    search_checks = await _search_checks(
        verified,
        clients=clients,
        places_by_id=places_by_id,
        place_ids=(new_place_ids if reuse_global_from is not None else place_ids),
        include_destination=reuse_global_from is None,
    )
    if reuse_global_from is None:
        search_available = all(
            check.result.status == "available" for check in search_checks
        )
    else:
        search_available = (
            "tavily" in reuse_global_from.verified_sources
            and all(check.result.status == "available" for check in search_checks)
        )
    global_warnings.extend(_search_warnings(search_checks))
    if not search_available and not any(
        warning.code == "travel_search_unavailable"
        for warning in global_warnings
    ):
        global_warnings.append(
            Warning(
                level="caution",
                code="travel_search_unavailable",
                message="Some recent travel notices could not be checked.",
                source="tavily",
            )
        )

    weather_by_date = {weather_day.date: weather_day for weather_day in weather_days}
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
                continue
            if item.kind == "place" and item.place is None:
                place_unavailable = True
                item.warnings.append(
                    Warning(
                        level="caution",
                        code="place_verification_unavailable",
                        message=f"Live details for {item.title} could not be verified.",
                        source="google_places",
                        item_id=item.id,
                    )
                )
                continue
            if item.place is not None:
                place_warnings, place_complete = _place_warnings(
                    day.date,
                    item,
                    item.place,
                )
                item.warnings.extend(place_warnings)
                if not place_complete:
                    place_unavailable = True

            weather_day = weather_by_date.get(day.date)
            if weather_day is not None and _is_outdoor(item):
                weather_warning = _outdoor_weather_warning(item, weather_day)
                if weather_warning is not None:
                    item.warnings.append(weather_warning)

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


async def _search_checks(
    itinerary: Itinerary,
    *,
    clients: AppClients,
    places_by_id: dict[str, Place],
    place_ids: list[str],
    include_destination: bool,
) -> list[_SearchCheck]:
    queries: list[tuple[str, str | None]] = []
    if include_destination:
        queries.append(
            (
                f"{itinerary.destination} travel closures strikes protests warnings",
                None,
            )
        )

    allowed_ids = set(place_ids)
    seen_places: set[str] = set()
    for day in itinerary.days:
        for item in day.items:
            if (
                item.place_id is None
                or item.place_id not in allowed_ids
                or item.place_id in seen_places
            ):
                continue
            place = places_by_id.get(item.place_id)
            if place is None or not _is_high_risk_place(place):
                continue
            seen_places.add(item.place_id)
            queries.append(
                (
                    f"{place.name} {itinerary.destination} closure strike warning",
                    item.id,
                )
            )
            if len(seen_places) >= 5:
                break
        if len(seen_places) >= 5:
            break

    results = await asyncio.gather(
        *(
            clients.search.search(
                query,
                time_range="month",
                max_results=5 if item_id is None else 3,
            )
            for query, item_id in queries
        )
    )
    return [
        _SearchCheck(result=result, item_id=item_id)
        for (_, item_id), result in zip(queries, results, strict=True)
    ]


def _is_high_risk_place(place: Place) -> bool:
    place_types = set(place.types)
    if place.primary_type:
        place_types.add(place.primary_type)
    return bool(place_types & _HIGH_RISK_PLACE_TYPES) or any(
        term in place.name.lower() for term in _HIGH_RISK_NAME_TERMS
    )


def _search_warnings(checks: list[_SearchCheck]) -> list[Warning]:
    risk_terms = ("closed", "closure", "strike", "protest", "warning")
    warnings: list[Warning] = []
    for check in checks:
        if check.result.status != "available":
            continue
        for result in check.result.results:
            text = f"{result.title} {result.content}".lower()
            if any(term in text for term in risk_terms):
                warnings.append(
                    Warning(
                        level="caution",
                        code="recent_travel_notice",
                        message=result.title,
                        source="tavily",
                        item_id=check.item_id,
                        source_url=result.url,
                    )
                )
    return warnings


def _weather_warnings(weather: WeatherResult) -> list[Warning]:
    if weather.status == "available":
        return []
    return [
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
    ]


def _place_warnings(
    visit_date: date,
    item: Item,
    place: Place,
) -> tuple[list[Warning], bool]:
    warnings: list[Warning] = []
    complete = True
    if place.business_status != "OPERATIONAL":
        complete = False
        warnings.append(
            Warning(
                level="caution",
                code="business_status_unknown",
                message=f"The operating status of {item.title} is unknown.",
                source="google_places",
                item_id=item.id,
            )
        )

    opening_status = _opening_status(
        visit_date,
        item.start_time,
        item.end_time,
        place.opening_hours,
    )
    if opening_status == "unknown":
        complete = False
        warnings.append(
            Warning(
                level="caution",
                code="opening_hours_unknown",
                message=f"Opening hours for {item.title} could not be confirmed.",
                source="google_places",
                item_id=item.id,
            )
        )
    elif opening_status == "closed_day":
        warnings.append(
            Warning(
                level="caution",
                code="place_closed_on_visit_day",
                message=f"{item.title} appears closed on the planned visit day.",
                source="google_places",
                item_id=item.id,
            )
        )
    elif opening_status == "outside":
        warnings.append(
            Warning(
                level="caution",
                code="outside_opening_hours",
                message=f"The planned time for {item.title} is outside listed hours.",
                source="google_places",
                item_id=item.id,
            )
        )
    return warnings, complete


def _opening_status(
    visit_date: date,
    start_time: time,
    end_time: time,
    opening_hours: PlaceOpeningHours | None,
) -> Literal["inside", "closed_day", "outside", "unknown"]:
    if opening_hours is None or not opening_hours.periods:
        return "unknown"

    google_day = (visit_date.weekday() + 1) % 7
    visit_start = google_day * 24 * 60 + start_time.hour * 60 + start_time.minute
    visit_end = google_day * 24 * 60 + end_time.hour * 60 + end_time.minute
    day_start = google_day * 24 * 60
    day_end = day_start + 24 * 60
    has_hours_on_day = False

    for period in opening_hours.periods:
        opens = period.opens_at
        open_minute = opens.day * 24 * 60 + opens.hour * 60 + opens.minute
        if period.closes_at is None:
            return "inside"
        closes = period.closes_at
        close_minute = closes.day * 24 * 60 + closes.hour * 60 + closes.minute
        if close_minute <= open_minute:
            close_minute += _WEEK_MINUTES

        for shift in (-_WEEK_MINUTES, 0, _WEEK_MINUTES):
            shifted_open = open_minute + shift
            shifted_close = close_minute + shift
            if shifted_open < day_end and shifted_close > day_start:
                has_hours_on_day = True
            if shifted_open <= visit_start and visit_end <= shifted_close:
                return "inside"

    return "outside" if has_hours_on_day else "closed_day"


def _is_outdoor(item: Item) -> bool:
    text = f"{item.title} {item.description}".lower()
    if any(term in text for term in _OUTDOOR_TERMS):
        return True
    if item.place is None:
        return False
    place_types = set(item.place.types)
    if item.place.primary_type:
        place_types.add(item.place.primary_type)
    return bool(place_types & _OUTDOOR_PLACE_TYPES)


def _outdoor_weather_warning(
    item: Item,
    weather: DailyWeather,
) -> Warning | None:
    risky = (
        weather.weather_code in _SEVERE_WEATHER_CODES
        or (weather.precipitation_probability_max or 0) >= 70
        or (weather.precipitation_sum_mm or 0) >= 10
        or (weather.wind_speed_max_kmh or 0) >= 40
        or (
            weather.temperature_max_c is not None
            and weather.temperature_max_c >= 35
        )
        or (
            weather.temperature_min_c is not None
            and weather.temperature_min_c <= 0
        )
    )
    if not risky:
        return None
    return Warning(
        level="caution",
        code="outdoor_weather_risk",
        message=f"Weather may affect {item.title}: {weather.summary}.",
        source="open_meteo",
        item_id=item.id,
    )


def known_places(itinerary: Itinerary) -> dict[str, Place]:
    return {
        item.place_id: item.place
        for day in itinerary.days
        for item in day.items
        if item.place_id is not None and item.place is not None
    }

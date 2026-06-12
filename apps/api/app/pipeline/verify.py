from __future__ import annotations

from datetime import date

from app.deps import Deps
from app.schemas import (
    BusinessStatus,
    GeoPoint,
    Itinerary,
    ItineraryItem,
    Warning,
    WarningSeverity,
)

# Web search is the main variable cost, so cap how many venue-level freshness
# checks we run per itinerary. Closed/uncertain venues are prioritised.
_MAX_VENUE_SEARCHES = 8

# Keywords that suggest an outdoor activity sensitive to heavy rain.
_OUTDOOR_HINTS = ("park", "garden", "hike", "beach", "outdoor", "walk", "market", "tour")


async def verify_itinerary(
    itinerary: Itinerary, deps: Deps, *, location: GeoPoint | None = None
) -> Itinerary:
    """Re-check a draft itinerary against live reality for each visit date.

    Mutates items in place with refreshed `business_status`, backfilled
    contact/location data, and per-item warnings; attaches weather to each day;
    and aggregates destination-level disruption warnings at the trip level.
    """
    location = location or await _geocode(itinerary.destination, deps)

    weather_by_date: dict = {}
    if location is not None and deps.weather.is_configured():
        try:
            weather_by_date = await deps.weather.forecast(
                location, itinerary.start_date, itinerary.end_date
            )
        except Exception:  # noqa: BLE001 - weather is best-effort
            weather_by_date = {}

    trip_warnings: list[Warning] = []
    if deps.web_search.is_configured():
        trip_warnings = await _destination_disruptions(itinerary, deps)

    # Verify venues, prioritising those most likely to be a problem.
    items_with_place = [
        (day_idx, item_idx, item)
        for day_idx, day in enumerate(itinerary.days)
        for item_idx, item in enumerate(day.items)
        if item.place_id
    ]
    venue_search_budget = _MAX_VENUE_SEARCHES

    for day_idx, item_idx, item in items_with_place:
        spent = await _verify_item(item, itinerary.days[day_idx].date, deps, venue_search_budget)
        venue_search_budget -= spent

    for day in itinerary.days:
        day.weather = weather_by_date.get(day.date)
        if day.weather and day.weather.precipitation_mm and day.weather.precipitation_mm >= 10:
            for item in day.items:
                if _is_outdoor(item):
                    item.warnings.append(
                        Warning(
                            severity=WarningSeverity.INFO,
                            message=(
                                f"Heavy rain forecast ({day.weather.precipitation_mm:.0f}mm) "
                                f"on {day.date}; consider an indoor backup."
                            ),
                            source="open_meteo",
                            related_item=item.name,
                        )
                    )

    itinerary.warnings = trip_warnings + itinerary.warnings
    return itinerary


async def _verify_item(
    item: ItineraryItem, visit_date: str, deps: Deps, venue_search_budget: int
) -> int:
    """Verify a single venue. Returns the number of web searches consumed."""
    searches_used = 0
    if not item.place_id or not deps.places.is_configured():
        return searches_used

    try:
        place = await deps.places.get_details(item.place_id)
    except Exception:  # noqa: BLE001 - a single venue failing must not abort the trip
        place = None

    if place is None:
        return searches_used

    # Backfill verified contact/location data from Places.
    item.business_status = place.business_status
    item.location = item.location or place.location
    item.address = item.address or place.address
    item.website = item.website or place.website
    if not item.reservation_url and place.website:
        item.reservation_url = place.website

    if place.business_status is BusinessStatus.CLOSED_PERMANENTLY:
        item.warnings.append(
            Warning(
                severity=WarningSeverity.BLOCKER,
                message=f"{place.name} is permanently closed; it should be replaced.",
                source="google_places",
                related_item=item.name,
            )
        )
    elif place.business_status is BusinessStatus.CLOSED_TEMPORARILY:
        item.warnings.append(
            Warning(
                severity=WarningSeverity.BLOCKER,
                message=f"{place.name} is temporarily closed; verify before visiting.",
                source="google_places",
                related_item=item.name,
            )
        )

    # Day-of-week opening check for the specific visit date.
    weekday = _weekday_name(visit_date)
    if weekday and place.opening_hours:
        hours = place.opening_hours.get(weekday, "")
        if "closed" in hours.lower():
            item.warnings.append(
                Warning(
                    severity=WarningSeverity.CAUTION,
                    message=f"{place.name} is usually closed on {weekday} ({visit_date}).",
                    source="google_places",
                    related_item=item.name,
                )
            )

    # Targeted same-day freshness search for higher-risk venues, within budget.
    needs_search = place.business_status in (
        BusinessStatus.CLOSED_TEMPORARILY,
        BusinessStatus.UNKNOWN,
    ) or _is_attraction(place.types)
    if needs_search and venue_search_budget > 0 and deps.web_search.is_configured():
        searches_used = 1
        try:
            results = await deps.web_search.search(
                f'"{place.name}" closed OR closure {visit_date}',
                max_results=3,
                recency_days=30,
            )
        except Exception:  # noqa: BLE001
            results = []
        for r in results:
            text = f"{r.title} {r.content}".lower()
            if "closed" in text or "closure" in text or "strike" in text:
                item.warnings.append(
                    Warning(
                        severity=WarningSeverity.CAUTION,
                        message=f"Possible disruption reported: {r.title}",
                        source=r.url,
                        related_item=item.name,
                    )
                )
                break

    return searches_used


async def _destination_disruptions(itinerary: Itinerary, deps: Deps) -> list[Warning]:
    query = (
        f"{itinerary.destination} travel disruption strike OR closure OR protest "
        f"{itinerary.start_date} to {itinerary.end_date}"
    )
    try:
        results = await deps.web_search.search(query, max_results=4, recency_days=14)
    except Exception:  # noqa: BLE001
        return []

    warnings: list[Warning] = []
    for r in results:
        text = f"{r.title} {r.content}".lower()
        if any(k in text for k in ("strike", "closure", "closed", "protest", "advisory")):
            warnings.append(
                Warning(
                    severity=WarningSeverity.CAUTION,
                    message=r.title,
                    source=r.url,
                )
            )
    return warnings


async def _geocode(destination: str, deps: Deps) -> GeoPoint | None:
    if not deps.places.is_configured():
        return None
    try:
        places = await deps.places.text_search(destination, max_results=1)
    except Exception:  # noqa: BLE001
        return None
    return places[0].location if places else None


def _weekday_name(iso_date: str) -> str | None:
    try:
        return date.fromisoformat(iso_date).strftime("%A")
    except ValueError:
        return None


def _is_attraction(types: list[str]) -> bool:
    return any(
        t in types
        for t in ("museum", "tourist_attraction", "art_gallery", "amusement_park", "zoo")
    )


def _is_outdoor(item: ItineraryItem) -> bool:
    haystack = f"{item.name} {item.category or ''} {item.description or ''}".lower()
    return any(h in haystack for h in _OUTDOOR_HINTS)

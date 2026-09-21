from __future__ import annotations

from datetime import date, time, timedelta
from types import SimpleNamespace

import pytest

from app.external.places import (
    Place,
    PlaceCoordinate,
    PlaceDetailsResult,
    PlaceOpeningHours,
    PlaceOpeningPeriod,
    PlaceOpeningTime,
)
from app.external.search import SearchItem, SearchResult
from app.external.weather import DailyWeather, WeatherResult
from app.schemas import Day, Item, Itinerary
from app.verification import verify_itinerary


@pytest.fixture(autouse=True)
def clean_test_database() -> None:
    """Override the integration fixture: these tests do not access the database."""


class _Places:
    def __init__(self, places: list[Place]) -> None:
        self._places = {place.place_id: place for place in places}

    async def details(self, place_id: str) -> PlaceDetailsResult:
        place = self._places.get(place_id)
        return PlaceDetailsResult(
            status="available" if place is not None else "not_found",
            place=place,
        )


class _Weather:
    def __init__(self, result: WeatherResult) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    async def forecast(self, **kwargs: object) -> WeatherResult:
        self.calls.append(kwargs)
        if self.result.status != "available" or not self.result.days:
            return self.result
        start_date = kwargs["start_date"]
        end_date = kwargs["end_date"]
        assert isinstance(start_date, date)
        assert isinstance(end_date, date)
        template = self.result.days[0]
        return self.result.model_copy(
            update={
                "days": [
                    template.model_copy(update={"date": start_date + timedelta(days=index)})
                    for index in range((end_date - start_date).days + 1)
                ]
            }
        )


class _Search:
    def __init__(self, result: SearchResult) -> None:
        self.result = result
        self.queries: list[str] = []

    async def search(self, query: str, **_kwargs: object) -> SearchResult:
        self.queries.append(query)
        return self.result


def _clients(
    places: list[Place],
    *,
    weather: WeatherResult | None = None,
    search: SearchResult | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        places=_Places(places),
        weather=_Weather(weather or WeatherResult(status="available", days=[])),
        search=_Search(search or SearchResult(status="available", results=[])),
    )


def _hours(
    *,
    day: int,
    opens: int = 9,
    closes: int = 17,
) -> PlaceOpeningHours:
    return PlaceOpeningHours(
        periods=[
            PlaceOpeningPeriod(
                opens_at=PlaceOpeningTime(day=day, hour=opens, minute=0),
                closes_at=PlaceOpeningTime(day=day, hour=closes, minute=0),
            )
        ],
        weekday_descriptions=[],
    )


def _place(
    place_id: str,
    *,
    opening_hours: PlaceOpeningHours | None,
    status: str | None = "OPERATIONAL",
    types: list[str] | None = None,
) -> Place:
    return Place(
        place_id=place_id,
        name=place_id.replace("-", " ").title(),
        location=PlaceCoordinate(latitude=35.68, longitude=139.76),
        types=types or ["restaurant"],
        business_status=status,
        opening_hours=opening_hours,
    )


def _item(
    place_id: str,
    *,
    start: int = 10,
    end: int = 11,
) -> Item:
    return Item(
        id=f"item-{place_id}",
        start_time=time(start),
        end_time=time(end),
        title=place_id.replace("-", " ").title(),
        kind="place",
        place_id=place_id,
    )


def _itinerary(
    items: list[Item],
    *,
    with_coordinates: bool = True,
) -> Itinerary:
    return Itinerary(
        destination="Tokyo",
        destination_location=(
            PlaceCoordinate(latitude=35.6762, longitude=139.6503)
            if with_coordinates
            else None
        ),
        start_date=date(2026, 9, 21),
        end_date=date(2026, 9, 21),
        days=[
            Day(
                date=date(2026, 9, 21),
                city="Tokyo",
                country="Japan",
                location=(
                    PlaceCoordinate(latitude=35.6762, longitude=139.6503)
                    if with_coordinates
                    else None
                ),
                title="Tokyo",
                items=items,
            )
        ],
    )


def _weather_day(*, severe: bool = False) -> DailyWeather:
    return DailyWeather(
        date=date(2026, 9, 21),
        weather_code=65 if severe else 1,
        summary="Heavy rain" if severe else "Mainly clear",
        temperature_max_c=25,
        temperature_min_c=18,
        precipitation_probability_max=90 if severe else 10,
        precipitation_sum_mm=15 if severe else 0,
        wind_speed_max_kmh=20,
    )


async def test_place_schedule_boundaries_and_unknown_hours() -> None:
    places = [
        _place("closed-monday", opening_hours=_hours(day=2)),
        _place("outside-hours", opening_hours=_hours(day=1)),
        _place("unknown-hours", opening_hours=None),
    ]
    result = await verify_itinerary(
        _itinerary(
            [
                _item("closed-monday"),
                _item("outside-hours", start=18, end=19),
                _item("unknown-hours"),
            ]
        ),
        clients=_clients(places),
        places_available=True,
    )

    warning_codes = {
        item.place_id: {warning.code for warning in item.warnings}
        for item in result.itinerary.days[0].items
    }
    assert warning_codes["closed-monday"] == {"place_closed_on_visit_day"}
    assert warning_codes["outside-hours"] == {"outside_opening_hours"}
    assert warning_codes["unknown-hours"] == {"opening_hours_unknown"}
    assert result.itinerary.verification_status == "partial"
    assert "google_places" in result.itinerary.unavailable_sources


async def test_closed_place_blocks_but_search_summary_is_only_caution() -> None:
    places = [
        _place(
            "closed-place",
            opening_hours=_hours(day=1),
            status="CLOSED_PERMANENTLY",
        ),
        _place(
            "open-museum",
            opening_hours=_hours(day=1),
            types=["museum"],
        ),
    ]
    search = SearchResult(
        status="available",
        results=[
            SearchItem(
                title="Museum closure reported",
                url="https://example.com/notice",
                content="Check the latest notice before visiting.",
            )
        ],
    )
    result = await verify_itinerary(
        _itinerary(
            [_item("closed-place"), _item("open-museum", start=12, end=13)]
        ),
        clients=_clients(places, search=search),
        places_available=True,
    )

    assert result.blocker_place_ids == {"closed-place"}
    assert all(warning.level == "caution" for warning in result.itinerary.warnings)
    assert any(
        warning.code == "recent_travel_notice"
        for warning in result.itinerary.warnings
    )
    assert all(
        warning.level != "blocker"
        for warning in result.itinerary.days[0].items[1].warnings
    )


async def test_adverse_weather_warns_for_outdoor_activity() -> None:
    park = _place(
        "city-park",
        opening_hours=_hours(day=1, opens=6, closes=22),
        types=["park"],
    )
    result = await verify_itinerary(
        _itinerary([_item("city-park")]),
        clients=_clients(
            [park],
            weather=WeatherResult(
                status="available",
                days=[_weather_day(severe=True)],
            ),
        ),
        places_available=True,
    )

    item = result.itinerary.days[0].items[0]
    assert {warning.code for warning in item.warnings} == {"outdoor_weather_risk"}
    assert result.itinerary.days[0].weather is not None
    assert result.itinerary.days[0].weather.summary == "Heavy rain"
    assert result.itinerary.verification_status == "verified"


@pytest.mark.parametrize(
    (
        "places_available",
        "with_coordinates",
        "weather",
        "search",
        "status",
        "verified",
        "unavailable",
    ),
    [
        (
            True,
            True,
            WeatherResult(status="available", days=[_weather_day()]),
            SearchResult(status="available", results=[]),
            "verified",
            {"google_places", "open_meteo", "tavily"},
            set(),
        ),
        (
            True,
            True,
            WeatherResult(
                status="not_available_for_date",
                unavailable_reason="date_outside_forecast_range",
            ),
            SearchResult(status="available", results=[]),
            "partial",
            {"google_places", "tavily"},
            {"open_meteo"},
        ),
        (
            False,
            False,
            WeatherResult(status="available", days=[_weather_day()]),
            SearchResult(status="unavailable", unavailable_reason="not_configured"),
            "unavailable",
            set(),
            {"google_places", "open_meteo", "tavily"},
        ),
    ],
)
async def test_verification_status_matches_source_results(
    places_available: bool,
    with_coordinates: bool,
    weather: WeatherResult,
    search: SearchResult,
    status: str,
    verified: set[str],
    unavailable: set[str],
) -> None:
    result = await verify_itinerary(
        _itinerary([], with_coordinates=with_coordinates),
        clients=_clients([], weather=weather, search=search),
        places_available=places_available,
    )

    assert result.itinerary.verification_status == status
    assert set(result.itinerary.verified_sources) == verified
    assert set(result.itinerary.unavailable_sources) == unavailable
    if "open_meteo" in unavailable:
        assert result.itinerary.days[0].weather is None
        assert any(
            warning.code == "weather_not_available"
            for warning in result.itinerary.warnings
        )


async def test_weather_is_saved_on_each_overnight_city() -> None:
    tokyo = PlaceCoordinate(latitude=35.6762, longitude=139.6503)
    kyoto = PlaceCoordinate(latitude=35.0116, longitude=135.7681)
    itinerary = Itinerary(
        destination="Tokyo and Kyoto",
        start_date=date(2026, 9, 21),
        end_date=date(2026, 9, 22),
        days=[
            Day(
                date=date(2026, 9, 21),
                city="Tokyo",
                country="Japan",
                location=tokyo,
                title="Tokyo",
            ),
            Day(
                date=date(2026, 9, 22),
                city="Kyoto",
                country="Japan",
                location=kyoto,
                title="Kyoto",
                intercity_transport="Tokyo to Kyoto by train",
            ),
        ],
    )
    clients = _clients(
        [],
        weather=WeatherResult(status="available", days=[_weather_day()]),
    )

    result = await verify_itinerary(
        itinerary,
        clients=clients,
        places_available=True,
    )

    assert [day.weather.summary if day.weather else None for day in result.itinerary.days] == [
        "Mainly clear",
        "Mainly clear",
    ]
    assert len(clients.weather.calls) == 2

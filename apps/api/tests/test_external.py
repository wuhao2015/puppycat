import json
from datetime import datetime, timedelta, timezone

import httpx

from app.external.places import PlacesClient
from app.external.search import SearchClient
from app.external.weather import WeatherClient


async def test_places_search_and_details_are_normalized_and_cached() -> None:
    calls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        assert request.headers["X-Goog-Api-Key"] == "test-places-key"
        if request.url.path.endswith("places:searchText"):
            assert json.loads(request.content) == {
                "textQuery": "gardens in Kyoto",
                "pageSize": 3,
                "languageCode": "en",
                "regionCode": "JP",
            }
            return httpx.Response(
                200,
                json={
                    "places": [
                        {
                            "id": "kyoto-garden",
                            "displayName": {"text": "Kyoto Garden"},
                            "formattedAddress": "Kyoto, Japan",
                            "location": {
                                "latitude": 35.0116,
                                "longitude": 135.7681,
                            },
                            "types": ["park", "tourist_attraction"],
                            "primaryType": "park",
                            "addressComponents": [
                                {
                                    "shortText": "JP",
                                    "longText": "Japan",
                                    "types": ["country"],
                                }
                            ],
                            "businessStatus": "OPERATIONAL",
                            "googleMapsUri": "https://maps.google.test/garden",
                        }
                    ]
                },
            )

        assert request.url.path.endswith("/places/kyoto-garden")
        return httpx.Response(
            200,
            json={
                "id": "kyoto-garden",
                "displayName": {"text": "Kyoto Garden"},
                "formattedAddress": "Kyoto, Japan",
                "location": {"latitude": 35.0116, "longitude": 135.7681},
                "addressComponents": [
                    {
                        "shortText": "JP",
                        "longText": "Japan",
                        "types": ["country"],
                    }
                ],
                "websiteUri": "https://garden.example",
                "regularOpeningHours": {
                    "periods": [
                        {
                            "open": {"day": 1, "hour": 9},
                            "close": {"day": 1, "hour": 17},
                        }
                    ],
                    "weekdayDescriptions": ["Monday: 9:00 AM–5:00 PM"],
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        places = PlacesClient(http, api_key="test-places-key")
        first_search = await places.search_text(
            " gardens in Kyoto ",
            max_results=3,
            language_code="en",
            region_code="jp",
        )
        cached_search = await places.search_text(
            "gardens in Kyoto",
            max_results=3,
            language_code="en",
            region_code="JP",
        )
        first_details = await places.details("kyoto-garden")
        cached_details = await places.details("kyoto-garden")

    assert first_search == cached_search
    assert first_search.status == "available"
    assert first_search.places[0].country_code == "JP"
    assert first_search.places[0].country_name == "Japan"
    assert first_search.places[0].location is not None
    assert first_search.places[0].location.latitude == 35.0116

    assert first_details == cached_details
    assert first_details.status == "available"
    assert first_details.place is not None
    assert first_details.place.website_uri == "https://garden.example"
    assert first_details.place.opening_hours is not None
    period = first_details.place.opening_hours.periods[0]
    assert (period.opens_at.day, period.opens_at.hour, period.opens_at.minute) == (
        1,
        9,
        0,
    )
    assert calls == ["/v1/places:searchText", "/v1/places/kyoto-garden"]


async def test_weather_forecast_maps_wmo_and_uses_cache() -> None:
    today = datetime.now(timezone.utc).date()
    tomorrow = today + timedelta(days=1)
    request_count = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        assert request.url.params["start_date"] == today.isoformat()
        assert request.url.params["end_date"] == tomorrow.isoformat()
        return httpx.Response(
            200,
            json={
                "latitude": 40.71,
                "longitude": -74.01,
                "timezone": "America/New_York",
                "daily": {
                    "time": [today.isoformat(), tomorrow.isoformat()],
                    "weather_code": [0, 61],
                    "temperature_2m_max": [22.0, 20.5],
                    "temperature_2m_min": [14.0, 13.5],
                    "precipitation_probability_max": [5, 70],
                    "precipitation_sum": [0.0, 4.2],
                    "wind_speed_10m_max": [12.0, 18.0],
                },
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        weather = WeatherClient(http)
        first = await weather.forecast(
            latitude=40.7128,
            longitude=-74.006,
            start_date=today,
            end_date=tomorrow,
        )
        cached = await weather.forecast(
            latitude=40.7128,
            longitude=-74.006,
            start_date=today,
            end_date=tomorrow,
        )
        outside_range = await weather.forecast(
            latitude=40.7128,
            longitude=-74.006,
            start_date=today + timedelta(days=16),
            end_date=today + timedelta(days=16),
        )

    assert first == cached
    assert [day.summary for day in first.days] == ["Clear sky", "Slight rain"]
    assert request_count == 1
    assert outside_range.status == "not_available_for_date"
    assert outside_range.unavailable_reason == "date_outside_forecast_range"


async def test_tavily_search_is_normalized_and_cached() -> None:
    request_count = 0

    def handle(request: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        assert request.headers["Authorization"] == "Bearer test-tavily-key"
        body = json.loads(request.content)
        assert body["search_depth"] == "basic"
        assert body["include_answer"] is False
        assert body["include_raw_content"] is False
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Official travel notice",
                        "url": "https://example.gov/notice",
                        "content": "A scheduled closure was announced.",
                        "score": 0.91,
                        "published_date": "2026-09-16",
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        search = SearchClient(http, api_key="test-tavily-key")
        first = await search.search(
            "New York travel closures",
            topic="news",
            time_range="week",
            include_domains=["EXAMPLE.GOV"],
        )
        cached = await search.search(
            "New York travel closures",
            topic="news",
            time_range="week",
            include_domains=["example.gov"],
        )

    assert first == cached
    assert first.status == "available"
    assert first.results[0].title == "Official travel notice"
    assert request_count == 1


async def test_external_http_failures_return_unavailable_results() -> None:
    today = datetime.now(timezone.utc).date()

    def unavailable(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"error": "upstream details stay private"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(unavailable)
    ) as http:
        places_result = await PlacesClient(
            http,
            api_key="failed-places-key",
        ).search_text("failure-only place query")
        search_result = await SearchClient(
            http,
            api_key="failed-tavily-key",
        ).search("failure-only web query")
        weather_result = await WeatherClient(http).forecast(
            latitude=51.5072,
            longitude=-0.1276,
            start_date=today,
            end_date=today,
        )

    assert places_result.status == "unavailable"
    assert places_result.unavailable_reason == "request_failed"
    assert search_result.status == "unavailable"
    assert search_result.unavailable_reason == "request_failed"
    assert weather_result.status == "unavailable"
    assert weather_result.unavailable_reason == "request_failed"

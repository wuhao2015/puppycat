from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from httpx import AsyncClient
from pydantic import BaseModel
from sqlalchemy import func, select

from app.db import SessionLocal
from app.external.places import (
    Place,
    PlaceCoordinate,
    PlaceDetailsResult,
    PlacesSearchResult,
)
from app.external.search import SearchResult
from app.external.weather import WeatherResult
from app.gemini import GeminiMessage
from app.main import app
from app.models import Itinerary as ItineraryRecord
from app.models import Trip
from app.schemas import Day, Item, Itinerary, TripRequest


class _FakeGemini:
    def __init__(self, responses: Sequence[BaseModel | Exception]) -> None:
        self.responses = list(responses)
        self.calls: list[tuple[list[GeminiMessage], type[BaseModel]]] = []

    async def complete_json(
        self,
        messages: Sequence[GeminiMessage],
        response_schema: type[BaseModel],
    ) -> BaseModel:
        self.calls.append((list(messages), response_schema))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response_schema.model_validate(response)


class _FakePlaces:
    def __init__(
        self,
        candidates: list[Place],
        details: dict[str, PlaceDetailsResult],
        *,
        require_concurrent_search: bool = False,
    ) -> None:
        self.candidates = candidates
        self.detail_results = details
        self.detail_calls: list[str] = []
        self.require_concurrent_search = require_concurrent_search
        self.concurrent_search_observed = False
        self._search_count = 0
        self._both_searches_started = asyncio.Event()

    async def search_text(
        self, query: str, *, max_results: int = 10
    ) -> PlacesSearchResult:
        if self.require_concurrent_search:
            self._search_count += 1
            if self._search_count == 2:
                self.concurrent_search_observed = True
                self._both_searches_started.set()
            await asyncio.wait_for(self._both_searches_started.wait(), timeout=1)
        if max_results == 1:
            return PlacesSearchResult(status="available", places=[_destination()])
        return PlacesSearchResult(status="available", places=self.candidates)

    async def details(self, place_id: str) -> PlaceDetailsResult:
        self.detail_calls.append(place_id)
        return self.detail_results[place_id]


class _FakeWeather:
    async def forecast(self, **_kwargs: object) -> WeatherResult:
        return WeatherResult(status="available", days=[])


class _FakeSearch:
    async def search(self, _query: str, **_kwargs: object) -> SearchResult:
        return SearchResult(status="available", results=[])


async def _register(client: AsyncClient, prefix: str = "planner") -> dict[str, str]:
    response = await client.post(
        "/api/auth/register",
        json={
            "email": f"{prefix}-{uuid4()}@example.com",
            "password": "correct-horse-battery-staple",
            "signup_code": "test-signup-code",
        },
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _trip_with_message(client: AsyncClient, headers: dict[str, str]) -> str:
    trip = (await client.post("/api/trips", headers=headers)).json()
    await _append_user_message(
        trip["id"],
        "Tokyo from 2026-09-20 to 2026-09-20, relaxed pace and gardens.",
    )
    return trip["id"]


async def _append_user_message(trip_id: str, content: str) -> None:
    async with SessionLocal() as session:
        trip = await session.get(Trip, trip_id)
        assert trip is not None
        trip.chat_messages = [
            *(trip.chat_messages or []),
            {
                "role": "user",
                "content": content,
                "ts": datetime.now(timezone.utc).isoformat(),
            },
        ]
        await session.commit()


def _destination() -> Place:
    return Place(
        place_id="tokyo",
        name="Tokyo",
        location=PlaceCoordinate(latitude=35.6762, longitude=139.6503),
        business_status="OPERATIONAL",
    )


def _place(place_id: str, *, status: str = "OPERATIONAL") -> Place:
    return Place(
        place_id=place_id,
        name=place_id.replace("-", " ").title(),
        location=PlaceCoordinate(latitude=35.68, longitude=139.76),
        business_status=status,
        google_maps_uri=f"https://maps.example/{place_id}",
    )


def _request(*, destination: str | None = "Tokyo") -> TripRequest:
    return TripRequest(
        destination=destination,
        start_date="2026-09-20",
        end_date="2026-09-20",
        interests=["gardens"],
        pace="relaxed",
    )


def _itinerary(*place_ids: str) -> Itinerary:
    return Itinerary(
        destination="Tokyo",
        start_date="2026-09-20",
        end_date="2026-09-20",
        days=[
            Day(
                date="2026-09-20",
                title="Tokyo highlights",
                items=[
                    Item(
                        id=f"item-{index}",
                        start_time=time(9 + index * 2),
                        end_time=time(10 + index * 2),
                        title=place_id,
                        kind="place",
                        place_id=place_id,
                    )
                    for index, place_id in enumerate(place_ids)
                ],
            )
        ],
    )


def _install_clients(
    monkeypatch: pytest.MonkeyPatch,
    gemini: _FakeGemini,
    places: _FakePlaces,
) -> None:
    monkeypatch.setattr(
        app.state,
        "clients",
        SimpleNamespace(
            gemini=gemini,
            places=places,
            weather=_FakeWeather(),
            search=_FakeSearch(),
        ),
        raising=False,
    )


async def _itinerary_count(trip_id: str) -> int:
    async with SessionLocal() as session:
        count = await session.scalar(
            select(func.count())
            .select_from(ItineraryRecord)
            .where(ItineraryRecord.trip_id == trip_id)
        )
    return count or 0


async def test_first_plan_runs_searches_concurrently_and_is_owner_scoped(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await _register(client, "plan-owner")
    other = await _register(client, "plan-other")
    trip_id = await _trip_with_message(client, owner)
    garden = _place("garden")
    places = _FakePlaces(
        [garden],
        {"garden": PlaceDetailsResult(status="available", place=garden)},
        require_concurrent_search=True,
    )
    gemini = _FakeGemini([_request(), _itinerary("garden")])
    _install_clients(monkeypatch, gemini, places)

    forbidden = await client.post(f"/api/trips/{trip_id}/plan", headers=other)
    response = await client.post(f"/api/trips/{trip_id}/plan", headers=owner)

    assert forbidden.status_code == 404
    assert response.status_code == 200
    assert places.concurrent_search_observed
    assert response.json()["data"]["days"][0]["items"][0]["place"]["place_id"] == (
        "garden"
    )
    assert await _itinerary_count(trip_id) == 1
    detail = (await client.get(f"/api/trips/{trip_id}", headers=owner)).json()
    assert detail["destination"] == "Tokyo"
    assert detail["preferences"] == {
        "interests": ["gardens"],
        "pace": "relaxed",
    }
    assert "destination" not in detail["preferences"]
    assert detail["latest_itinerary"]["id"] == response.json()["id"]


async def test_invalid_requests_and_unknown_place_do_not_save_a_plan(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await _register(client)
    trip_id = await _trip_with_message(client, owner)
    garden = _place("garden")
    places = _FakePlaces(
        [garden],
        {"garden": PlaceDetailsResult(status="available", place=garden)},
    )

    _install_clients(monkeypatch, _FakeGemini([_request(destination=None)]), places)
    missing = await client.post(f"/api/trips/{trip_id}/plan", headers=owner)
    assert missing.status_code == 422
    assert missing.json()["detail"]["missing_fields"] == ["destination"]

    invalid_request = _request().model_copy(
        update={"start_date": datetime(2026, 9, 21).date(), "end_date": datetime(2026, 9, 20).date()}
    )
    _install_clients(monkeypatch, _FakeGemini([invalid_request]), places)
    invalid = await client.post(f"/api/trips/{trip_id}/plan", headers=owner)
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "invalid_trip_dates"

    _install_clients(
        monkeypatch,
        _FakeGemini([_request(), _itinerary("invented-place")]),
        places,
    )
    unknown = await client.post(f"/api/trips/{trip_id}/plan", headers=owner)
    assert unknown.status_code == 502
    assert unknown.json()["detail"]["code"] == "itinerary_generation_failed"
    assert await _itinerary_count(trip_id) == 0


async def test_blocker_is_replaced_once_and_only_replacement_is_reverified(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await _register(client)
    trip_id = await _trip_with_message(client, owner)
    closed = _place("closed-museum", status="CLOSED_PERMANENTLY")
    garden = _place("garden")
    places = _FakePlaces(
        [closed, garden],
        {
            "closed-museum": PlaceDetailsResult(status="available", place=closed),
            "garden": PlaceDetailsResult(status="available", place=garden),
        },
    )
    gemini = _FakeGemini(
        [_request(), _itinerary("closed-museum"), _itinerary("garden")]
    )
    _install_clients(monkeypatch, gemini, places)

    response = await client.post(f"/api/trips/{trip_id}/plan", headers=owner)

    assert response.status_code == 200
    assert places.detail_calls == ["closed-museum", "garden"]
    item = response.json()["data"]["days"][0]["items"][0]
    assert item["place_id"] == "garden"
    assert all(warning["level"] != "blocker" for warning in item["warnings"])


async def test_update_adds_a_version_reuses_places_and_failure_keeps_latest(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = await _register(client)
    trip_id = await _trip_with_message(client, owner)
    garden = _place("garden")
    market = _place("market")
    places = _FakePlaces(
        [garden, market],
        {
            "garden": PlaceDetailsResult(status="available", place=garden),
            "market": PlaceDetailsResult(status="available", place=market),
        },
    )
    first_gemini = _FakeGemini([_request(), _itinerary("garden")])
    _install_clients(monkeypatch, first_gemini, places)
    first = await client.post(f"/api/trips/{trip_id}/plan", headers=owner)
    assert first.status_code == 200

    await asyncio.sleep(0.01)
    await _append_user_message(trip_id, "Please add the market.")
    places.detail_calls.clear()
    update_gemini = _FakeGemini([_request(), _itinerary("garden", "market")])
    _install_clients(monkeypatch, update_gemini, places)
    updated = await client.post(f"/api/trips/{trip_id}/plan", headers=owner)

    assert updated.status_code == 200
    assert updated.json()["id"] != first.json()["id"]
    assert await _itinerary_count(trip_id) == 2
    assert places.detail_calls == ["market"]
    extraction_payload = json.loads(update_gemini.calls[0][0][1].content)
    assert [message["content"] for message in extraction_payload["conversation"]] == [
        "Please add the market."
    ]
    assert extraction_payload["previous_itinerary"]["days"][0]["items"][0][
        "place_id"
    ] == "garden"

    await asyncio.sleep(0.01)
    await _append_user_message(trip_id, "Replace it with somewhere quiet.")
    _install_clients(
        monkeypatch,
        _FakeGemini([_request(), _itinerary("not-a-candidate")]),
        places,
    )
    failed = await client.post(f"/api/trips/{trip_id}/plan", headers=owner)
    assert failed.status_code == 502
    assert await _itinerary_count(trip_id) == 2
    detail = (await client.get(f"/api/trips/{trip_id}", headers=owner)).json()
    assert detail["latest_itinerary"]["id"] == updated.json()["id"]

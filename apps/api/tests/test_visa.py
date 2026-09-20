from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from httpx import AsyncClient
from pydantic import BaseModel

from app.db import SessionLocal
from app.external.places import Place, PlacesSearchResult
from app.external.search import SearchItem, SearchResult
from app.gemini import GeminiMessage
from app.main import app
from app.models import Trip


OFFICIAL_URL = "https://www.mofa.go.jp/j_info/visit/visa/"


class _FakePlaces:
    async def search_text(
        self, query: str, *, max_results: int = 10
    ) -> PlacesSearchResult:
        assert query == "Kyoto, Japan"
        assert max_results == 1
        return PlacesSearchResult(
            status="available",
            places=[
                Place(
                    place_id="kyoto",
                    name="Kyoto",
                    address="Kyoto, Japan",
                    country_code="JP",
                )
            ],
        )


class _FakeSearch:
    def __init__(self, *, official: bool = True) -> None:
        self.official = official
        self.queries: list[str] = []
        self.call_options: list[dict[str, object]] = []

    async def search(self, query: str, **kwargs: object) -> SearchResult:
        self.queries.append(query)
        self.call_options.append(kwargs)
        url = OFFICIAL_URL if self.official else "https://travel-blog.example/visa"
        return SearchResult(
            status="available",
            results=[
                SearchItem(
                    title="Official visa guidance",
                    url=url,
                    content=(
                        "Official guidance covering visitor eligibility, documents, "
                        "application steps, processing time, and fees."
                    ),
                    published_date="2026-08-01",
                )
            ],
        )


class _FakeGemini:
    def __init__(self) -> None:
        self.contexts: list[dict[str, object]] = []

    async def complete_json(
        self,
        messages: Sequence[GeminiMessage],
        response_schema: type[BaseModel],
    ) -> BaseModel:
        context = json.loads(messages[-1].content)
        self.contexts.append(context)
        return response_schema.model_validate(
            {
                "visa_required": {"value": True, "source_url": OFFICIAL_URL},
                "visa_type": {
                    "value": "Temporary Visitor",
                    "source_url": OFFICIAL_URL,
                },
                "allowed_stay": {
                    "value": "Up to 90 days",
                    "source_url": OFFICIAL_URL,
                },
                "processing_time": {
                    "value": "About 5 days",
                    "source_url": OFFICIAL_URL,
                },
                "fees": {
                    "value": "A fee guessed from an unofficial site",
                    "source_url": "https://travel-blog.example/visa",
                },
                "notes": {
                    "value": "Apply before travel.",
                    "source_url": OFFICIAL_URL,
                },
                "materials": [
                    {
                        "name": "Passport",
                        "category": "required",
                        "source_url": OFFICIAL_URL,
                    },
                    {
                        "name": "Application form",
                        "category": "required",
                        "source_url": OFFICIAL_URL,
                    },
                    {
                        "name": "Travel itinerary",
                        "category": "required",
                        "source_url": OFFICIAL_URL,
                    },
                    {
                        "name": "Proof of funds",
                        "category": "conditional",
                        "source_url": OFFICIAL_URL,
                    },
                    {
                        "name": "Additional explanation",
                        "category": "optional",
                        "source_url": OFFICIAL_URL,
                    },
                ],
                "steps": [
                    {
                        "order": 1,
                        "title": "Prepare documents",
                        "description": "Collect the listed materials.",
                        "source_url": OFFICIAL_URL,
                    }
                ],
                "official_links": [
                    {"label": "Japan visa guidance", "url": OFFICIAL_URL}
                ],
            }
        )


class _GeminiMustNotRun:
    async def complete_json(self, *_args: object, **_kwargs: object) -> BaseModel:
        raise AssertionError("Gemini must not run without official sources")


async def _register(client: AsyncClient, prefix: str) -> dict[str, str]:
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


async def _create_ready_trip(client: AsyncClient, headers: dict[str, str]) -> str:
    response = await client.post("/api/trips", headers=headers)
    assert response.status_code == 201
    trip_id = response.json()["id"]
    async with SessionLocal() as session:
        trip = await session.get(Trip, trip_id)
        assert trip is not None
        trip.destination = "Kyoto, Japan"
        trip.start_date = date(2026, 10, 10)
        trip.end_date = date(2026, 10, 12)
        await session.commit()
    return trip_id


def _install_clients(
    monkeypatch: pytest.MonkeyPatch,
    *,
    search: _FakeSearch,
    gemini: object,
) -> None:
    monkeypatch.setattr(
        app.state,
        "clients",
        SimpleNamespace(
            places=_FakePlaces(),
            search=search,
            gemini=gemini,
        ),
        raising=False,
    )


async def test_visa_uses_country_duration_passports_and_keeps_all_materials(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = await _register(client, "visa-grounded")
    profile = await client.patch(
        "/api/auth/profile",
        headers=headers,
        json={"passport_countries": ["CN", "US"]},
    )
    assert profile.status_code == 200
    trip_id = await _create_ready_trip(client, headers)
    search = _FakeSearch()
    gemini = _FakeGemini()
    _install_clients(monkeypatch, search=search, gemini=gemini)

    response = await client.get(f"/api/trips/{trip_id}/visa", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["destination_country"] == "Japan"
    assert payload["destination_country_code"] == "JP"
    assert payload["stay_days"] == 3
    assert {item["passport_country"] for item in payload["checklists"]} == {
        "CN",
        "US",
    }
    assert all("stay 3 days" in query for query in search.queries)
    assert all("include_domains" not in options for options in search.call_options)
    assert {context["passport_country"] for context in gemini.contexts} == {
        "CN",
        "US",
    }
    assert all(
        context["destination_country"] == "Japan"
        for context in gemini.contexts
    )
    assert all(context["stay_days"] == 3 for context in gemini.contexts)

    checklist = payload["checklists"][0]
    assert checklist["fees"] is None
    assert checklist["processing_time"] == "About 5 days"
    assert len(checklist["materials"]) == 5
    assert {material["category"] for material in checklist["materials"]} == {
        "required",
        "optional",
        "conditional",
    }
    assert checklist["steps"]
    assert checklist["official_links"]
    assert checklist["sources"]
    assert "embassy or consulate" in checklist["disclaimer"]


async def test_visa_requires_a_saved_passport(
    client: AsyncClient,
) -> None:
    headers = await _register(client, "visa-passport")
    trip_id = await _create_ready_trip(client, headers)

    response = await client.get(f"/api/trips/{trip_id}/visa", headers=headers)

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "passport_countries_required"


async def test_visa_returns_unknown_without_official_sources(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = await _register(client, "visa-unknown")
    profile = await client.patch(
        "/api/auth/profile",
        headers=headers,
        json={"passport_countries": ["CN"]},
    )
    assert profile.status_code == 200
    trip_id = await _create_ready_trip(client, headers)
    _install_clients(
        monkeypatch,
        search=_FakeSearch(official=False),
        gemini=_GeminiMustNotRun(),
    )

    response = await client.get(f"/api/trips/{trip_id}/visa", headers=headers)

    assert response.status_code == 200
    checklist = response.json()["checklists"][0]
    assert checklist["status"] == "unavailable"
    assert checklist["visa_required"] is None
    assert checklist["visa_type"] is None
    assert checklist["allowed_stay"] is None
    assert checklist["processing_time"] is None
    assert checklist["fees"] is None
    assert checklist["materials"] == []
    assert checklist["steps"] == []

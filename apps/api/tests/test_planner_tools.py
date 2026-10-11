from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.external.places import (
    Place,
    PlaceCoordinate,
    PlaceDetailsResult,
    PlacesSearchResult,
)
from app.planner_tools import (
    PLANNER_TOOL_REGISTRY,
    GetPlaceDetailsOutput,
    PlannerToolArgumentsError,
    PlannerToolLimitError,
    PlannerToolLimits,
    PlannerToolPolicyError,
    PlannerToolbox,
    ResolveDestinationOutput,
    SearchPlacesOutput,
    UnknownPlannerToolError,
)


class _FakePlaces:
    def __init__(
        self,
        *,
        searches: list[PlacesSearchResult] | None = None,
        details: dict[str, PlaceDetailsResult] | None = None,
    ) -> None:
        self.search_results = list(searches or [])
        self.detail_results = details or {}
        self.search_calls: list[tuple[str, int]] = []
        self.detail_calls: list[str] = []

    async def search_text(
        self,
        query: str,
        *,
        max_results: int = 10,
    ) -> PlacesSearchResult:
        self.search_calls.append((query, max_results))
        return self.search_results.pop(0)

    async def details(self, place_id: str) -> PlaceDetailsResult:
        self.detail_calls.append(place_id)
        return self.detail_results[place_id]


def _place(
    place_id: str,
    name: str | None = None,
    *,
    country: str = "Japan",
) -> Place:
    return Place(
        place_id=place_id,
        name=name or place_id.replace("-", " ").title(),
        address=f"{name or place_id}, {country}",
        location=PlaceCoordinate(latitude=35.68, longitude=139.76),
        country_code="JP",
        country_name=country,
        business_status="OPERATIONAL",
    )


def _toolbox(
    places: _FakePlaces,
    *,
    destination_facts: list[str] | None = None,
    known_places: list[Place] | None = None,
    limits: PlannerToolLimits | None = None,
) -> PlannerToolbox:
    return PlannerToolbox(
        SimpleNamespace(places=places),
        destination_facts=destination_facts or ["Tokyo"],
        known_places=known_places,
        limits=limits,
    )


async def test_registry_and_arguments_reject_uncontrolled_calls() -> None:
    places = _FakePlaces()
    toolbox = _toolbox(places)

    assert set(PLANNER_TOOL_REGISTRY) == {
        "resolve_destination",
        "search_places",
        "get_place_details",
    }
    with pytest.raises(TypeError):
        PLANNER_TOOL_REGISTRY["arbitrary"] = object()  # type: ignore[index]

    with pytest.raises(UnknownPlannerToolError):
        await toolbox.execute("fetch_url", {"url": "https://example.com"})
    with pytest.raises(PlannerToolArgumentsError):
        await toolbox.execute(
            "resolve_destination",
            {"query": "Tokyo", "field_mask": "*"},
        )
    with pytest.raises(PlannerToolArgumentsError):
        await toolbox.execute(
            "resolve_destination",
            {"query": "https://example.com/Tokyo"},
        )
    with pytest.raises(PlannerToolPolicyError):
        await toolbox.execute("resolve_destination", {"query": "Osaka"})

    assert places.search_calls == []
    assert places.detail_calls == []
    assert toolbox.tool_call_count == 0


async def test_ambiguous_destination_is_bounded_and_cannot_be_searched() -> None:
    candidates = [
        _place("springfield-il", "Springfield"),
        _place("springfield-ma", "Springfield"),
        _place("springfield-mo", "Springfield"),
        _place("springfield-or", "Springfield"),
        _place("springfield-oh", "Springfield"),
        _place("springfield-il", "Duplicate Springfield"),
        _place("springfield-vt", "Springfield"),
    ]
    places = _FakePlaces(
        searches=[PlacesSearchResult(status="available", places=candidates)]
    )
    toolbox = _toolbox(places, destination_facts=["Springfield"])

    output = await toolbox.execute(
        "resolve_destination",
        {"query": "  Springfield  "},
    )

    assert isinstance(output, ResolveDestinationOutput)
    assert output.requires_clarification
    assert [place.place_id for place in output.candidates] == [
        "springfield-il",
        "springfield-ma",
        "springfield-mo",
        "springfield-or",
        "springfield-oh",
    ]
    assert places.search_calls == [("Springfield", 5)]

    with pytest.raises(PlannerToolPolicyError):
        await toolbox.execute(
            "search_places",
            {
                "area_place_id": "springfield-il",
                "category": "museum",
            },
        )
    assert len(places.search_calls) == 1


async def test_search_is_scoped_deduplicated_and_cached() -> None:
    tokyo = _place("tokyo", "Tokyo")
    museum = _place("museum", "Modern Art Museum")
    park = _place("park", "Art Park")
    places = _FakePlaces(
        searches=[
            PlacesSearchResult(status="available", places=[tokyo]),
            PlacesSearchResult(
                status="available",
                places=[museum, museum.model_copy(), park],
            ),
            PlacesSearchResult(status="available", places=[park]),
        ]
    )
    toolbox = _toolbox(places)
    await toolbox.execute("resolve_destination", {"query": "Tokyo"})

    arguments = {
        "area_place_id": "tokyo",
        "category": "museum",
        "query": "  modern art ",
        "max_results": 2,
    }
    first = await toolbox.execute("search_places", arguments)
    second = await toolbox.execute(
        "search_places",
        {**arguments, "query": "MODERN   ART", "max_results": 20},
    )
    changed = await toolbox.execute(
        "search_places",
        {**arguments, "query": "architecture", "max_results": 1},
    )

    assert isinstance(first, SearchPlacesOutput)
    assert first == second
    assert isinstance(changed, SearchPlacesOutput)
    assert [place.place_id for place in first.places] == ["museum", "park"]
    assert [place.place_id for place in changed.places] == ["park"]
    assert places.search_calls == [
        ("Tokyo", 5),
        ("modern art museum in Tokyo, Japan", 2),
        ("architecture museum in Tokyo, Japan", 1),
    ]
    assert toolbox.tool_call_count == 3
    assert toolbox.place_search_count == 3
    assert set(toolbox.discovered_places) == {"tokyo", "museum", "park"}

    with pytest.raises(PlannerToolArgumentsError):
        await toolbox.execute(
            "search_places",
            {
                "area_place_id": "tokyo",
                "category": "hotel",
            },
        )
    with pytest.raises(PlannerToolPolicyError):
        await toolbox.execute(
            "search_places",
            {
                "area_place_id": "invented-area",
                "category": "park",
            },
        )
    assert len(places.search_calls) == 3


async def test_details_only_accept_discovered_or_previous_places() -> None:
    previous = _place("previous", "Previous Place")
    detailed = previous.model_copy(
        update={"website_uri": "https://previous.example"},
    )
    places = _FakePlaces(
        details={
            "previous": PlaceDetailsResult(status="available", place=detailed),
        }
    )
    toolbox = _toolbox(places, known_places=[previous])

    with pytest.raises(PlannerToolPolicyError):
        await toolbox.execute(
            "get_place_details",
            {"place_id": "invented"},
        )
    with pytest.raises(PlannerToolArgumentsError):
        await toolbox.execute(
            "get_place_details",
            {"place_id": "https://example.com/place"},
        )

    first = await toolbox.execute(
        "get_place_details",
        {"place_id": "previous"},
    )
    second = await toolbox.execute(
        "get_place_details",
        {"place_id": " previous "},
    )

    assert isinstance(first, GetPlaceDetailsOutput)
    assert first == second
    assert first.place is not None
    assert first.place.website_uri == "https://previous.example"
    assert places.detail_calls == ["previous"]
    assert toolbox.tool_call_count == 1


async def test_tool_and_search_limits_apply_after_cached_results() -> None:
    tokyo = _place("tokyo", "Tokyo")
    other = _place("other", "Other Known Place")
    places = _FakePlaces(
        searches=[PlacesSearchResult(status="available", places=[tokyo])],
        details={
            "tokyo": PlaceDetailsResult(status="available", place=tokyo),
            "other": PlaceDetailsResult(status="available", place=other),
        },
    )
    toolbox = _toolbox(
        places,
        known_places=[other],
        limits=PlannerToolLimits(max_tool_calls=2, max_place_searches=1),
    )

    await toolbox.execute("resolve_destination", {"query": "Tokyo"})
    with pytest.raises(PlannerToolLimitError, match="search limit"):
        await toolbox.execute(
            "search_places",
            {"area_place_id": "tokyo", "category": "park"},
        )

    details = await toolbox.execute(
        "get_place_details",
        {"place_id": "tokyo"},
    )
    cached = await toolbox.execute(
        "get_place_details",
        {"place_id": "tokyo"},
    )
    assert details == cached
    assert toolbox.tool_call_count == 2
    assert places.detail_calls == ["tokyo"]

    with pytest.raises(PlannerToolLimitError, match="tool call limit"):
        await toolbox.execute(
            "get_place_details",
            {"place_id": "other"},
        )
    assert places.detail_calls == ["tokyo"]

from __future__ import annotations

from collections.abc import Sequence
from datetime import time
from types import SimpleNamespace

import pytest

from app.errors import AgentExecutionLimitError
from app.external.places import Place, PlaceCoordinate, PlacesSearchResult
from app.gemini import (
    GeminiFunctionCall,
    GeminiFunctionExchange,
    GeminiFunctionTurn,
    GeminiMessage,
)
from app.planner_agent import (
    MAX_AGENT_TURNS,
    MAX_FUNCTION_CALLS_PER_TURN,
    PlannerDraftEvaluation,
    run_planner_agent,
)
from app.schemas import Day, Itinerary, Item, TripRequest


class _FakeGemini:
    def __init__(self, turns: Sequence[GeminiFunctionTurn]) -> None:
        self.turns = list(turns)
        self.exchanges: list[list[GeminiFunctionExchange]] = []

    async def complete_function_turn(
        self,
        _messages: Sequence[GeminiMessage],
        _functions: object,
        exchanges: Sequence[GeminiFunctionExchange] = (),
    ) -> GeminiFunctionTurn:
        self.exchanges.append(list(exchanges))
        return self.turns.pop(0)


class _FakePlaces:
    def __init__(self, results: dict[str, PlacesSearchResult]) -> None:
        self.results = results
        self.calls: list[tuple[str, int]] = []

    async def search_text(
        self,
        query: str,
        *,
        max_results: int = 10,
    ) -> PlacesSearchResult:
        self.calls.append((query, max_results))
        return self.results[query]


def _place(place_id: str, name: str, country: str) -> Place:
    return Place(
        place_id=place_id,
        name=name,
        address=f"{name}, {country}",
        country_name=country,
        location=PlaceCoordinate(latitude=35.0, longitude=139.0),
        business_status="OPERATIONAL",
    )


def _turn(name: str, arguments: dict[str, object]) -> GeminiFunctionTurn:
    return GeminiFunctionTurn(
        calls=(GeminiFunctionCall(name=name, arguments=arguments),)
    )


def _two_city_itinerary() -> Itinerary:
    return Itinerary(
        destination="Tokyo and Kyoto",
        start_date="2026-09-20",
        end_date="2026-09-21",
        days=[
            Day(
                date="2026-09-20",
                city="Tokyo",
                country="Japan",
                title="Tokyo",
                accommodation="Tokyo hotel",
                items=[
                    Item(
                        id="tokyo-item",
                        start_time=time(9),
                        end_time=time(10),
                        title="Tokyo Park",
                        kind="place",
                        place_id="tokyo-park",
                    )
                ],
            ),
            Day(
                date="2026-09-21",
                city="Kyoto",
                country="Japan",
                title="Kyoto",
                accommodation="Kyoto hotel",
                intercity_transport="Train from Tokyo",
                items=[
                    Item(
                        id="kyoto-item",
                        start_time=time(9),
                        end_time=time(10),
                        title="Kyoto Temple",
                        kind="place",
                        place_id="kyoto-temple",
                    )
                ],
            ),
        ],
    )


async def test_multi_city_agent_calls_tools_then_submits() -> None:
    tokyo = _place("tokyo", "Tokyo", "Japan")
    kyoto = _place("kyoto", "Kyoto", "Japan")
    tokyo_park = _place("tokyo-park", "Tokyo Park", "Japan")
    kyoto_temple = _place("kyoto-temple", "Kyoto Temple", "Japan")
    itinerary = _two_city_itinerary()
    gemini = _FakeGemini(
        [
            GeminiFunctionTurn(
                calls=(
                    GeminiFunctionCall(
                        name="resolve_destination",
                        arguments={"query": "Tokyo"},
                    ),
                    GeminiFunctionCall(
                        name="resolve_destination",
                        arguments={"query": "Kyoto"},
                    ),
                )
            ),
            GeminiFunctionTurn(
                calls=(
                    GeminiFunctionCall(
                        name="search_places",
                        arguments={
                            "area_place_id": "tokyo",
                            "category": "park",
                        },
                    ),
                    GeminiFunctionCall(
                        name="search_places",
                        arguments={
                            "area_place_id": "kyoto",
                            "category": "attraction",
                        },
                    ),
                )
            ),
            _turn(
                "submit_draft",
                {"itinerary": itinerary.model_dump(mode="json")},
            ),
        ]
    )
    places = _FakePlaces(
        {
            "Tokyo": PlacesSearchResult(status="available", places=[tokyo]),
            "Kyoto": PlacesSearchResult(status="available", places=[kyoto]),
            "park in Tokyo, Japan": PlacesSearchResult(
                status="available",
                places=[tokyo_park],
            ),
            "attraction in Kyoto, Japan": PlacesSearchResult(
                status="available",
                places=[kyoto_temple],
            ),
        }
    )
    progress: list[tuple[str, int, int]] = []

    result = await run_planner_agent(
        clients=SimpleNamespace(gemini=gemini, places=places),
        request=TripRequest(
            destination="Tokyo and Kyoto",
            destination_facts=["Tokyo", "Kyoto"],
            start_date="2026-09-20",
            end_date="2026-09-21",
        ),
        previous_itinerary=None,
        new_user_messages=[],
        progress=lambda stage, step, tools: _record_progress(
            progress, stage, step, tools
        ),
        evaluate_draft=_accept_draft,
    )

    assert result.draft == itinerary
    assert result.clarification_question is None
    assert result.step_count == 3
    assert result.tool_call_count == 5
    assert result.places_available
    assert set(result.discovered_places) == {
        "tokyo",
        "kyoto",
        "tokyo-park",
        "kyoto-temple",
    }
    assert progress[-1] == ("drafting", 3, 5)


async def test_ambiguous_destination_requests_clarification() -> None:
    springfield_il = _place("springfield-il", "Springfield", "United States")
    springfield_ma = _place("springfield-ma", "Springfield", "United States")
    gemini = _FakeGemini(
        [
            _turn("resolve_destination", {"query": "Springfield"}),
            _turn(
                "request_clarification",
                {"question": "Which Springfield do you mean?"},
            ),
        ]
    )
    places = _FakePlaces(
        {
            "Springfield": PlacesSearchResult(
                status="available",
                places=[springfield_il, springfield_ma],
            )
        }
    )

    result = await run_planner_agent(
        clients=SimpleNamespace(gemini=gemini, places=places),
        request=TripRequest(
            destination="Springfield",
            start_date="2026-09-20",
            end_date="2026-09-20",
        ),
        previous_itinerary=None,
        new_user_messages=[],
        progress=_ignore_progress,
        evaluate_draft=_accept_draft,
    )

    assert result.draft is None
    assert result.clarification_question == "Which Springfield do you mean?"
    assert result.step_count == 2
    assert result.tool_call_count == 2


async def test_agent_turn_limit_fails_explicitly() -> None:
    gemini = _FakeGemini(
        [
            _turn("fetch_url", {"url": "https://example.com"})
            for _ in range(MAX_AGENT_TURNS)
        ]
    )

    with pytest.raises(AgentExecutionLimitError):
        await run_planner_agent(
            clients=SimpleNamespace(gemini=gemini, places=_FakePlaces({})),
            request=TripRequest(
                destination="Tokyo",
                start_date="2026-09-20",
                end_date="2026-09-20",
            ),
            previous_itinerary=None,
            new_user_messages=[],
            progress=_ignore_progress,
            evaluate_draft=_accept_draft,
        )

    last_exchange = gemini.exchanges[-1][-1]
    assert last_exchange.results[0].response["error"]["code"] == (
        "tool_call_rejected"
    )


async def test_agent_rejects_excessive_calls_before_running_tools() -> None:
    gemini = _FakeGemini(
        [
            GeminiFunctionTurn(
                calls=tuple(
                    GeminiFunctionCall(
                        name="resolve_destination",
                        arguments={"query": "Tokyo"},
                    )
                    for _ in range(MAX_FUNCTION_CALLS_PER_TURN + 1)
                )
            )
        ]
    )
    places = _FakePlaces({})

    with pytest.raises(AgentExecutionLimitError):
        await run_planner_agent(
            clients=SimpleNamespace(gemini=gemini, places=places),
            request=TripRequest(
                destination="Tokyo",
                start_date="2026-09-20",
                end_date="2026-09-20",
            ),
            previous_itinerary=None,
            new_user_messages=[],
            progress=_ignore_progress,
            evaluate_draft=_accept_draft,
        )

    assert places.calls == []


async def _record_progress(
    target: list[tuple[str, int, int]],
    stage: str,
    step: int,
    tools: int,
) -> None:
    target.append((stage, step, tools))


async def _ignore_progress(_stage: str, _step: int, _tools: int) -> None:
    pass


async def _accept_draft(
    itinerary: Itinerary,
    _candidate_ids: set[str],
    _places_available: bool,
    _step: int,
    _tools: int,
) -> PlannerDraftEvaluation:
    return PlannerDraftEvaluation(itinerary=itinerary)

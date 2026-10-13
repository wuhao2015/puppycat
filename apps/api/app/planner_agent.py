from __future__ import annotations

import json
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import date

from app.clients import AppClients
from app.errors import AgentExecutionLimitError
from app.external.places import Place
from app.gemini import (
    GeminiFunctionDefinition,
    GeminiFunctionExchange,
    GeminiFunctionResult,
    GeminiMessage,
)
from app.planner_tools import (
    PLANNER_TOOL_REGISTRY,
    PlannerToolArgumentsError,
    PlannerToolError,
    PlannerToolLimitError,
    PlannerToolPolicyError,
    PlannerToolbox,
    RequestClarificationInput,
    SubmitDraftInput,
)
from app.schemas import ChatMessage, Itinerary, PlanGenerationStage, TripRequest


MAX_AGENT_TURNS = 12
MAX_FUNCTION_CALLS_PER_TURN = 40

PlannerProgress = Callable[[PlanGenerationStage, int, int], Awaitable[None]]
PlannerDraftEvaluator = Callable[
    [Itinerary, set[str], bool, int, int],
    Awaitable["PlannerDraftEvaluation"],
]

AGENT_PROMPT = """You are Puppycat's Planner Agent. Build a complete, practical
itinerary from the supplied structured trip facts. You may only act through the
registered functions.

Rules:
- Resolve every exact destination_fact before planning places.
- If a destination has multiple candidates, call request_clarification; never
  select one yourself.
- Search each uniquely resolved city or area at least once. Search again only
  for a genuinely different user interest or constraint.
- Place items in the draft may only reference place_ids returned by tools or the
  supplied previous itinerary. Use kind=generic and place_id=null otherwise.
- The draft must cover every trip date exactly once and include each overnight
  city, country, accommodation when known, and necessary intercity transport.
- Never invent verification data, warnings, coordinates, weather, or source
  status; the server adds them.
- Call request_clarification only for missing required facts or a genuine
  destination ambiguity.
- Finish by calling exactly one terminal function: submit_draft or
  request_clarification. Do not answer with prose.
"""


@dataclass(frozen=True)
class PlannerAgentResult:
    request: TripRequest
    draft: Itinerary | None
    clarification_question: str | None
    discovered_places: dict[str, Place]
    places_available: bool
    step_count: int
    tool_call_count: int


@dataclass(frozen=True)
class PlannerDraftEvaluation:
    itinerary: Itinerary | None
    rejection_message: str | None = None
    blocker_place_ids: tuple[str, ...] = ()


async def run_planner_agent(
    *,
    clients: AppClients,
    request: TripRequest,
    previous_itinerary: Itinerary | None,
    new_user_messages: Sequence[ChatMessage],
    progress: PlannerProgress,
    evaluate_draft: PlannerDraftEvaluator,
) -> PlannerAgentResult:
    previous_places = (
        [
            item.place
            for day in previous_itinerary.days
            for item in day.items
            if item.place is not None
        ]
        if previous_itinerary is not None
        else []
    )
    toolbox = PlannerToolbox(
        clients,
        destination_facts=request.destination_facts,
        known_places=previous_places,
    )
    messages = _agent_messages(
        request,
        previous_itinerary=previous_itinerary,
        new_user_messages=new_user_messages,
    )
    functions = tuple(
        GeminiFunctionDefinition(
            name=definition.name,
            description=definition.description,
            parameters=definition.input_schema.model_json_schema(),
        )
        for definition in PLANNER_TOOL_REGISTRY.values()
    )
    exchanges: list[GeminiFunctionExchange] = []

    for step_count in range(1, MAX_AGENT_TURNS + 1):
        turn = await clients.gemini.complete_function_turn(
            messages,
            functions,
            exchanges,
        )
        if len(turn.calls) > MAX_FUNCTION_CALLS_PER_TURN:
            raise AgentExecutionLimitError()

        stage = _stage_for_calls([call.name for call in turn.calls])
        await progress(stage, step_count, toolbox.tool_call_count)

        terminal_calls = [
            call
            for call in turn.calls
            if call.name in {"submit_draft", "request_clarification"}
        ]
        if terminal_calls and len(turn.calls) != 1:
            exchanges.append(
                GeminiFunctionExchange(
                    turn=turn,
                    results=tuple(
                        _error_result(
                            call.name,
                            call.call_id,
                            "tool_batch_rejected",
                            "A terminal function must be the only call in its turn",
                        )
                        for call in turn.calls
                    ),
                )
            )
            continue

        call_results: list[GeminiFunctionResult] = []
        for call in turn.calls:
            if call.name == "submit_draft":
                parsed = _parse_terminal_call(
                    toolbox,
                    call.name,
                    call.arguments,
                    call.call_id,
                )
                if isinstance(parsed, GeminiFunctionResult):
                    call_results.append(parsed)
                    continue
                assert isinstance(parsed, SubmitDraftInput)
                rejection = _submission_rejection(request, toolbox)
                if rejection is not None:
                    call_results.append(
                        _error_result(
                            call.name,
                            call.call_id,
                            "draft_not_ready",
                            rejection,
                        )
                    )
                    continue
                _record_terminal_call(toolbox)
                await progress("drafting", step_count, toolbox.tool_call_count)
                evaluation = await evaluate_draft(
                    parsed.itinerary,
                    set(toolbox.discovered_places),
                    toolbox.places_available,
                    step_count,
                    toolbox.tool_call_count,
                )
                if evaluation.itinerary is None:
                    error: dict[str, object] = {
                        "code": "draft_rejected",
                        "message": evaluation.rejection_message
                        or "The draft failed server validation",
                    }
                    if evaluation.blocker_place_ids:
                        error["blocker_place_ids"] = list(
                            evaluation.blocker_place_ids
                        )
                    call_results.append(
                        GeminiFunctionResult(
                            name=call.name,
                            call_id=call.call_id,
                            response={"error": error},
                        )
                    )
                    continue
                return PlannerAgentResult(
                    request=request,
                    draft=evaluation.itinerary,
                    clarification_question=None,
                    discovered_places=toolbox.discovered_places,
                    places_available=toolbox.places_available,
                    step_count=step_count,
                    tool_call_count=toolbox.tool_call_count,
                )

            if call.name == "request_clarification":
                parsed = _parse_terminal_call(
                    toolbox,
                    call.name,
                    call.arguments,
                    call.call_id,
                )
                if isinstance(parsed, GeminiFunctionResult):
                    call_results.append(parsed)
                    continue
                assert isinstance(parsed, RequestClarificationInput)
                if not _clarification_allowed(request, toolbox):
                    call_results.append(
                        _error_result(
                            call.name,
                            call.call_id,
                            "clarification_not_allowed",
                            "Use the available tools to determine the answer",
                        )
                    )
                    continue
                _record_terminal_call(toolbox)
                await progress(stage, step_count, toolbox.tool_call_count)
                return PlannerAgentResult(
                    request=request,
                    draft=None,
                    clarification_question=parsed.question,
                    discovered_places=toolbox.discovered_places,
                    places_available=toolbox.places_available,
                    step_count=step_count,
                    tool_call_count=toolbox.tool_call_count,
                )

            try:
                output = await toolbox.execute(call.name, call.arguments)
                call_results.append(
                    GeminiFunctionResult(
                        name=call.name,
                        call_id=call.call_id,
                        response={"output": output.model_dump(mode="json")},
                    )
                )
            except PlannerToolLimitError as error:
                raise AgentExecutionLimitError() from error
            except PlannerToolError as error:
                call_results.append(
                    _error_result(
                        call.name,
                        call.call_id,
                        "tool_call_rejected",
                        _safe_tool_error(error),
                    )
                )

        await progress(stage, step_count, toolbox.tool_call_count)
        exchanges.append(
            GeminiFunctionExchange(turn=turn, results=tuple(call_results))
        )

    raise AgentExecutionLimitError()


def _agent_messages(
    request: TripRequest,
    *,
    previous_itinerary: Itinerary | None,
    new_user_messages: Sequence[ChatMessage],
) -> list[GeminiMessage]:
    payload = {
        "trip_request": request.model_dump(mode="json"),
        "previous_itinerary": (
            previous_itinerary.model_dump(mode="json")
            if previous_itinerary is not None
            else None
        ),
        "new_user_messages": [
            message.model_dump(mode="json") for message in new_user_messages
        ],
    }
    return [
        GeminiMessage(role="system", content=AGENT_PROMPT),
        GeminiMessage(
            role="user",
            content=json.dumps(payload, ensure_ascii=False),
        ),
    ]


def _stage_for_calls(tool_names: list[str]) -> PlanGenerationStage:
    if "submit_draft" in tool_names:
        return "drafting"
    if "resolve_destination" in tool_names:
        return "resolving_destination"
    if any(
        name in {"search_places", "get_place_details"} for name in tool_names
    ):
        return "searching_places"
    return "understanding"


def _submission_rejection(
    request: TripRequest,
    toolbox: PlannerToolbox,
) -> str | None:
    missing = _missing_required_fields(request)
    if missing:
        return f"Required trip facts are missing: {', '.join(missing)}"
    if _dates_invalid(request.start_date, request.end_date):
        return "The trip date range is invalid"
    if toolbox.has_ambiguous_destination:
        return "A destination is ambiguous and must be clarified"
    if not toolbox.ready_to_submit:
        return "Resolve every destination and search each resolved area first"
    return None


def _clarification_allowed(
    request: TripRequest,
    toolbox: PlannerToolbox,
) -> bool:
    return bool(
        _missing_required_fields(request)
        or _dates_invalid(request.start_date, request.end_date)
        or toolbox.has_ambiguous_destination
    )


def _missing_required_fields(request: TripRequest) -> list[str]:
    return [
        field
        for field in ("destination", "start_date", "end_date")
        if getattr(request, field) is None
    ]


def _dates_invalid(start_date: date | None, end_date: date | None) -> bool:
    return (
        start_date is not None
        and end_date is not None
        and end_date < start_date
    )


def _parse_terminal_call(
    toolbox: PlannerToolbox,
    name: str,
    arguments: object,
    call_id: str | None = None,
) -> SubmitDraftInput | RequestClarificationInput | GeminiFunctionResult:
    try:
        parsed = toolbox.parse_arguments(name, arguments)
    except PlannerToolError as error:
        return _error_result(
            name,
            call_id,
            "tool_call_rejected",
            _safe_tool_error(error),
        )
    assert isinstance(parsed, (SubmitDraftInput, RequestClarificationInput))
    return parsed


def _record_terminal_call(toolbox: PlannerToolbox) -> None:
    try:
        toolbox.record_terminal_call()
    except PlannerToolLimitError as error:
        raise AgentExecutionLimitError() from error


def _safe_tool_error(error: PlannerToolError) -> str:
    if isinstance(error, PlannerToolArgumentsError):
        return "The function arguments are invalid"
    if isinstance(error, PlannerToolPolicyError):
        return str(error)
    return "The function call is not allowed"


def _error_result(
    name: str,
    call_id: str | None,
    code: str,
    message: str,
) -> GeminiFunctionResult:
    return GeminiFunctionResult(
        name=name,
        call_id=call_id,
        response={"error": {"code": code, "message": message}},
    )

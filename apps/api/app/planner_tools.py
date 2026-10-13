from __future__ import annotations

import json
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, TypeAlias

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from app.clients import AppClients
from app.external.places import Place, PlacesUnavailableReason
from app.schemas import Itinerary


PlannerToolName = Literal[
    "resolve_destination",
    "search_places",
    "get_place_details",
    "submit_draft",
    "request_clarification",
]
PlaceSearchCategory = Literal[
    "attraction",
    "museum",
    "restaurant",
    "park",
    "activity",
]
ToolAvailability = Literal["available", "unavailable"]
DetailsAvailability = Literal["available", "not_found", "unavailable"]

MAX_TOOL_CALLS = 40
MAX_DESTINATION_RESOLUTIONS = 10
MAX_PLACE_SEARCHES = 20
MAX_SEARCH_RESULTS = 20
MAX_DESTINATION_CANDIDATES = 5


class PlannerToolError(Exception):
    """Base class for rejected Planner tool calls."""


class UnknownPlannerToolError(PlannerToolError):
    pass


class PlannerToolArgumentsError(PlannerToolError):
    pass


class PlannerToolPolicyError(PlannerToolError):
    pass


class PlannerToolLimitError(PlannerToolError):
    pass


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def _normalized_key(value: str) -> str:
    return _normalize_text(value).casefold()


def _reject_url(value: str) -> str:
    normalized = _normalize_text(value)
    lowered = normalized.casefold()
    if "://" in lowered or lowered.startswith("www."):
        raise ValueError("URLs are not allowed in Planner tool arguments")
    return normalized


class ResolveDestinationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=200)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = _reject_url(value)
        if not normalized:
            raise ValueError("Destination query cannot be empty")
        return normalized


class SearchPlacesInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    area_place_id: str = Field(min_length=1, max_length=500)
    category: PlaceSearchCategory
    query: str | None = Field(default=None, max_length=120)
    max_results: int = Field(default=10, ge=1, le=MAX_SEARCH_RESULTS)

    @field_validator("area_place_id")
    @classmethod
    def normalize_area_place_id(cls, value: str) -> str:
        normalized = _reject_url(value)
        if not normalized:
            raise ValueError("area_place_id cannot be empty")
        return normalized

    @field_validator("query")
    @classmethod
    def normalize_optional_query(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _reject_url(value) or None


class GetPlaceDetailsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    place_id: str = Field(min_length=1, max_length=500)

    @field_validator("place_id")
    @classmethod
    def normalize_place_id(cls, value: str) -> str:
        normalized = _reject_url(value)
        if not normalized:
            raise ValueError("place_id cannot be empty")
        return normalized


class SubmitDraftInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    itinerary: Itinerary


class RequestClarificationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=300)

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        normalized = _reject_url(value)
        if not normalized:
            raise ValueError("Clarification question cannot be empty")
        return normalized


class ResolveDestinationOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["google_places"] = "google_places"
    status: ToolAvailability
    candidates: list[Place] = Field(
        default_factory=list,
        max_length=MAX_DESTINATION_CANDIDATES,
    )
    requires_clarification: bool = False
    unavailable_reason: PlacesUnavailableReason | None = None

    @model_validator(mode="after")
    def validate_status(self) -> ResolveDestinationOutput:
        if self.status == "unavailable" and self.candidates:
            raise ValueError("Unavailable destination results cannot have candidates")
        if self.requires_clarification != (len(self.candidates) > 1):
            raise ValueError("Destination clarification state is inconsistent")
        return self


class SearchPlacesOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["google_places"] = "google_places"
    status: ToolAvailability
    places: list[Place] = Field(default_factory=list, max_length=MAX_SEARCH_RESULTS)
    unavailable_reason: PlacesUnavailableReason | None = None

    @model_validator(mode="after")
    def validate_status(self) -> SearchPlacesOutput:
        if self.status == "unavailable" and self.places:
            raise ValueError("Unavailable place search results cannot have places")
        return self


class GetPlaceDetailsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["google_places"] = "google_places"
    status: DetailsAvailability
    place: Place | None = None
    unavailable_reason: PlacesUnavailableReason | None = None

    @model_validator(mode="after")
    def validate_status(self) -> GetPlaceDetailsOutput:
        if self.status == "available" and self.place is None:
            raise ValueError("Available place details require a place")
        if self.status != "available" and self.place is not None:
            raise ValueError("Unavailable place details cannot include a place")
        return self


PlannerToolInput: TypeAlias = (
    ResolveDestinationInput
    | SearchPlacesInput
    | GetPlaceDetailsInput
    | SubmitDraftInput
    | RequestClarificationInput
)
PlannerToolOutput: TypeAlias = (
    ResolveDestinationOutput | SearchPlacesOutput | GetPlaceDetailsOutput
)


@dataclass(frozen=True)
class PlannerToolDefinition:
    name: PlannerToolName
    input_schema: type[BaseModel]
    output_schema: type[BaseModel] | None
    description: str


PLANNER_TOOL_REGISTRY = MappingProxyType(
    {
        "resolve_destination": PlannerToolDefinition(
            name="resolve_destination",
            input_schema=ResolveDestinationInput,
            output_schema=ResolveDestinationOutput,
            description=(
                "Resolve a destination fact into at most five normalized place "
                "candidates."
            ),
        ),
        "search_places": PlannerToolDefinition(
            name="search_places",
            input_schema=SearchPlacesInput,
            output_schema=SearchPlacesOutput,
            description=(
                "Search an unambiguous resolved area for an allowed place category."
            ),
        ),
        "get_place_details": PlannerToolDefinition(
            name="get_place_details",
            input_schema=GetPlaceDetailsInput,
            output_schema=GetPlaceDetailsOutput,
            description="Get details for a place known to this generation.",
        ),
        "submit_draft": PlannerToolDefinition(
            name="submit_draft",
            input_schema=SubmitDraftInput,
            output_schema=None,
            description=(
                "Submit the complete itinerary after all destinations are resolved "
                "and enough place searches have been completed."
            ),
        ),
        "request_clarification": PlannerToolDefinition(
            name="request_clarification",
            input_schema=RequestClarificationInput,
            output_schema=None,
            description=(
                "End planning with one concise question only when required trip "
                "facts are missing or a destination is genuinely ambiguous."
            ),
        ),
    }
)


@dataclass(frozen=True)
class PlannerToolLimits:
    max_tool_calls: int = MAX_TOOL_CALLS
    max_destination_resolutions: int = MAX_DESTINATION_RESOLUTIONS
    max_place_searches: int = MAX_PLACE_SEARCHES

    def __post_init__(self) -> None:
        if self.max_tool_calls < 1:
            raise ValueError("max_tool_calls must be positive")
        if self.max_destination_resolutions < 1:
            raise ValueError("max_destination_resolutions must be positive")
        if self.max_place_searches < 1:
            raise ValueError("max_place_searches must be positive")
        if self.max_destination_resolutions > self.max_tool_calls:
            raise ValueError(
                "max_destination_resolutions cannot exceed max_tool_calls"
            )
        if self.max_place_searches > self.max_tool_calls:
            raise ValueError("max_place_searches cannot exceed max_tool_calls")


class PlannerToolbox:
    """Generation-scoped registry, policy, deduplication, and Places execution."""

    def __init__(
        self,
        clients: AppClients,
        *,
        destination_facts: list[str],
        known_places: list[Place] | None = None,
        limits: PlannerToolLimits | None = None,
    ) -> None:
        self._clients = clients
        self._destination_facts = {
            _normalized_key(fact): _normalize_text(fact)
            for fact in destination_facts
            if _normalize_text(fact)
        }
        self._limits = limits or PlannerToolLimits()
        self._known_places = {
            place.place_id: place.model_copy(deep=True)
            for place in (known_places or [])
        }
        self._resolved_areas: dict[str, Place] = {}
        self._resolved_fact_areas: dict[str, str] = {}
        self._attempted_destination_facts: set[str] = set()
        self._ambiguous_destination_facts: set[str] = set()
        self._ambiguous_area_ids: set[str] = set()
        self._attempted_search_area_ids: set[str] = set()
        self._searched_area_ids: set[str] = set()
        self._discovered_places: dict[str, Place] = dict(self._known_places)
        self._results: dict[str, PlannerToolOutput] = {}
        self.tool_call_count = 0
        self.destination_resolution_count = 0
        self.place_search_count = 0

    @property
    def discovered_places(self) -> dict[str, Place]:
        return {
            place_id: place.model_copy(deep=True)
            for place_id, place in self._discovered_places.items()
        }

    @property
    def has_ambiguous_destination(self) -> bool:
        return bool(self._ambiguous_destination_facts)

    @property
    def ready_to_submit(self) -> bool:
        facts = set(self._destination_facts)
        return (
            bool(facts)
            and facts <= self._attempted_destination_facts
            and not self._ambiguous_destination_facts
            and set(self._resolved_fact_areas.values())
            <= self._attempted_search_area_ids
        )

    @property
    def places_available(self) -> bool:
        return (
            self.ready_to_submit
            and len(self._resolved_fact_areas) == len(self._destination_facts)
            and set(self._resolved_fact_areas.values()) <= self._searched_area_ids
        )

    def parse_arguments(
        self,
        tool_name: str,
        arguments: object,
    ) -> PlannerToolInput:
        definition = PLANNER_TOOL_REGISTRY.get(tool_name)
        if definition is None:
            raise UnknownPlannerToolError(f"Unknown Planner tool: {tool_name}")
        return self._parse_arguments(definition, arguments)

    def record_terminal_call(self) -> None:
        self._reserve_call()

    async def execute(
        self,
        tool_name: str,
        arguments: object,
    ) -> PlannerToolOutput:
        definition = PLANNER_TOOL_REGISTRY.get(tool_name)
        if definition is None:
            raise UnknownPlannerToolError(f"Unknown Planner tool: {tool_name}")

        if definition.output_schema is None:
            raise PlannerToolPolicyError(
                f"Terminal Planner tool must be handled by the Agent: {tool_name}"
            )

        parsed = self._parse_arguments(definition, arguments)
        self._enforce_policy(tool_name, parsed)
        call_key = self._call_key(tool_name, parsed)
        cached = self._results.get(call_key)
        if cached is not None:
            return cached.model_copy(deep=True)

        self._reserve_call(
            is_destination_resolution=tool_name == "resolve_destination",
            is_place_search=tool_name == "search_places",
        )
        if tool_name == "resolve_destination":
            output = await self._resolve_destination(parsed)
        elif tool_name == "search_places":
            output = await self._search_places(parsed)
        else:
            output = await self._get_place_details(parsed)

        validated = definition.output_schema.model_validate(output)
        self._results[call_key] = validated
        return validated.model_copy(deep=True)

    def _parse_arguments(
        self,
        definition: PlannerToolDefinition,
        arguments: object,
    ) -> PlannerToolInput:
        try:
            return definition.input_schema.model_validate(arguments)
        except ValidationError as error:
            raise PlannerToolArgumentsError(
                f"Invalid arguments for {definition.name}"
            ) from error

    def _enforce_policy(
        self,
        tool_name: str,
        arguments: PlannerToolInput,
    ) -> None:
        if tool_name == "resolve_destination":
            assert isinstance(arguments, ResolveDestinationInput)
            if _normalized_key(arguments.query) not in self._destination_facts:
                raise PlannerToolPolicyError(
                    "Destination query must come from confirmed trip facts"
                )
            return

        if tool_name == "search_places":
            assert isinstance(arguments, SearchPlacesInput)
            if arguments.area_place_id in self._ambiguous_area_ids:
                raise PlannerToolPolicyError(
                    "Ambiguous destinations must be clarified before place search"
                )
            if arguments.area_place_id not in self._resolved_areas:
                raise PlannerToolPolicyError(
                    "Place search requires an unambiguous resolved area"
                )
            return

        assert isinstance(arguments, GetPlaceDetailsInput)
        if arguments.place_id not in self._discovered_places:
            raise PlannerToolPolicyError(
                "Place details require a place known to this generation"
            )

    def _reserve_call(
        self,
        *,
        is_destination_resolution: bool = False,
        is_place_search: bool = False,
    ) -> None:
        if self.tool_call_count >= self._limits.max_tool_calls:
            raise PlannerToolLimitError("Planner tool call limit reached")
        if (
            is_destination_resolution
            and self.destination_resolution_count
            >= self._limits.max_destination_resolutions
        ):
            raise PlannerToolLimitError(
                "Planner destination resolution limit reached"
            )
        if (
            is_place_search
            and self.place_search_count >= self._limits.max_place_searches
        ):
            raise PlannerToolLimitError("Planner place search limit reached")
        self.tool_call_count += 1
        if is_destination_resolution:
            self.destination_resolution_count += 1
        if is_place_search:
            self.place_search_count += 1

    async def _resolve_destination(
        self,
        arguments: PlannerToolInput,
    ) -> ResolveDestinationOutput:
        assert isinstance(arguments, ResolveDestinationInput)
        result = await self._clients.places.search_text(
            arguments.query,
            max_results=MAX_DESTINATION_CANDIDATES,
        )
        candidates = _unique_places(
            result.places,
            limit=MAX_DESTINATION_CANDIDATES,
        )
        requires_clarification = len(candidates) > 1
        fact_key = _normalized_key(arguments.query)
        self._attempted_destination_facts.add(fact_key)
        self._resolved_fact_areas.pop(fact_key, None)
        self._ambiguous_destination_facts.discard(fact_key)
        if result.status == "available":
            for place in candidates:
                self._discovered_places.setdefault(place.place_id, place)
                if requires_clarification:
                    self._resolved_areas.pop(place.place_id, None)
                    self._ambiguous_area_ids.add(place.place_id)
                elif candidates:
                    self._ambiguous_area_ids.discard(place.place_id)
                    self._resolved_areas[place.place_id] = place
            if requires_clarification:
                self._ambiguous_destination_facts.add(fact_key)
            elif len(candidates) == 1:
                self._resolved_fact_areas[fact_key] = candidates[0].place_id
        return ResolveDestinationOutput(
            status=result.status,
            candidates=candidates,
            requires_clarification=requires_clarification,
            unavailable_reason=result.unavailable_reason,
        )

    async def _search_places(
        self,
        arguments: PlannerToolInput,
    ) -> SearchPlacesOutput:
        assert isinstance(arguments, SearchPlacesInput)
        area = self._resolved_areas[arguments.area_place_id]
        area_label = area.address
        if not area_label:
            area_parts = [area.name]
            if (
                area.country_name
                and area.country_name.casefold() != area.name.casefold()
            ):
                area_parts.append(area.country_name)
            area_label = ", ".join(area_parts)
        query = (
            f"{arguments.query} {arguments.category} in {area_label}"
            if arguments.query
            else f"{arguments.category} in {area_label}"
        )
        result = await self._clients.places.search_text(
            query,
            max_results=arguments.max_results,
        )
        self._attempted_search_area_ids.add(arguments.area_place_id)
        places = _unique_places(result.places, limit=arguments.max_results)
        if result.status == "available":
            self._searched_area_ids.add(arguments.area_place_id)
            for place in places:
                self._discovered_places.setdefault(place.place_id, place)
        return SearchPlacesOutput(
            status=result.status,
            places=places,
            unavailable_reason=result.unavailable_reason,
        )

    async def _get_place_details(
        self,
        arguments: PlannerToolInput,
    ) -> GetPlaceDetailsOutput:
        assert isinstance(arguments, GetPlaceDetailsInput)
        result = await self._clients.places.details(arguments.place_id)
        if result.status == "available" and result.place is not None:
            self._discovered_places[arguments.place_id] = result.place
        return GetPlaceDetailsOutput(
            status=result.status,
            place=result.place,
            unavailable_reason=result.unavailable_reason,
        )

    @staticmethod
    def _call_key(tool_name: str, arguments: PlannerToolInput) -> str:
        if isinstance(arguments, ResolveDestinationInput):
            payload = {"query": _normalized_key(arguments.query)}
        elif isinstance(arguments, SearchPlacesInput):
            payload = {
                "area_place_id": arguments.area_place_id,
                "category": arguments.category,
                "query": _normalized_key(arguments.query or ""),
            }
        else:
            payload = {"place_id": arguments.place_id}
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return f"{tool_name}:{encoded}"


def _unique_places(places: list[Place], *, limit: int) -> list[Place]:
    unique: list[Place] = []
    seen: set[str] = set()
    for place in places:
        if place.place_id in seen:
            continue
        seen.add(place.place_id)
        unique.append(place.model_copy(deep=True))
        if len(unique) >= limit:
            break
    return unique

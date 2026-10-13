from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import AppClients
from app.errors import (
    ItineraryGenerationError,
    NoNewTripRequirementsError,
)
from app.gemini import GeminiMessage
from app.models import Itinerary as ItineraryRecord
from app.models import Trip
from app.planner_agent import (
    PlannerDraftEvaluation,
    PlannerProgress,
    run_planner_agent,
)
from app.schemas import (
    ChatMessage,
    Itinerary,
    PlanGenerationStage,
    TripRequest,
)
from app.verification import known_places, verify_itinerary


EXTRACTION_PROMPT = """Extract the complete travel request from the supplied trip data and conversation.
Use ISO dates. Return null for a destination or date that the user has not supplied.
Set destination to the complete user-facing destination summary. Put each distinct
city, region, or country that must be resolved separately in destination_facts.
Preferences must not repeat destination or dates. Never invent missing facts."""

@dataclass(frozen=True)
class PlanGenerationResult:
    itinerary: ItineraryRecord | None
    clarification_question: str | None
    step_count: int
    tool_call_count: int


async def latest_itinerary(
    session: AsyncSession, trip_id: str
) -> ItineraryRecord | None:
    return await session.scalar(
        select(ItineraryRecord)
        .where(ItineraryRecord.trip_id == trip_id)
        .order_by(ItineraryRecord.created_at.desc(), ItineraryRecord.id.desc())
        .limit(1)
    )


async def generate_plan(
    session: AsyncSession,
    *,
    trip: Trip,
    clients: AppClients,
    through: datetime | None = None,
    previous_input_message_ts: datetime | None = None,
    progress: PlannerProgress | None = None,
) -> PlanGenerationResult:
    previous = await latest_itinerary(session, trip.id)
    conversation = _messages_through(trip.chat_messages or [], through)
    messages_since = (
        previous_input_message_ts
        if previous_input_message_ts is not None
        else previous.created_at
        if previous is not None
        else None
    )
    new_user_messages = _messages_after(
        conversation,
        messages_since,
    )
    if previous is not None and not new_user_messages:
        raise NoNewTripRequirementsError()

    previous_data = (
        Itinerary.model_validate(previous.data) if previous is not None else None
    )
    extracted = await clients.gemini.complete_json(
        _extraction_messages(
            trip,
            previous_data=previous_data,
            new_user_messages=new_user_messages,
            conversation=conversation,
        ),
        TripRequest,
    )
    async def report_progress(
        stage: PlanGenerationStage,
        step_count: int,
        tool_call_count: int,
    ) -> None:
        if progress is not None:
            await progress(stage, step_count, tool_call_count)

    existing_places = (
        known_places(previous_data) if previous_data is not None else {}
    )

    async def evaluate_draft(
        draft: Itinerary,
        candidate_ids: set[str],
        places_available: bool,
        step_count: int,
        tool_call_count: int,
    ) -> PlannerDraftEvaluation:
        await report_progress("drafting", step_count, tool_call_count)
        try:
            prepared = await _prepare_draft(
                draft,
                request=extracted,
                candidate_ids=candidate_ids,
                clients=clients,
            )
        except ItineraryGenerationError:
            return PlannerDraftEvaluation(
                itinerary=None,
                rejection_message=(
                    "The draft does not match the trip facts or allowed places"
                ),
            )
        await report_progress("verifying", step_count, tool_call_count)
        verification = await verify_itinerary(
            prepared,
            clients=clients,
            places_available=places_available,
            known_places=existing_places,
        )
        if verification.blocker_place_ids:
            return PlannerDraftEvaluation(
                itinerary=None,
                rejection_message=(
                    "Replace every closed or missing place before resubmitting"
                ),
                blocker_place_ids=tuple(sorted(verification.blocker_place_ids)),
            )
        return PlannerDraftEvaluation(itinerary=verification.itinerary)

    agent_result = await run_planner_agent(
        clients=clients,
        request=extracted,
        previous_itinerary=previous_data,
        new_user_messages=new_user_messages,
        progress=report_progress,
        evaluate_draft=evaluate_draft,
    )

    if agent_result.clarification_question is not None:
        return PlanGenerationResult(
            itinerary=None,
            clarification_question=agent_result.clarification_question,
            step_count=agent_result.step_count,
            tool_call_count=agent_result.tool_call_count,
        )

    draft = agent_result.draft
    assert draft is not None

    assert extracted.destination is not None
    assert extracted.start_date is not None
    assert extracted.end_date is not None
    trip.destination = extracted.destination
    trip.start_date = extracted.start_date
    trip.end_date = extracted.end_date
    trip.preferences = extracted.preferences()
    record = ItineraryRecord(
        trip_id=trip.id,
        data=draft.model_dump(mode="json"),
    )
    session.add(record)
    await session.flush()
    await session.refresh(record)
    return PlanGenerationResult(
        itinerary=record,
        clarification_question=None,
        step_count=agent_result.step_count,
        tool_call_count=agent_result.tool_call_count,
    )


def _messages_through(
    payloads: list[dict[str, object]], through: datetime | None
) -> list[dict[str, object]]:
    if through is None:
        return payloads
    return [
        payload
        for payload in payloads
        if ChatMessage.model_validate(payload).ts <= through
    ]


def _messages_after(
    payloads: list[dict[str, object]], since: datetime | None
) -> list[ChatMessage]:
    messages = [ChatMessage.model_validate(payload) for payload in payloads]
    return [
        message
        for message in messages
        if message.role == "user" and (since is None or message.ts > since)
    ]


def _extraction_messages(
    trip: Trip,
    *,
    previous_data: Itinerary | None,
    new_user_messages: list[ChatMessage],
    conversation: list[dict[str, object]],
) -> list[GeminiMessage]:
    known = {
        "destination": trip.destination,
        "start_date": trip.start_date,
        "end_date": trip.end_date,
        "preferences": trip.preferences or {},
    }
    context = {
        "known_trip": known,
        "previous_itinerary": (
            previous_data.model_dump(mode="json") if previous_data else None
        ),
        "conversation": [
            message.model_dump(mode="json")
            for message in (
                new_user_messages
                if previous_data is not None
                else [
                    ChatMessage.model_validate(payload)
                    for payload in conversation
                ]
            )
        ],
    }
    return [
        GeminiMessage(role="system", content=EXTRACTION_PROMPT),
        GeminiMessage(
            role="user",
            content=json.dumps(context, ensure_ascii=False, default=str),
        ),
    ]


async def _prepare_draft(
    draft: Itinerary,
    *,
    request: TripRequest,
    candidate_ids: set[str],
    clients: AppClients,
) -> Itinerary:
    if (
        request.destination is None
        or draft.destination.strip().casefold()
        != request.destination.strip().casefold()
        or draft.start_date != request.start_date
        or draft.end_date != request.end_date
    ):
        raise ItineraryGenerationError()
    for day in draft.days:
        if not day.city or not day.country:
            raise ItineraryGenerationError()
        for item in day.items:
            if item.kind == "place" and item.place_id not in candidate_ids:
                raise ItineraryGenerationError()
            item.place = None
            item.warnings = []
        day.weather = None

    location_queries = list(
        dict.fromkeys((day.city.strip(), day.country.strip()) for day in draft.days)
    )
    locations = await asyncio.gather(
        *(
            clients.places.search_text(f"{city}, {country}", max_results=1)
            for city, country in location_queries
        )
    )
    location_by_query = dict(zip(location_queries, locations, strict=True))
    for day in draft.days:
        result = location_by_query[(day.city.strip(), day.country.strip())]
        location = result.places[0] if result.status == "available" and result.places else None
        if location is None:
            day.location = None
            day.country_code = None
            continue
        day.city = location.name
        day.country = location.country_name or day.country
        day.country_code = location.country_code
        day.location = location.location

    draft.destination = request.destination
    draft.warnings = []
    draft.verification_status = "unavailable"
    draft.verified_sources = []
    draft.unavailable_sources = []
    return draft

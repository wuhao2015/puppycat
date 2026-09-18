from __future__ import annotations

import asyncio
import json
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import AppClients
from app.errors import (
    InvalidTripDatesError,
    ItineraryGenerationError,
    MissingTripFieldsError,
    NoNewTripRequirementsError,
)
from app.external.places import Place, PlacesSearchResult
from app.gemini import GeminiMessage
from app.models import Itinerary as ItineraryRecord
from app.models import Trip
from app.schemas import ChatMessage, Itinerary, TripRequest
from app.verification import known_places, verify_itinerary


EXTRACTION_PROMPT = """Extract the complete travel request from the supplied trip data and conversation.
Use ISO dates. Return null for a destination or date that the user has not supplied.
Preferences must not repeat destination or dates. Never invent missing facts."""

DRAFT_PROMPT = """Create a practical daily itinerary matching the supplied request.
Every place item must use a place_id from candidate_places. Activities without a
specific candidate must be kind=generic and have place_id=null. Cover every date
exactly once in chronological order, use unique item IDs, and keep item times
within one day. Do not invent verification results, warnings, place details,
weather, destination coordinates, or source status; those are added by the server."""


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
) -> ItineraryRecord:
    previous = await latest_itinerary(session, trip.id)
    new_user_messages = _messages_after(
        trip.chat_messages or [], previous.created_at if previous else None
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
        ),
        TripRequest,
    )
    _validate_request(extracted)

    destination = extracted.destination
    start_date = extracted.start_date
    end_date = extracted.end_date
    assert destination is not None
    assert start_date is not None
    assert end_date is not None

    destination_result, candidates_result = await asyncio.gather(
        clients.places.search_text(destination, max_results=1),
        clients.places.search_text(
            f"top attractions restaurants and activities in {destination}",
            max_results=20,
        ),
    )
    candidates = _candidate_places(destination_result, candidates_result)
    if previous_data is not None:
        candidates = _merge_places(
            candidates,
            list(known_places(previous_data).values()),
        )

    draft = await clients.gemini.complete_json(
        _draft_messages(
            extracted,
            candidates,
            previous_data=previous_data,
            new_user_messages=new_user_messages,
        ),
        Itinerary,
    )
    draft = _prepare_draft(
        draft,
        request=extracted,
        candidate_ids={place.place_id for place in candidates},
        destination_result=destination_result,
    )
    existing_places = known_places(previous_data) if previous_data is not None else {}
    result = await verify_itinerary(
        draft,
        clients=clients,
        places_available=(
            destination_result.status == "available"
            and candidates_result.status == "available"
        ),
        known_places=existing_places,
    )

    if result.blocker_place_ids:
        replacement = await clients.gemini.complete_json(
            _replacement_messages(
                result.itinerary,
                result.blocker_place_ids,
                candidates,
            ),
            Itinerary,
        )
        replacement = _prepare_draft(
            replacement,
            request=extracted,
            candidate_ids={place.place_id for place in candidates}
            - result.blocker_place_ids,
            destination_result=destination_result,
        )
        reusable = known_places(result.itinerary)
        for place_id in result.blocker_place_ids:
            reusable.pop(place_id, None)
        result = await verify_itinerary(
            replacement,
            clients=clients,
            places_available=(
                destination_result.status == "available"
                and candidates_result.status == "available"
            ),
            known_places=reusable,
            reuse_global_from=result.itinerary,
        )
        if result.blocker_place_ids:
            raise ItineraryGenerationError()

    trip.destination = destination
    trip.start_date = start_date
    trip.end_date = end_date
    trip.preferences = extracted.preferences()
    record = ItineraryRecord(
        trip_id=trip.id,
        data=result.itinerary.model_dump(mode="json"),
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


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
                    for payload in (trip.chat_messages or [])
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


def _draft_messages(
    request: TripRequest,
    candidates: list[Place],
    *,
    previous_data: Itinerary | None,
    new_user_messages: list[ChatMessage],
) -> list[GeminiMessage]:
    payload = {
        "trip_request": request.model_dump(mode="json"),
        "candidate_places": [place.model_dump(mode="json") for place in candidates],
        "previous_itinerary": (
            previous_data.model_dump(mode="json") if previous_data else None
        ),
        "new_user_requests": [
            message.model_dump(mode="json") for message in new_user_messages
        ],
    }
    return [
        GeminiMessage(role="system", content=DRAFT_PROMPT),
        GeminiMessage(role="user", content=json.dumps(payload, ensure_ascii=False)),
    ]


def _replacement_messages(
    itinerary: Itinerary,
    blocker_place_ids: set[str],
    candidates: list[Place],
) -> list[GeminiMessage]:
    allowed = [
        place.model_dump(mode="json")
        for place in candidates
        if place.place_id not in blocker_place_ids
    ]
    payload = {
        "itinerary": itinerary.model_dump(mode="json"),
        "blocked_place_ids": sorted(blocker_place_ids),
        "candidate_places": allowed,
    }
    return [
        GeminiMessage(
            role="system",
            content=(
                "Replace every blocked place once while preserving all unaffected "
                "items. Use only the supplied candidate place IDs or an explicit "
                "generic activity. Return the complete itinerary."
            ),
        ),
        GeminiMessage(role="user", content=json.dumps(payload, ensure_ascii=False)),
    ]


def _validate_request(request: TripRequest) -> None:
    missing = [
        field
        for field in ("destination", "start_date", "end_date")
        if getattr(request, field) is None
    ]
    if missing:
        raise MissingTripFieldsError(missing)
    assert request.start_date is not None
    assert request.end_date is not None
    if request.end_date < request.start_date:
        raise InvalidTripDatesError()


def _candidate_places(
    destination: PlacesSearchResult,
    candidates: PlacesSearchResult,
) -> list[Place]:
    return _merge_places(destination.places, candidates.places)


def _merge_places(first: list[Place], second: list[Place]) -> list[Place]:
    by_id: dict[str, Place] = {}
    for place in [*first, *second]:
        by_id.setdefault(place.place_id, place)
    return list(by_id.values())


def _prepare_draft(
    draft: Itinerary,
    *,
    request: TripRequest,
    candidate_ids: set[str],
    destination_result: PlacesSearchResult,
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
        for item in day.items:
            if item.kind == "place" and item.place_id not in candidate_ids:
                raise ItineraryGenerationError()
            item.place = None
            item.warnings = []
    draft.destination = request.destination
    draft.destination_location = next(
        (
            place.location
            for place in destination_result.places
            if place.location is not None
        ),
        None,
    )
    draft.weather = []
    draft.warnings = []
    draft.verification_status = "unavailable"
    draft.verified_sources = []
    draft.unavailable_sources = []
    return draft

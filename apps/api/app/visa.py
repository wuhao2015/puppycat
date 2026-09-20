from __future__ import annotations

import asyncio
import json
import logging
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.clients import AppClients
from app.db import cache_get, cache_set
from app.errors import (
    InvalidTripDatesError,
    MissingTripFieldsError,
    VisaCountryResolutionError,
)
from app.external import build_cache_key
from app.external.places import Place
from app.external.search import SearchItem, SearchResult
from app.gemini import GeminiMessage
from app.models import Trip
from app.schemas import (
    VisaChecklist,
    VisaChecklistResponse,
    VisaMaterial,
    VisaOfficialLink,
    VisaSource,
    VisaStep,
)


logger = logging.getLogger(__name__)

VISA_CACHE_TTL_SECONDS = 6 * 60 * 60
VISA_DISCLAIMER = (
    "Visa rules can change and eligibility depends on your circumstances. "
    "Confirm every requirement with the destination's embassy or consulate "
    "before applying or booking travel."
)


class _TextFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str | None = None
    source_url: str | None = None


class _OfficialSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str
    url: str
    content: str
    published_date: str | None = None


class _BooleanFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: bool | None = None
    source_url: str | None = None


class _MaterialDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    category: Literal["required", "optional", "conditional"]
    details: str | None = None
    source_url: str


class _StepDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order: int = Field(ge=1)
    title: str
    description: str
    source_url: str


class _LinkDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    url: str


class _ChecklistDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visa_required: _BooleanFact
    visa_type: _TextFact
    allowed_stay: _TextFact
    processing_time: _TextFact
    fees: _TextFact
    notes: _TextFact
    materials: list[_MaterialDraft] = Field(default_factory=list)
    steps: list[_StepDraft] = Field(default_factory=list)
    official_links: list[_LinkDraft] = Field(default_factory=list)


_VISA_PROMPT = """
You organize visa information for a travel planning application.

Use only the official source excerpts supplied in the user message. Do not use
general knowledge. Every non-null fact, material, step, and link must cite one
of the exact supplied source URLs. If the excerpts do not establish a value,
return null for that value. Never infer that a visa is or is not required.

The passport country, destination country, tourism purpose, and exact trip
length are authoritative request context. Include every supported application
material. Do not apply a fixed item limit. Classify materials as required,
optional, or conditional. Keep fees and processing time null unless an official
excerpt explicitly states them for this context.
""".strip()


async def build_visa_checklist(
    trip: Trip,
    *,
    passport_countries: list[str],
    clients: AppClients,
) -> VisaChecklistResponse:
    missing_fields = [
        field
        for field in ("destination", "start_date", "end_date")
        if getattr(trip, field) is None
    ]
    if missing_fields:
        raise MissingTripFieldsError(missing_fields)
    assert trip.destination is not None
    assert trip.start_date is not None
    assert trip.end_date is not None
    if trip.end_date < trip.start_date:
        raise InvalidTripDatesError()

    destination = await _resolve_destination_country(trip.destination, clients)
    destination_code = destination.country_code
    assert destination_code is not None
    destination_country = _destination_country_name(destination, trip.destination)
    stay_days = (trip.end_date - trip.start_date).days + 1
    passports = list(
        dict.fromkeys(code.strip().upper() for code in passport_countries)
    )
    cache_key = build_cache_key(
        "visa:checklist:v1",
        {
            "passports": passports,
            "destination_country": destination_country,
            "destination_country_code": destination_code,
            "start_date": trip.start_date.isoformat(),
            "end_date": trip.end_date.isoformat(),
        },
    )
    cached = await _cached_checklist(cache_key)
    if cached is not None:
        return cached

    search_results = await asyncio.gather(
        *(
            clients.search.search(
                _search_query(
                    passport_country=passport,
                    destination_country=destination_country,
                    stay_days=stay_days,
                ),
                max_results=10,
            )
            for passport in passports
        )
    )
    checklists = await asyncio.gather(
        *(
            _build_passport_checklist(
                passport_country=passport,
                destination_country=destination_country,
                stay_days=stay_days,
                search_result=search_result,
                clients=clients,
            )
            for passport, search_result in zip(passports, search_results, strict=True)
        )
    )
    response = VisaChecklistResponse(
        destination_country=destination_country,
        destination_country_code=destination_code,
        stay_days=stay_days,
        checklists=list(checklists),
    )
    try:
        await cache_set(
            cache_key,
            response.model_dump(mode="json"),
            ttl_seconds=VISA_CACHE_TTL_SECONDS,
        )
    except SQLAlchemyError:
        logger.warning("Could not persist visa checklist cache entry")
    return response


async def _resolve_destination_country(
    destination: str, clients: AppClients
) -> Place:
    result = await clients.places.search_text(destination, max_results=1)
    if result.status != "available" or not result.places:
        raise VisaCountryResolutionError()
    place = result.places[0]
    if not place.country_code:
        raise VisaCountryResolutionError()
    return place.model_copy(update={"country_code": place.country_code.upper()})


def _destination_country_name(place: Place, destination: str) -> str:
    assert place.country_code is not None
    if place.address and "," in place.address:
        return place.address.rsplit(",", 1)[-1].strip()
    if "," in destination:
        return destination.rsplit(",", 1)[-1].strip()
    return place.name.strip() or place.country_code


async def _build_passport_checklist(
    *,
    passport_country: str,
    destination_country: str,
    stay_days: int,
    search_result: SearchResult,
    clients: AppClients,
) -> VisaChecklist:
    sources = _official_sources(search_result)
    if not sources:
        return _unknown_checklist(
            passport_country=passport_country,
            destination_country=destination_country,
        )

    draft = await clients.gemini.complete_json(
        [
            GeminiMessage(role="system", content=_VISA_PROMPT),
            GeminiMessage(
                role="user",
                content=json.dumps(
                    {
                        "passport_country": passport_country,
                        "destination_country": destination_country,
                        "purpose": "tourism",
                        "stay_days": stay_days,
                        "official_sources": [
                            source.model_dump(mode="json") for source in sources
                        ],
                    },
                    ensure_ascii=False,
                ),
            ),
        ],
        _ChecklistDraft,
    )
    return _ground_draft(
        draft,
        passport_country=passport_country,
        destination_country=destination_country,
        sources=sources,
    )


def _ground_draft(
    draft: _ChecklistDraft,
    *,
    passport_country: str,
    destination_country: str,
    sources: list[_OfficialSource],
) -> VisaChecklist:
    source_by_url = {_canonical_url(source.url): source for source in sources}

    def text_value(fact: _TextFact) -> str | None:
        return fact.value if _is_grounded(fact.source_url, source_by_url) else None

    visa_required = (
        draft.visa_required.value
        if _is_grounded(draft.visa_required.source_url, source_by_url)
        else None
    )
    materials = [
        VisaMaterial(**material.model_dump())
        for material in draft.materials
        if _is_grounded(material.source_url, source_by_url)
    ]
    steps = [
        VisaStep(**step.model_dump())
        for step in sorted(draft.steps, key=lambda item: item.order)
        if _is_grounded(step.source_url, source_by_url)
    ]
    links: list[VisaOfficialLink] = []
    known_link_urls: set[str] = set()
    for link in draft.official_links:
        canonical = _canonical_url(link.url)
        if canonical in source_by_url and canonical not in known_link_urls:
            links.append(VisaOfficialLink(label=link.label, url=link.url))
            known_link_urls.add(canonical)

    cited_urls = {
        _canonical_url(url)
        for url in (
            draft.visa_required.source_url,
            draft.visa_type.source_url,
            draft.allowed_stay.source_url,
            draft.processing_time.source_url,
            draft.fees.source_url,
            draft.notes.source_url,
            *(material.source_url for material in materials),
            *(step.source_url for step in steps),
            *(link.url for link in links),
        )
        if url
    }
    cited_sources = [
        VisaSource(
            title=source.title,
            url=source.url,
            published_date=source.published_date,
        )
        for source in sources
        if _canonical_url(source.url) in cited_urls
    ]
    return VisaChecklist(
        passport_country=passport_country,
        destination_country=destination_country,
        visa_required=visa_required,
        visa_type=text_value(draft.visa_type),
        allowed_stay=text_value(draft.allowed_stay),
        processing_time=text_value(draft.processing_time),
        fees=text_value(draft.fees),
        notes=text_value(draft.notes),
        materials=materials,
        steps=steps,
        official_links=links,
        sources=cited_sources,
        status="available" if cited_sources else "unavailable",
        disclaimer=VISA_DISCLAIMER,
    )


def _unknown_checklist(
    *,
    passport_country: str,
    destination_country: str,
) -> VisaChecklist:
    return VisaChecklist(
        passport_country=passport_country,
        destination_country=destination_country,
        disclaimer=VISA_DISCLAIMER,
    )


def _official_sources(search_result: SearchResult) -> list[_OfficialSource]:
    if search_result.status != "available":
        return []
    sources: list[_OfficialSource] = []
    seen_urls: set[str] = set()
    for item in search_result.results:
        if not _is_official_url(item.url):
            continue
        canonical = _canonical_url(item.url)
        if canonical in seen_urls:
            continue
        seen_urls.add(canonical)
        sources.append(_source(item))
    return sources


def _source(item: SearchItem) -> _OfficialSource:
    return _OfficialSource(
        title=item.title,
        url=item.url,
        content=item.content,
        published_date=item.published_date,
    )


def _is_grounded(
    source_url: str | None, source_by_url: dict[str, _OfficialSource]
) -> bool:
    return bool(source_url and _canonical_url(source_url) in source_by_url)


def _is_official_url(url: str) -> bool:
    hostname = (urlsplit(url).hostname or "").lower()
    if not hostname:
        return False
    labels = hostname.split(".")
    return (
        hostname.endswith(".gov")
        or hostname.endswith(".europa.eu")
        or any(label in {"gov", "gouv", "go", "gc", "govt"} for label in labels[:-1])
    )


def _canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/"),
            parts.query,
            "",
        )
    )


def _search_query(
    *, passport_country: str, destination_country: str, stay_days: int
) -> str:
    return (
        f"current official tourist visa requirements passport {passport_country} "
        f"destination {destination_country} stay {stay_days} days documents "
        "application steps processing time fees"
    )


async def _cached_checklist(key: str) -> VisaChecklistResponse | None:
    try:
        payload = await cache_get(key)
        return (
            VisaChecklistResponse.model_validate(payload)
            if payload is not None
            else None
        )
    except (SQLAlchemyError, ValidationError):
        logger.warning("Ignoring unavailable or invalid visa checklist cache entry")
        return None

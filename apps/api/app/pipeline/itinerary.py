from __future__ import annotations

import asyncio
import json

from pydantic import ValidationError

from app.deps import Deps
from app.llm import ModelTier
from app.pipeline.verify import _geocode, verify_itinerary
from app.schemas import (
    Itinerary,
    Place,
    TripRequest,
    Warning,
    WarningSeverity,
)

_MAX_CANDIDATES = 40

_ITINERARY_SHAPE = """
Return a JSON object with this exact shape:
{
  "destination": str,
  "start_date": "YYYY-MM-DD",
  "end_date": "YYYY-MM-DD",
  "days": [
    {
      "date": "YYYY-MM-DD",
      "title": str,
      "summary": str,
      "items": [
        {
          "name": str,
          "place_id": str | null,   // MUST be a place_id from the candidate list when the item is one of those venues
          "category": str,          // e.g. "museum", "restaurant", "walk"
          "description": str,
          "start_time": "HH:MM",
          "end_time": "HH:MM"
        }
      ]
    }
  ],
  "warnings": []
}
Only reference real venues from the candidate list (use their exact place_id). You may add
generic activities (e.g. "lunch near the harbour") without a place_id. Do not invent place_ids.
"""


async def generate_itinerary(req: TripRequest, deps: Deps) -> Itinerary:
    """Run the deterministic pipeline:
    parse -> candidate POIs -> draft -> real-time verify -> re-rank/finalise.
    """
    location = await _geocode(req.destination, deps)
    candidates = await _gather_candidates(req, deps)

    draft = await _draft_itinerary(req, candidates, deps)
    verified = await verify_itinerary(draft, deps, location=location)
    final = await _finalise(req, verified, candidates, deps)
    return final


async def _gather_candidates(req: TripRequest, deps: Deps) -> list[Place]:
    if not deps.places.is_configured():
        return []

    queries = [f"top attractions in {req.destination}", f"best restaurants in {req.destination}"]
    queries += [f"{interest} in {req.destination}" for interest in req.interests]

    async def run(q: str) -> list[Place]:
        try:
            return await deps.places.text_search(q, max_results=8)
        except Exception:  # noqa: BLE001 - skip a failing query, keep the rest
            return []

    results = await asyncio.gather(*(run(q) for q in queries))

    seen: dict[str, Place] = {}
    for batch in results:
        for place in batch:
            if place.place_id and place.place_id not in seen:
                seen[place.place_id] = place
    return list(seen.values())[:_MAX_CANDIDATES]


def _candidate_digest(candidates: list[Place]) -> str:
    lines = []
    for p in candidates:
        rating = f"{p.rating}\u2605" if p.rating else "no rating"
        lines.append(
            f"- place_id={p.place_id} | {p.name} | {','.join(p.types[:3]) or 'n/a'} "
            f"| {rating} | {p.address or ''}"
        )
    return "\n".join(lines) if lines else "(no candidate venues available)"


async def _draft_itinerary(req: TripRequest, candidates: list[Place], deps: Deps) -> Itinerary:
    system = (
        "You are a meticulous travel planner. Build a realistic day-by-day itinerary that "
        "respects the traveller's pace, groups nearby venues on the same day to minimise "
        "transit, and includes meals. Ground every named venue in the provided candidate list."
    )
    user = (
        f"Trip request:\n"
        f"- destination: {req.destination}\n"
        f"- dates: {req.start_date} to {req.end_date}\n"
        f"- pace: {req.pace.value}\n"
        f"- travelers: {req.travelers}\n"
        f"- budget: {req.budget or 'unspecified'}\n"
        f"- interests: {', '.join(req.interests) or 'general sightseeing'}\n"
        f"- notes: {req.notes or 'none'}\n\n"
        f"Candidate venues (use exact place_id values):\n{_candidate_digest(candidates)}\n\n"
        f"{_ITINERARY_SHAPE}"
    )
    raw = await deps.llm.complete_json(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        tier=ModelTier.CHEAP,
    )
    return await _validate_or_repair(raw, req, deps)


async def _finalise(
    req: TripRequest, verified: Itinerary, candidates: list[Place], deps: Deps
) -> Itinerary:
    """Final synthesis pass: use verification warnings to drop/replace blocked
    venues and attach reservation links, producing the user-facing itinerary."""
    blockers = _collect_blockers(verified)
    if not blockers:
        _backfill_reservation_links(verified, candidates)
        return verified

    system = (
        "You are finalising a travel itinerary. Some venues were flagged by a real-time "
        "verification pass as closed or disrupted. Remove or replace every BLOCKER venue using "
        "only the candidate list, keep the rest, preserve timing and flow, and keep each item's "
        "place_id accurate. Do not reintroduce removed venues."
    )
    user = (
        f"Current itinerary JSON:\n{verified.model_dump_json()}\n\n"
        f"Blocking issues to resolve:\n{json.dumps(blockers, indent=2)}\n\n"
        f"Replacement candidates:\n{_candidate_digest(candidates)}\n\n"
        f"{_ITINERARY_SHAPE}"
    )
    raw = await deps.llm.complete_json(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        tier=ModelTier.SYNTHESIS,
    )
    final = await _validate_or_repair(raw, req, deps)

    # Re-verify replaced venues once so new picks are also grounded, then carry
    # forward any unresolved trip-level warnings.
    final = await verify_itinerary(final, deps)
    _backfill_reservation_links(final, candidates)
    final.warnings = _dedupe_warnings(verified.warnings + final.warnings)
    return final


def _collect_blockers(itinerary: Itinerary) -> list[dict]:
    blockers = []
    for day in itinerary.days:
        for item in day.items:
            for w in item.warnings:
                if w.severity is WarningSeverity.BLOCKER:
                    blockers.append({"date": day.date, "item": item.name, "issue": w.message})
    return blockers


def _backfill_reservation_links(itinerary: Itinerary, candidates: list[Place]) -> None:
    by_id = {p.place_id: p for p in candidates}
    for day in itinerary.days:
        for item in day.items:
            if item.place_id and item.place_id in by_id:
                place = by_id[item.place_id]
                item.location = item.location or place.location
                item.website = item.website or place.website
                item.address = item.address or place.address
                if not item.reservation_url:
                    item.reservation_url = place.website or place.google_maps_uri


def _dedupe_warnings(warnings: list[Warning]) -> list[Warning]:
    seen: set[tuple] = set()
    out: list[Warning] = []
    for w in warnings:
        key = (w.severity, w.message, w.related_item)
        if key not in seen:
            seen.add(key)
            out.append(w)
    return out


async def _validate_or_repair(raw: dict, req: TripRequest, deps: Deps) -> Itinerary:
    """Validate LLM JSON against the Itinerary schema; repair once on failure."""
    raw.setdefault("destination", req.destination)
    raw.setdefault("start_date", req.start_date)
    raw.setdefault("end_date", req.end_date)
    try:
        return Itinerary.model_validate(raw)
    except ValidationError as exc:
        repair_prompt = (
            "The following JSON failed validation against the required itinerary schema. "
            "Fix it so it validates. Return only corrected JSON.\n\n"
            f"Validation errors:\n{exc}\n\n"
            f"JSON:\n{json.dumps(raw)}\n\n{_ITINERARY_SHAPE}"
        )
        fixed = await deps.llm.complete_json(
            [{"role": "user", "content": repair_prompt}], tier=ModelTier.CHEAP
        )
        fixed.setdefault("destination", req.destination)
        fixed.setdefault("start_date", req.start_date)
        fixed.setdefault("end_date", req.end_date)
        return Itinerary.model_validate(fixed)

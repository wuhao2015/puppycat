from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import ValidationError

from app.deps import Deps
from app.llm import ModelTier
from app.schemas import DISCLAIMER, VisaNotice

_STATIC_PATH = Path(__file__).resolve().parent.parent / "data" / "visa_static.json"

_NOTICE_SHAPE = """
Return a JSON object with this exact shape:
{
  "visa_required": bool | null,
  "allowed_stay": str | null,        // e.g. "Up to 90 days for tourism"
  "summary": str | null,             // one or two plain sentences, no fluff
  "key_documents": [str],            // at most 3 essentials, e.g. "Passport valid 6+ months"
  "official_link": str | null
}
Keep it short: this is a reminder, not a full application guide. Base every field on the
provided sources/hint. Use null when unsure rather than guessing fees or processing times.
"""


@lru_cache
def _static_data() -> dict:
    try:
        return json.loads(_STATIC_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _static_hint(passport_country: str, destination: str) -> dict | None:
    data = _static_data()
    key = f"{passport_country.upper()}:{destination.upper()}"
    return data.get(key)


async def build_visa_notice(
    passport_country: str,
    destination: str,
    deps: Deps,
    *,
    purpose: str = "tourism",
    duration_days: int = 14,
) -> VisaNotice:
    """Produce a concise, grounded visa reminder for one passport x destination."""
    sources: list[str] = []
    snippets: list[str] = []

    if deps.web_search.is_configured():
        query = (
            f"{passport_country} passport visa requirements for {destination} "
            f"{purpose} stay {duration_days} days official government"
        )
        try:
            results = await deps.web_search.search(query, max_results=4, recency_days=180)
        except Exception:  # noqa: BLE001 - reminders are best-effort
            results = []
        for r in results:
            sources.append(r.url)
            snippets.append(f"[{r.title}]({r.url})\n{r.content}")

    hint = _static_hint(passport_country, destination)
    hint_text = json.dumps(hint, indent=2) if hint else "(no curated entry)"
    sources_text = "\n\n".join(snippets) if snippets else "(no live sources retrieved)"

    system = (
        "You are a careful visa-requirements assistant. Give a short, practical reminder "
        "grounded strictly in the provided sources and curated hint. Never fabricate fees or "
        "processing times. Prefer official government sources."
    )
    user = (
        f"Passport: {passport_country}\nDestination: {destination}\n"
        f"Purpose: {purpose}\nIntended stay: {duration_days} days\n\n"
        f"Curated hint:\n{hint_text}\n\n"
        f"Live sources:\n{sources_text}\n\n{_NOTICE_SHAPE}"
    )

    try:
        raw = await deps.llm.complete_json(
            [{"role": "system", "content": system}, {"role": "user", "content": user}],
            tier=ModelTier.CHEAP,
        )
    except Exception:  # noqa: BLE001 - degrade to whatever the static hint offers
        raw = {}

    notice = _coerce_notice(raw, passport_country, destination, hint, sources)
    return notice


def _coerce_notice(
    raw: dict,
    passport_country: str,
    destination: str,
    hint: dict | None,
    sources: list[str],
) -> VisaNotice:
    raw = dict(raw or {})
    raw["passport_country"] = passport_country
    raw["destination_country"] = destination

    if hint:
        raw.setdefault("visa_required", hint.get("visa_required"))
        raw.setdefault("allowed_stay", hint.get("allowed_stay"))
        if not raw.get("key_documents"):
            raw["key_documents"] = [
                d["name"] for d in hint.get("documents", []) if d.get("required")
            ][:3]
        if not raw.get("official_link"):
            links = hint.get("official_links") or []
            raw["official_link"] = links[0] if links else None

    if not raw.get("official_link") and sources:
        raw["official_link"] = sources[0]

    raw["disclaimer"] = DISCLAIMER
    try:
        return VisaNotice.model_validate(raw)
    except ValidationError:
        return VisaNotice(
            passport_country=passport_country,
            destination_country=destination,
        )

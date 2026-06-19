from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import ValidationError

from app.deps import Deps, get_current_user, get_deps
from app.llm import ModelTier
from app.schemas import DISCLAIMER, VisaChecklist, VisaRequest

router = APIRouter(prefix="/api", tags=["visa"])

_STATIC_PATH = Path(__file__).resolve().parent.parent / "data" / "visa_static.json"

_VISA_SHAPE = """
Return a JSON object with this exact shape:
{
  "passport_country": str,
  "destination_country": str,
  "visa_required": bool | null,
  "visa_type": str | null,
  "allowed_stay": str | null,
  "processing_time": str | null,
  "fees": str | null,
  "documents": [{"name": str, "detail": str | null, "required": bool}],
  "steps": [str],
  "official_links": [str]
}
Base every field on the provided sources. If unsure about a field, use null rather than guessing.
"""


@lru_cache
def _static_data() -> dict:
    try:
        return json.loads(_STATIC_PATH.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _static_hint(req: VisaRequest) -> dict | None:
    data = _static_data()
    # Match when the caller passes ISO-style codes, e.g. "US" and "JP".
    key = f"{req.passport_country.upper()}:{req.destination_country.upper()}"
    return data.get(key)


@router.post(
    "/visa-checklist", response_model=VisaChecklist, dependencies=[Depends(get_current_user)]
)
async def visa_checklist(
    req: VisaRequest, deps: Deps = Depends(get_deps)
) -> VisaChecklist:
    sources: list[str] = []
    snippets: list[str] = []

    if deps.web_search.is_configured():
        query = (
            f"{req.passport_country} passport visa requirements for {req.destination_country} "
            f"{req.purpose} stay {req.duration_days} days official government"
        )
        try:
            results = await deps.web_search.search(query, max_results=5, recency_days=180)
        except Exception:  # noqa: BLE001 - fall back to static/LLM knowledge
            results = []
        for r in results:
            sources.append(r.url)
            snippets.append(f"[{r.title}]({r.url})\n{r.content}")

    hint = _static_hint(req)
    hint_text = json.dumps(hint, indent=2) if hint else "(no curated entry)"
    sources_text = "\n\n".join(snippets) if snippets else "(no live sources retrieved)"

    system = (
        "You are a careful visa-requirements assistant. Summarise requirements strictly from "
        "the provided sources and curated hint. Never fabricate fees or processing times. "
        "Prefer official government sources."
    )
    user = (
        f"Passport: {req.passport_country}\nDestination: {req.destination_country}\n"
        f"Purpose: {req.purpose}\nIntended stay: {req.duration_days} days\n\n"
        f"Curated hint:\n{hint_text}\n\n"
        f"Live sources:\n{sources_text}\n\n{_VISA_SHAPE}"
    )

    raw = await deps.llm.complete_json(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        tier=ModelTier.CHEAP,
    )
    raw.setdefault("passport_country", req.passport_country)
    raw.setdefault("destination_country", req.destination_country)

    try:
        checklist = VisaChecklist.model_validate(raw)
    except ValidationError:
        checklist = VisaChecklist(
            passport_country=req.passport_country,
            destination_country=req.destination_country,
        )

    # Merge source links discovered via search with any the model surfaced.
    merged_links = list(dict.fromkeys(checklist.official_links + sources))
    checklist.official_links = [s for s in merged_links if s][:8]
    checklist.sources = sources[:8]
    checklist.disclaimer = DISCLAIMER
    return checklist

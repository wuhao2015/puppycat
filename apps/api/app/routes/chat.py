from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from app.deps import Deps, get_current_user, get_deps
from app.llm import ModelTier
from app.schemas import ChatRequest

router = APIRouter(prefix="/api", tags=["chat"])

_SYSTEM = (
    "You are Puppycat, a travel planning assistant. Your edge over a generic chatbot is that "
    "you ground answers in real, current data. Use the provided context (venues, opening hours, "
    "recent web findings) when relevant, cite venue names, and link reservation/official pages "
    "instead of booking anything yourself. If the context suggests a closure or disruption, warn "
    "the user. Be concise and practical."
)


async def _build_context(message: str, deps: Deps) -> str:
    """Lightweight retrieval step that reuses the itinerary data sources."""
    blocks: list[str] = []

    if deps.places.is_configured():
        try:
            places = await deps.places.text_search(message, max_results=5)
        except Exception:  # noqa: BLE001 - context is best-effort
            places = []
        for p in places:
            status = p.business_status.value
            hours = "; ".join(f"{d}: {h}" for d, h in list(p.opening_hours.items())[:2])
            blocks.append(
                f"VENUE {p.name} | status={status} | rating={p.rating} "
                f"| {p.address or ''} | {hours} | {p.website or ''}"
            )

    if deps.web_search.is_configured():
        try:
            results = await deps.web_search.search(message, max_results=3, recency_days=14)
        except Exception:  # noqa: BLE001
            results = []
        for r in results:
            blocks.append(f"WEB {r.title} | {r.url}\n{r.content}")

    return "\n".join(blocks) if blocks else "(no external context retrieved)"


@router.post("/chat", dependencies=[Depends(get_current_user)])
async def chat(req: ChatRequest, deps: Deps = Depends(get_deps)) -> StreamingResponse:
    last_user = next(
        (m.content for m in reversed(req.messages) if m.role == "user"), ""
    )
    context = await _build_context(last_user, deps)

    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "system", "content": f"Context retrieved for this turn:\n{context}"},
    ]
    messages += [{"role": m.role, "content": m.content} for m in req.messages]

    async def token_stream() -> AsyncIterator[str]:
        async for chunk in deps.llm.stream(messages, tier=ModelTier.CHEAP):
            yield chunk

    return StreamingResponse(token_stream(), media_type="text/plain; charset=utf-8")

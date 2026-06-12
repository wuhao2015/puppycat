from __future__ import annotations

import enum
import json
import threading
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from datetime import date
from typing import Any

from app.config import Settings, get_settings
from app.errors import BudgetExceededError, ConfigurationError, UpstreamUnavailableError


class ModelTier(str, enum.Enum):
    """Which model to use. CHEAP handles parsing/verification reasoning,
    SYNTHESIS handles the final user-facing itinerary."""

    CHEAP = "cheap"
    SYNTHESIS = "synthesis"


# Rough per-1M-token USD prices used only for budget estimation, not billing.
# Keyed by model name; unknown models fall back to a conservative default.
_PRICE_PER_1M = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
}
_DEFAULT_PRICE = (2.50, 10.00)


class _DailyBudget:
    """Tracks estimated spend per calendar day (UTC) and refuses overspend.

    In-memory is sufficient for the single-process v1; the interface leaves
    room to back this with the database when running multiple workers.
    """

    def __init__(self, cap_usd: float) -> None:
        self._cap = cap_usd
        self._day = date.today()
        self._spent = 0.0
        self._lock = threading.Lock()

    def _roll_day(self) -> None:
        today = date.today()
        if today != self._day:
            self._day = today
            self._spent = 0.0

    def check(self) -> None:
        with self._lock:
            self._roll_day()
            if self._spent >= self._cap:
                raise BudgetExceededError(
                    f"Daily LLM budget of ${self._cap:.2f} reached; try again tomorrow."
                )

    def record(self, model: str, prompt_tokens: int, completion_tokens: int) -> None:
        in_price, out_price = _PRICE_PER_1M.get(model, _DEFAULT_PRICE)
        cost = (prompt_tokens * in_price + completion_tokens * out_price) / 1_000_000
        with self._lock:
            self._roll_day()
            self._spent += cost

    @property
    def spent_today(self) -> float:
        with self._lock:
            self._roll_day()
            return self._spent


class LLMProvider(ABC):
    """Provider-agnostic LLM surface used across the app."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.budget = _DailyBudget(settings.daily_llm_budget_usd)

    def model_for(self, tier: ModelTier) -> str:
        return (
            self.settings.llm_cheap_model
            if tier is ModelTier.CHEAP
            else self.settings.llm_synthesis_model
        )

    @abstractmethod
    async def complete(
        self, messages: list[dict[str, Any]], *, tier: ModelTier, temperature: float = 0.4
    ) -> str: ...

    @abstractmethod
    async def complete_json(
        self, messages: list[dict[str, Any]], *, tier: ModelTier, temperature: float = 0.2
    ) -> dict[str, Any]: ...

    @abstractmethod
    def stream(
        self,
        messages: list[dict[str, Any]],
        *,
        tier: ModelTier,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]: ...


class OpenAIProvider(LLMProvider):
    def __init__(self, settings: Settings) -> None:
        super().__init__(settings)
        if not settings.openai_api_key:
            raise ConfigurationError("OPENAI_API_KEY is not set.")
        from openai import AsyncOpenAI

        kwargs: dict[str, Any] = {"api_key": settings.openai_api_key}
        if settings.openai_base_url:
            kwargs["base_url"] = settings.openai_base_url
        self._client = AsyncOpenAI(**kwargs)

    async def complete(
        self, messages: list[dict[str, Any]], *, tier: ModelTier, temperature: float = 0.4
    ) -> str:
        self.budget.check()
        model = self.model_for(tier)
        try:
            resp = await self._client.chat.completions.create(
                model=model, messages=messages, temperature=temperature
            )
        except Exception as exc:  # noqa: BLE001 - surface upstream failures cleanly
            raise UpstreamUnavailableError(f"LLM request failed: {exc}") from exc
        self._record(model, resp)
        return resp.choices[0].message.content or ""

    async def complete_json(
        self, messages: list[dict[str, Any]], *, tier: ModelTier, temperature: float = 0.2
    ) -> dict[str, Any]:
        self.budget.check()
        model = self.model_for(tier)
        try:
            resp = await self._client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                response_format={"type": "json_object"},
            )
        except Exception as exc:  # noqa: BLE001
            raise UpstreamUnavailableError(f"LLM request failed: {exc}") from exc
        self._record(model, resp)
        content = resp.choices[0].message.content or "{}"
        return json.loads(content)

    async def stream(
        self,
        messages: list[dict[str, Any]],
        *,
        tier: ModelTier,
        tools: list[dict[str, Any]] | None = None,
    ) -> AsyncIterator[str]:
        self.budget.check()
        model = self.model_for(tier)
        kwargs: dict[str, Any] = {"model": model, "messages": messages, "stream": True}
        if tools:
            kwargs["tools"] = tools
        try:
            stream = await self._client.chat.completions.create(**kwargs)
            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta and delta.content:
                    yield delta.content
        except Exception as exc:  # noqa: BLE001
            raise UpstreamUnavailableError(f"LLM stream failed: {exc}") from exc

    def _record(self, model: str, resp: Any) -> None:
        usage = getattr(resp, "usage", None)
        if usage is not None:
            self.budget.record(
                model,
                getattr(usage, "prompt_tokens", 0),
                getattr(usage, "completion_tokens", 0),
            )


def build_llm_provider(settings: Settings | None = None) -> LLMProvider:
    settings = settings or get_settings()
    if settings.llm_provider == "openai":
        return OpenAIProvider(settings)
    raise ConfigurationError(f"Unknown LLM provider: {settings.llm_provider}")

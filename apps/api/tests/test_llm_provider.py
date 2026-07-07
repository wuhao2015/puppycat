from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.errors import UpstreamUnavailableError
from app.llm.provider import GeminiProvider, ModelTier


def _provider(monkeypatch: pytest.MonkeyPatch, responses: list[object]) -> GeminiProvider:
    types_module = SimpleNamespace(GenerateContentConfig=lambda **kwargs: kwargs)
    genai_module = ModuleType("google.genai")
    genai_module.types = types_module
    google_module = ModuleType("google")
    google_module.genai = genai_module
    monkeypatch.setitem(sys.modules, "google", google_module)
    monkeypatch.setitem(sys.modules, "google.genai", genai_module)

    provider = object.__new__(GeminiProvider)
    provider.settings = SimpleNamespace(
        llm_cheap_model="primary",
        llm_synthesis_model="primary",
        llm_fallback_model_list=["fallback"],
    )
    generate_content = AsyncMock(side_effect=responses)
    provider._client = SimpleNamespace(
        aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    )
    provider._record_usage = lambda _model, _resp: None
    return provider


@pytest.mark.asyncio
async def test_gemini_json_falls_back_when_primary_returns_invalid_json(monkeypatch):
    provider = _provider(
        monkeypatch,
        [SimpleNamespace(text="not JSON"), SimpleNamespace(text='{"destination": "Kyoto"}')],
    )

    model, text = await provider._generate_content_with_fallback(
        [{"role": "user", "content": "Plan a trip"}],
        tier=ModelTier.CHEAP,
        temperature=0.2,
        json_mode=True,
    )

    assert model == "fallback"
    assert text == '{"destination": "Kyoto"}'
    assert provider._client.aio.models.generate_content.await_count == 2


@pytest.mark.asyncio
async def test_gemini_json_returns_structured_upstream_error_when_all_models_are_invalid(
    monkeypatch,
):
    provider = _provider(
        monkeypatch,
        [SimpleNamespace(text=""), SimpleNamespace(text="[]")],
    )

    with pytest.raises(UpstreamUnavailableError, match="every configured model"):
        await provider._generate_content_with_fallback(
            [{"role": "user", "content": "Plan a trip"}],
            tier=ModelTier.CHEAP,
            temperature=0.2,
            json_mode=True,
        )

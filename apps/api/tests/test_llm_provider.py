from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.errors import ConfigurationError, UpstreamUnavailableError
from app.llm.provider import GeminiProvider, ModelTier, OpenAIProvider


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


def _openai_settings(**overrides: object) -> SimpleNamespace:
    values = {
        "daily_llm_budget_usd": 2.0,
        "openai_api_key": "sk-test",
        "openai_base_url": "",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _install_openai_stub(monkeypatch: pytest.MonkeyPatch) -> dict[str, object]:
    captured: dict[str, object] = {}

    class AsyncOpenAI:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    openai_module = ModuleType("openai")
    openai_module.AsyncOpenAI = AsyncOpenAI
    monkeypatch.setitem(sys.modules, "openai", openai_module)
    return captured


def test_openai_provider_rejects_base_url_without_protocol():
    with pytest.raises(ConfigurationError, match="OPENAI_BASE_URL"):
        OpenAIProvider(_openai_settings(openai_base_url="api.openai.com/v1"))


def test_openai_provider_ignores_blank_base_url(monkeypatch):
    captured = _install_openai_stub(monkeypatch)

    OpenAIProvider(_openai_settings(openai_base_url="   "))

    assert captured == {"api_key": "sk-test", "base_url": "https://api.openai.com/v1"}


def test_openai_provider_passes_valid_base_url(monkeypatch):
    captured = _install_openai_stub(monkeypatch)

    OpenAIProvider(_openai_settings(openai_base_url="https://api.openai.com/v1"))

    assert captured == {
        "api_key": "sk-test",
        "base_url": "https://api.openai.com/v1",
    }


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

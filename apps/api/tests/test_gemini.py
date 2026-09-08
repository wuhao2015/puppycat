from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from google.genai import errors
from pydantic import BaseModel

from app.db import cache_get
from app.errors import (
    GeminiRequestError,
    GeminiSafetyError,
    GeminiStreamInterruptedError,
)
from app.gemini import GeminiClient, GeminiMessage, MODEL_STATE_CACHE_KEY


PRIMARY_MODEL = "gemini-2.5-flash"
BACKUP_MODEL = "gemini-2.5-pro"


class _JsonResult(BaseModel):
    answer: str


def _response(
    *,
    parsed: object | None = None,
    text: str | None = None,
    block_reason: str | None = None,
) -> SimpleNamespace:
    feedback = (
        SimpleNamespace(block_reason=block_reason)
        if block_reason is not None
        else None
    )
    return SimpleNamespace(
        parsed=parsed,
        text=text,
        prompt_feedback=feedback,
        candidates=[],
    )


def _api_error(code: int) -> errors.APIError:
    status = {
        400: "INVALID_ARGUMENT",
        401: "UNAUTHENTICATED",
        403: "PERMISSION_DENIED",
        429: "RESOURCE_EXHAUSTED",
        503: "UNAVAILABLE",
    }[code]
    return errors.APIError(
        code,
        {"error": {"message": "fixed test error", "status": status}},
    )


class _FakeModels:
    def __init__(
        self,
        *,
        completions: dict[str, list[object]] | None = None,
        streams: dict[str, list[object]] | None = None,
    ) -> None:
        self.completions = completions or {}
        self.streams = streams or {}
        self.complete_calls: list[dict[str, Any]] = []
        self.stream_calls: list[dict[str, Any]] = []

    async def generate_content(self, **kwargs: Any) -> object:
        self.complete_calls.append(kwargs)
        outcome = self.completions[kwargs["model"]].pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    async def generate_content_stream(self, **kwargs: Any) -> AsyncIterator[object]:
        self.stream_calls.append(kwargs)
        events = self.streams[kwargs["model"]]

        async def iterate() -> AsyncIterator[object]:
            for event in events:
                if isinstance(event, BaseException):
                    raise event
                yield event

        return iterate()


class _FakeAsyncClient:
    def __init__(self, models: _FakeModels) -> None:
        self.models = models

    async def aclose(self) -> None:
        pass


class _FakeSdk:
    def __init__(self, models: _FakeModels) -> None:
        self.aio = _FakeAsyncClient(models)

    def close(self) -> None:
        pass


def _make_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    completions: dict[str, list[object]] | None = None,
    streams: dict[str, list[object]] | None = None,
) -> tuple[GeminiClient, _FakeModels]:
    models = _FakeModels(completions=completions, streams=streams)
    sdk = _FakeSdk(models)
    monkeypatch.setattr("app.gemini.genai.Client", lambda **kwargs: sdk)

    client = GeminiClient(api_key="test-key", default_model=PRIMARY_MODEL)
    client.eligible_models = [PRIMARY_MODEL, BACKUP_MODEL]
    client._next_catalog_refresh_at = datetime.now(timezone.utc) + timedelta(days=1)
    return client, models


def _messages() -> list[GeminiMessage]:
    return [
        GeminiMessage(role="system", content="You are Puppycat."),
        GeminiMessage(role="user", content="Plan Kyoto."),
        GeminiMessage(role="assistant", content="How many days?"),
        GeminiMessage(role="user", content="Three days."),
    ]


async def test_complete_json_calls_only_active_model_with_expected_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, models = _make_client(
        monkeypatch,
        completions={PRIMARY_MODEL: [_response(parsed={"answer": "ready"})]},
    )

    result = await client.complete_json(_messages(), _JsonResult)

    assert result == _JsonResult(answer="ready")
    assert [call["model"] for call in models.complete_calls] == [PRIMARY_MODEL]
    call = models.complete_calls[0]
    assert call["config"].response_mime_type == "application/json"
    assert call["config"].response_schema is _JsonResult
    assert call["config"].system_instruction == "You are Puppycat."
    assert [content.role for content in call["contents"]] == [
        "user",
        "model",
        "user",
    ]
    assert [content.parts[0].text for content in call["contents"]] == [
        "Plan Kyoto.",
        "How many days?",
        "Three days.",
    ]


async def test_retryable_error_falls_back_promotes_and_persists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, models = _make_client(
        monkeypatch,
        completions={
            PRIMARY_MODEL: [_api_error(429)],
            BACKUP_MODEL: [
                _response(parsed={"answer": "fallback"}),
                _response(parsed={"answer": "next request"}),
            ],
        },
    )

    result = await client.complete_json(_messages(), _JsonResult)

    assert result.answer == "fallback"
    assert [call["model"] for call in models.complete_calls] == [
        PRIMARY_MODEL,
        BACKUP_MODEL,
    ]
    assert client.active_model == BACKUP_MODEL
    cached_state = await cache_get(MODEL_STATE_CACHE_KEY)
    assert cached_state is not None
    assert cached_state["active_model"] == BACKUP_MODEL

    next_result = await client.complete_json(_messages(), _JsonResult)
    assert next_result.answer == "next request"
    assert [call["model"] for call in models.complete_calls] == [
        PRIMARY_MODEL,
        BACKUP_MODEL,
        BACKUP_MODEL,
    ]


@pytest.mark.parametrize(
    ("status_code", "expected_error_code"),
    [
        (400, "gemini_invalid_request"),
        (401, "gemini_authentication_failed"),
        (403, "gemini_authentication_failed"),
    ],
)
async def test_request_errors_do_not_fall_back(
    monkeypatch: pytest.MonkeyPatch,
    status_code: int,
    expected_error_code: str,
) -> None:
    client, models = _make_client(
        monkeypatch,
        completions={PRIMARY_MODEL: [_api_error(status_code)]},
    )

    with pytest.raises(GeminiRequestError) as raised:
        await client.complete_json(_messages(), _JsonResult)

    assert raised.value.error_code == expected_error_code
    assert [call["model"] for call in models.complete_calls] == [PRIMARY_MODEL]


async def test_safety_block_does_not_fall_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, models = _make_client(
        monkeypatch,
        completions={
            PRIMARY_MODEL: [
                _response(parsed={"answer": "blocked"}, block_reason="SAFETY")
            ]
        },
    )

    with pytest.raises(GeminiSafetyError):
        await client.complete_json(_messages(), _JsonResult)

    assert [call["model"] for call in models.complete_calls] == [PRIMARY_MODEL]


async def test_stream_fallback_depends_on_whether_output_started(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before_output, before_models = _make_client(
        monkeypatch,
        streams={
            PRIMARY_MODEL: [_api_error(503)],
            BACKUP_MODEL: [_response(text="fallback response")],
        },
    )

    chunks = [chunk async for chunk in before_output.stream_text(_messages())]

    assert chunks == ["fallback response"]
    assert [call["model"] for call in before_models.stream_calls] == [
        PRIMARY_MODEL,
        BACKUP_MODEL,
    ]

    after_output, after_models = _make_client(
        monkeypatch,
        streams={
            PRIMARY_MODEL: [_response(text="partial"), _api_error(503)],
            BACKUP_MODEL: [_response(text="must not be used")],
        },
    )
    stream = after_output.stream_text(_messages())

    assert await anext(stream) == "partial"
    with pytest.raises(GeminiStreamInterruptedError):
        await anext(stream)
    assert [call["model"] for call in after_models.stream_calls] == [PRIMARY_MODEL]

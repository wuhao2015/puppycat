from __future__ import annotations

import json
from collections.abc import AsyncGenerator, Awaitable, Callable, Sequence
from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from httpx import AsyncClient, Response

from app.db import SessionLocal
from app.errors import GeminiStreamInterruptedError, GeminiUnavailableError
from app.gemini import GeminiMessage
from app.main import app
from app.models import Trip
from app.schemas import ChatMessage


class _FakeGemini:
    def __init__(
        self,
        events: Sequence[str | Exception],
        *,
        on_start: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self.events = events
        self.on_start = on_start
        self.calls: list[list[GeminiMessage]] = []

    async def stream_text(
        self,
        messages: Sequence[GeminiMessage],
    ) -> AsyncGenerator[str, None]:
        self.calls.append(list(messages))
        if self.on_start is not None:
            await self.on_start()
        for event in self.events:
            if isinstance(event, Exception):
                raise event
            yield event


async def _register(client: AsyncClient) -> dict[str, str]:
    response = await client.post(
        "/api/auth/register",
        json={
            "email": f"chat-{uuid4()}@example.com",
            "password": "correct-horse-battery-staple",
            "signup_code": "test-signup-code",
        },
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _events(response: Response) -> list[dict[str, object]]:
    return [json.loads(line) for line in response.text.splitlines() if line]


def _install_gemini(monkeypatch: pytest.MonkeyPatch, gemini: _FakeGemini) -> None:
    monkeypatch.setattr(
        app.state,
        "clients",
        SimpleNamespace(gemini=gemini),
        raising=False,
    )


async def _trip_messages(
    client: AsyncClient,
    trip_id: str,
    headers: dict[str, str],
) -> list[dict[str, object]]:
    response = await client.get(f"/api/trips/{trip_id}", headers=headers)
    assert response.status_code == 200
    return response.json()["chat_messages"]


async def test_chat_streams_context_and_saves_complete_reply(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = await _register(client)
    trip = (await client.post("/api/trips", headers=headers)).json()
    older_messages = [
        ChatMessage(
            role="user",
            content="I like gardens.",
            ts=datetime(2026, 9, 1, tzinfo=timezone.utc),
        ).model_dump(mode="json"),
        ChatMessage(
            role="assistant",
            content="What pace do you prefer?",
            ts=datetime(2026, 9, 1, 0, 1, tzinfo=timezone.utc),
        ).model_dump(mode="json"),
    ]
    async with SessionLocal() as session:
        stored_trip = await session.get(Trip, trip["id"])
        assert stored_trip is not None
        stored_trip.destination = "Kyoto, Japan"
        stored_trip.start_date = date(2026, 10, 1)
        stored_trip.end_date = date(2026, 10, 3)
        stored_trip.preferences = {"pace": "relaxed"}
        stored_trip.chat_messages = older_messages
        await session.commit()

    async def assert_user_was_saved_before_gemini() -> None:
        async with SessionLocal() as session:
            stored_trip = await session.get(Trip, trip["id"])
            assert stored_trip is not None
            assert stored_trip.chat_messages[-1]["role"] == "user"
            assert stored_trip.chat_messages[-1]["content"] == "Local food too."

    gemini = _FakeGemini(
        ["Great — ", "I will keep the pace relaxed."],
        on_start=assert_user_was_saved_before_gemini,
    )
    _install_gemini(monkeypatch, gemini)

    response = await client.post(
        f"/api/trips/{trip['id']}/chat",
        headers=headers,
        json={"content": "  Local food too.  "},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    events = _events(response)
    assert [event["type"] for event in events] == ["chunk", "chunk", "done"]
    assert [event["content"] for event in events[:2]] == [
        "Great — ",
        "I will keep the pace relaxed.",
    ]
    assert events[-1]["message"]["content"] == (
        "Great — I will keep the pace relaxed."
    )

    assert len(gemini.calls) == 1
    context = gemini.calls[0]
    assert [message.role for message in context] == [
        "system",
        "system",
        "user",
        "assistant",
        "user",
    ]
    trip_context = json.loads(context[1].content.split("\n", 1)[1])
    assert trip_context == {
        "destination": "Kyoto, Japan",
        "end_date": "2026-10-03",
        "preferences": {"pace": "relaxed"},
        "start_date": "2026-10-01",
        "title": "New trip",
    }
    assert context[-1].content == "Local food too."

    messages = await _trip_messages(client, trip["id"], headers)
    assert [(message["role"], message["content"]) for message in messages] == [
        ("user", "I like gardens."),
        ("assistant", "What pace do you prefer?"),
        ("user", "Local food too."),
        ("assistant", "Great — I will keep the pace relaxed."),
    ]


async def test_chat_failure_before_first_chunk_keeps_only_user_message(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = await _register(client)
    trip = (await client.post("/api/trips", headers=headers)).json()
    _install_gemini(
        monkeypatch,
        _FakeGemini([GeminiUnavailableError(["gemini-test-model"])]),
    )

    response = await client.post(
        f"/api/trips/{trip['id']}/chat",
        headers=headers,
        json={"content": "Plan a quiet weekend."},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == {
        "code": "gemini_unavailable",
        "message": "No compatible Gemini model is currently available",
        "attempted_models": ["gemini-test-model"],
    }
    messages = await _trip_messages(client, trip["id"], headers)
    assert [(message["role"], message["content"]) for message in messages] == [
        ("user", "Plan a quiet weekend.")
    ]


async def test_chat_interruption_after_first_chunk_does_not_save_partial_reply(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    headers = await _register(client)
    trip = (await client.post("/api/trips", headers=headers)).json()
    _install_gemini(
        monkeypatch,
        _FakeGemini(["partial reply", GeminiStreamInterruptedError()]),
    )

    response = await client.post(
        f"/api/trips/{trip['id']}/chat",
        headers=headers,
        json={"content": "Tell me more."},
    )

    assert response.status_code == 200
    events = _events(response)
    assert [event["type"] for event in events] == ["chunk", "error"]
    assert events[0]["content"] == "partial reply"
    assert events[1]["detail"] == {
        "code": "gemini_stream_interrupted",
        "message": "The Gemini response was interrupted",
    }
    messages = await _trip_messages(client, trip["id"], headers)
    assert [(message["role"], message["content"]) for message in messages] == [
        ("user", "Tell me more.")
    ]

from __future__ import annotations

import asyncio
import logging
import re
import time
from collections.abc import AsyncGenerator, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Literal, TypeVar, cast

import httpx
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, ValidationError
from sqlalchemy.exc import SQLAlchemyError

from app.db import cache_get, cache_set
from app.errors import (
    GeminiConfigurationError,
    GeminiError,
    GeminiRequestError,
    GeminiSafetyError,
    GeminiStreamInterruptedError,
    GeminiUnavailableError,
)


logger = logging.getLogger(__name__)

MODEL_STATE_CACHE_KEY = "gemini:model-state"
CATALOG_REFRESH_INTERVAL = timedelta(hours=24)
DEFAULT_COOLDOWN_SECONDS = 60.0

STATIC_MODELS = (
    "gemini-3.7-flash",
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.5-pro",
    "gemini-3.1-pro-preview",
    "gemini-3-flash-preview",
)

_MODEL_NAME = re.compile(
    r"^gemini-[0-9][a-z0-9.-]*-(?:flash(?:-lite)?|pro)(?:-[a-z0-9.-]+)?$"
)
_EXCLUDED_MODEL_MARKERS = (
    "image",
    "tts",
    "live",
    "audio",
    "transcribe",
    "embedding",
    "robotics",
    "computer-use",
    "omni",
    "deep-research",
    "video",
)
_SAFETY_REASONS = (
    "SAFETY",
    "BLOCKLIST",
    "PROHIBITED_CONTENT",
    "SPII",
    "RECITATION",
    "JAILBREAK",
    "MODEL_ARMOR",
)
_FALLBACK_HTTP_CODES = {404, 408, 429, 500, 502, 503, 504}

ResponseModel = TypeVar("ResponseModel", bound=BaseModel)


@dataclass(frozen=True)
class GeminiMessage:
    role: Literal["system", "user", "assistant"]
    content: str


class _ModelState(BaseModel):
    active_model: str
    eligible_models: list[str]
    catalog_refreshed_at: datetime | None = None


class _RetryableModelOutputError(Exception):
    pass


class GeminiClient:
    def __init__(self, *, api_key: str, default_model: str) -> None:
        self._sdk = (
            genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(
                    retry_options=types.HttpRetryOptions(attempts=1)
                ),
            )
            if api_key
            else None
        )
        self.active_model = default_model
        self.eligible_models = list(STATIC_MODELS)
        if default_model not in self.eligible_models:
            self.eligible_models.insert(0, default_model)

        self.catalog_refreshed_at: datetime | None = None
        self._next_catalog_refresh_at = datetime.now(timezone.utc)
        self._catalog_lock = asyncio.Lock()
        self._promotion_lock = asyncio.Lock()
        self._cooldowns: dict[str, float] = {}

    async def initialize(self) -> None:
        cached_payload = await cache_get(MODEL_STATE_CACHE_KEY)
        if cached_payload is not None:
            try:
                state = _ModelState.model_validate(cached_payload)
                if state.eligible_models:
                    self.eligible_models = list(dict.fromkeys(state.eligible_models))
                    self.active_model = state.active_model
                    if self.active_model not in self.eligible_models:
                        self.eligible_models.insert(0, self.active_model)
                    self.catalog_refreshed_at = _as_utc(
                        state.catalog_refreshed_at
                    )
            except ValidationError:
                logger.warning("Ignoring invalid persisted Gemini model state")

        now = datetime.now(timezone.utc)
        self._next_catalog_refresh_at = (
            self.catalog_refreshed_at + CATALOG_REFRESH_INTERVAL
            if self.catalog_refreshed_at is not None
            else now
        )
        if now >= self._next_catalog_refresh_at:
            await self._refresh_catalog()

    async def close(self) -> None:
        if self._sdk is not None:
            await self._sdk.aio.aclose()
            self._sdk.close()

    async def complete_json(
        self,
        messages: Sequence[GeminiMessage],
        response_schema: type[ResponseModel],
    ) -> ResponseModel:
        if not isinstance(response_schema, type) or not issubclass(
            response_schema, BaseModel
        ):
            raise TypeError("response_schema must be a Pydantic model class")

        sdk = self._require_sdk()
        contents, system_instruction = _prepare_messages(messages)
        await self._ensure_catalog_current()
        attempted_models: list[str] = []

        for model in self._available_models():
            attempted_models.append(model)
            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=response_schema,
            )
            try:
                response = await sdk.aio.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config,
                )
                _raise_if_safety_blocked(response)
                result = _parse_structured_response(response, response_schema)
                await self._promote_model(model)
                return cast(ResponseModel, result)
            except Exception as error:
                if _is_fallback_error(error):
                    self._cool_down(model, error)
                    continue
                request_error = _request_error(error)
                if request_error is error:
                    raise
                raise request_error from error

        raise GeminiUnavailableError(attempted_models)

    async def stream_text(
        self, messages: Sequence[GeminiMessage]
    ) -> AsyncGenerator[str, None]:
        sdk = self._require_sdk()
        contents, system_instruction = _prepare_messages(messages)
        await self._ensure_catalog_current()
        attempted_models: list[str] = []

        for model in self._available_models():
            attempted_models.append(model)
            emitted_text = False
            try:
                stream = await sdk.aio.models.generate_content_stream(
                    model=model,
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction
                    ),
                )
                async for chunk in stream:
                    _raise_if_safety_blocked(chunk)
                    text = _optional_response_text(chunk)
                    if not text:
                        continue
                    if not emitted_text:
                        await self._promote_model(model)
                        emitted_text = True
                    yield text

                if emitted_text:
                    return
                raise _RetryableModelOutputError("Gemini returned empty text")
            except Exception as error:
                if emitted_text:
                    stream_error = _stream_error(error)
                    if stream_error is error:
                        raise
                    raise stream_error from error
                if _is_fallback_error(error):
                    self._cool_down(model, error)
                    continue
                request_error = _request_error(error)
                if request_error is error:
                    raise
                raise request_error from error

        raise GeminiUnavailableError(attempted_models)

    def _require_sdk(self) -> genai.Client:
        if self._sdk is None:
            raise GeminiConfigurationError()
        return self._sdk

    async def _ensure_catalog_current(self) -> None:
        if datetime.now(timezone.utc) < self._next_catalog_refresh_at:
            return

        async with self._catalog_lock:
            if datetime.now(timezone.utc) >= self._next_catalog_refresh_at:
                await self._refresh_catalog()

    async def _refresh_catalog(self) -> None:
        now = datetime.now(timezone.utc)
        # A failed discovery is retried after 24 hours, not by every request.
        self._next_catalog_refresh_at = now + CATALOG_REFRESH_INTERVAL
        if self._sdk is None:
            return

        try:
            pager = await self._sdk.aio.models.list()
            discovered = [
                model_name
                async for model in pager
                if (model_name := _eligible_model_name(model)) is not None
            ]
        except (errors.APIError, httpx.HTTPError, TimeoutError, ValueError) as error:
            logger.warning(
                "Gemini model discovery failed; using the existing catalog (%s)",
                type(error).__name__,
            )
            return

        ordered_models = _sort_discovered_models(discovered)
        if not ordered_models:
            logger.warning("Gemini model discovery returned no compatible text models")
            return

        self.eligible_models = ordered_models
        if self.active_model not in self.eligible_models:
            self.active_model = self.eligible_models[0]
        self.catalog_refreshed_at = now
        await self._persist_model_state()

    def _available_models(self) -> list[str]:
        now = time.monotonic()
        self._cooldowns = {
            model: deadline
            for model, deadline in self._cooldowns.items()
            if deadline > now
        }
        ordered = [
            self.active_model,
            *(model for model in self.eligible_models if model != self.active_model),
        ]
        return [
            model
            for model in dict.fromkeys(ordered)
            if model not in self._cooldowns
        ]

    def _cool_down(self, model: str, error: Exception) -> None:
        seconds = _retry_after_seconds(error)
        if seconds is None:
            seconds = DEFAULT_COOLDOWN_SECONDS
        self._cooldowns[model] = time.monotonic() + seconds

    async def _promote_model(self, model: str) -> None:
        if model == self.active_model:
            return

        async with self._promotion_lock:
            if model == self.active_model:
                return
            self.active_model = model
            try:
                await self._persist_model_state()
            except SQLAlchemyError:
                logger.warning("Could not persist the promoted Gemini model")

    async def _persist_model_state(self) -> None:
        state = _ModelState(
            active_model=self.active_model,
            eligible_models=self.eligible_models,
            catalog_refreshed_at=self.catalog_refreshed_at,
        )
        await cache_set(MODEL_STATE_CACHE_KEY, state.model_dump(mode="json"))


def _prepare_messages(
    messages: Sequence[GeminiMessage],
) -> tuple[list[types.Content], str | None]:
    if not messages:
        raise ValueError("At least one Gemini message is required")

    system_parts: list[str] = []
    contents: list[types.Content] = []
    for message in messages:
        content = message.content.strip()
        if not content:
            raise ValueError("Gemini messages cannot be empty")
        if message.role == "system":
            system_parts.append(content)
            continue

        contents.append(
            types.Content(
                role="model" if message.role == "assistant" else "user",
                parts=[types.Part.from_text(text=content)],
            )
        )

    if not contents:
        raise ValueError("Gemini messages must include a user or assistant message")
    return contents, "\n\n".join(system_parts) or None


def _eligible_model_name(model: types.Model) -> str | None:
    if not model.name:
        return None
    name = model.name.rsplit("/", 1)[-1].lower()
    if not _MODEL_NAME.fullmatch(name):
        return None
    if any(marker in name for marker in _EXCLUDED_MODEL_MARKERS):
        return None

    actions = {
        re.sub(r"[^a-z]", "", str(action).lower())
        for action in (model.supported_actions or [])
    }
    if not any("generatecontent" in action for action in actions):
        return None
    return name


def _sort_discovered_models(models: Sequence[str]) -> list[str]:
    unique_models = set(models)
    known_stable = [
        model
        for model in STATIC_MODELS
        if model in unique_models and not _is_preview(model)
    ]
    known_preview = [
        model
        for model in STATIC_MODELS
        if model in unique_models and _is_preview(model)
    ]
    new_stable = sorted(
        model
        for model in unique_models
        if model not in STATIC_MODELS and not _is_preview(model)
    )
    new_preview = sorted(
        model
        for model in unique_models
        if model not in STATIC_MODELS and _is_preview(model)
    )
    return [*known_stable, *new_stable, *known_preview, *new_preview]


def _is_preview(model: str) -> bool:
    return "preview" in model or "experimental" in model or "-exp-" in model


def _required_response_text(response: types.GenerateContentResponse) -> str:
    text = _optional_response_text(response)
    if text is None or not text.strip():
        raise _RetryableModelOutputError("Gemini returned empty text")
    return text.strip()


def _optional_response_text(response: types.GenerateContentResponse) -> str | None:
    try:
        return response.text
    except ValueError as error:
        raise _RetryableModelOutputError("Gemini returned unreadable text") from error


def _parse_structured_response(
    response: types.GenerateContentResponse,
    response_schema: type[BaseModel],
) -> BaseModel:
    parsed = response.parsed
    try:
        if isinstance(parsed, response_schema):
            return parsed
        if parsed is not None:
            return response_schema.model_validate(parsed)
        return response_schema.model_validate_json(_required_response_text(response))
    except (ValidationError, ValueError) as error:
        raise _RetryableModelOutputError(
            "Gemini returned invalid structured output"
        ) from error


def _raise_if_safety_blocked(response: types.GenerateContentResponse) -> None:
    feedback = response.prompt_feedback
    block_reason = getattr(feedback, "block_reason", None)
    if block_reason is not None and _is_safety_reason(block_reason):
        raise GeminiSafetyError()

    for candidate in response.candidates or []:
        if _is_safety_reason(candidate.finish_reason):
            raise GeminiSafetyError()


def _is_safety_reason(reason: object) -> bool:
    name = str(reason).upper()
    return any(marker in name for marker in _SAFETY_REASONS)


def _is_fallback_error(error: Exception) -> bool:
    if isinstance(error, _RetryableModelOutputError):
        return True
    if isinstance(error, (TimeoutError, asyncio.TimeoutError, httpx.TimeoutException)):
        return True
    if isinstance(error, errors.APIError):
        code = _api_error_code(error)
        status_name = str(error.status or "").upper()
        return code in _FALLBACK_HTTP_CODES or status_name == "RESOURCE_EXHAUSTED"
    return False


def _request_error(error: Exception) -> Exception:
    if isinstance(error, GeminiError):
        return error
    if not isinstance(error, errors.APIError):
        return error

    code = _api_error_code(error)
    status_name = str(error.status or "").upper()
    message = str(error.message or "").lower()
    if any(word in status_name or word.lower() in message for word in _SAFETY_REASONS):
        return GeminiSafetyError()
    if code == 400:
        return GeminiRequestError(
            error_code="gemini_invalid_request",
            public_message="Gemini rejected the request",
        )
    if code in {401, 403}:
        return GeminiRequestError(
            error_code="gemini_authentication_failed",
            public_message="Gemini credentials are invalid or lack permission",
        )
    return GeminiRequestError(
        error_code="gemini_request_failed",
        public_message="Gemini could not process the request",
    )


def _stream_error(error: Exception) -> Exception:
    if isinstance(error, GeminiSafetyError):
        return error
    if isinstance(error, (errors.APIError, httpx.HTTPError, TimeoutError)):
        return GeminiStreamInterruptedError()
    return error


def _api_error_code(error: errors.APIError) -> int | None:
    try:
        return int(error.code)
    except (TypeError, ValueError):
        return None


def _retry_after_seconds(error: Exception) -> float | None:
    if not isinstance(error, errors.APIError) or error.response is None:
        return None
    headers = getattr(error.response, "headers", None)
    if headers is None:
        return None
    value = headers.get("Retry-After")
    if not value:
        return None

    try:
        return max(float(value), 0.0)
    except (TypeError, ValueError):
        try:
            retry_at = parsedate_to_datetime(str(value))
        except (TypeError, ValueError, OverflowError):
            return None
        retry_at = _as_utc(retry_at)
        if retry_at is None:
            return None
        return max((retry_at - datetime.now(timezone.utc)).total_seconds(), 0.0)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)

"""Thin async wrapper around the Google Gen AI SDK.

- Model IDs come from Settings only.
- Structured output is always validated into a Pydantic model (never parse free-form prose).
- Provider failures are normalized to AppError(GEMINI_UNAVAILABLE).
- Transient 429/5xx/timeouts are retried with jittered backoff within gemini_timeout_s.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.errors import AppError, ErrorCode
from app.observability import timed

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

# Bounded retries for transient failures only.
_MAX_ATTEMPTS = 4
_BASE_BACKOFF_S = 0.4


def _is_retryable(exc: BaseException) -> bool:
    """True for timeouts, rate limits, and 5xx-class provider failures."""
    if isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        return True
    status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if status is None:
        status = getattr(getattr(exc, "response", None), "status_code", None)
    if isinstance(status, int) and (status == 429 or status >= 500):
        return True
    name = type(exc).__name__.lower()
    msg = str(exc).lower()
    markers = (
        "429",
        "500",
        "502",
        "503",
        "504",
        "timeout",
        "timed out",
        "rate limit",
        "unavailable",
        "resourceexhausted",
    )
    return any(m in name or m in msg for m in markers)


class GeminiClient:
    def __init__(self, settings: Settings) -> None:
        if settings.google_api_key is None:
            raise ValueError("GeminiClient requires GOOGLE_API_KEY")
        self._timeout_s = settings.gemini_timeout_s
        self._client = genai.Client(
            api_key=settings.google_api_key.get_secret_value(),
            http_options=types.HttpOptions(timeout=int(self._timeout_s * 1000)),
        )
        self.model = settings.gemini_model
        self.embedding_model = settings.gemini_embedding_model
        self.embedding_dimension = settings.gemini_embedding_dimension

    async def _with_retries(self, operation: str, call):
        deadline = time.monotonic() + self._timeout_s
        last_exc: BaseException | None = None
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                return await asyncio.wait_for(call(), timeout=remaining)
            except Exception as exc:  # SDK raises several error types; normalize them.
                last_exc = exc
                retryable = _is_retryable(exc)
                if not retryable or attempt >= _MAX_ATTEMPTS:
                    break
                sleep_s = min(
                    _BASE_BACKOFF_S * (2 ** (attempt - 1)) + random.uniform(0, 0.25),
                    max(0.0, deadline - time.monotonic()),
                )
                if sleep_s <= 0:
                    break
                logger.warning(
                    "gemini retry",
                    extra={
                        "operation": operation,
                        "attempt": attempt,
                        "error": type(exc).__name__,
                        "sleep_s": round(sleep_s, 3),
                    },
                )
                await asyncio.sleep(sleep_s)
        assert last_exc is not None
        logger.warning("gemini call failed", extra={"operation": operation, "error": type(last_exc).__name__})
        raise AppError(ErrorCode.GEMINI_UNAVAILABLE, "Gemini request failed") from last_exc

    async def generate_structured(
        self,
        *,
        prompt: str,
        schema: type[T],
        system_instruction: str | None = None,
        temperature: float = 0.2,
        operation: str = "gemini.generate",
        timings: dict[str, float] | None = None,
    ) -> T:
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=schema,
            temperature=temperature,
        )

        async def _call():
            return await self._client.aio.models.generate_content(model=self.model, contents=prompt, config=config)

        with timed(operation, timings, model=self.model):
            response = await self._with_retries(operation, _call)

        if isinstance(response.parsed, schema):
            return response.parsed
        try:
            return schema.model_validate_json(response.text or "")
        except ValidationError as exc:
            raise AppError(
                ErrorCode.GEMINI_UNAVAILABLE, "Gemini returned output that failed schema validation"
            ) from exc

    async def embed(
        self,
        texts: list[str],
        *,
        task_type: str = "RETRIEVAL_DOCUMENT",
        timings: dict[str, float] | None = None,
    ) -> list[list[float]]:
        if not texts:
            return []
        config = types.EmbedContentConfig(task_type=task_type, output_dimensionality=self.embedding_dimension)

        async def _call():
            return await self._client.aio.models.embed_content(
                model=self.embedding_model, contents=texts, config=config
            )

        with timed("gemini.embed", timings, model=self.embedding_model, count=len(texts)):
            response = await self._with_retries("gemini.embed", _call)
        return [list(e.values or []) for e in response.embeddings or []]

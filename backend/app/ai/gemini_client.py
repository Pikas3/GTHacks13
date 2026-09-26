"""Thin async wrapper around the Google Gen AI SDK.

- Model IDs come from Settings only.
- Structured output is always validated into a Pydantic model (never parse free-form prose).
- Provider failures are normalized to AppError(GEMINI_UNAVAILABLE).
"""

import logging
from typing import TypeVar

from google import genai
from google.genai import types
from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.errors import AppError, ErrorCode
from app.observability import timed

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


class GeminiClient:
    def __init__(self, settings: Settings) -> None:
        if settings.google_api_key is None:
            raise ValueError("GeminiClient requires GOOGLE_API_KEY")
        self._client = genai.Client(
            api_key=settings.google_api_key.get_secret_value(),
            http_options=types.HttpOptions(timeout=int(settings.gemini_timeout_s * 1000)),
        )
        self.model = settings.gemini_model
        self.embedding_model = settings.gemini_embedding_model
        self.embedding_dimension = settings.gemini_embedding_dimension

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
        try:
            with timed(operation, timings, model=self.model):
                response = await self._client.aio.models.generate_content(
                    model=self.model, contents=prompt, config=config
                )
        except Exception as exc:  # SDK raises several error types; normalize them.
            logger.warning("gemini call failed", extra={"operation": operation, "error": type(exc).__name__})
            raise AppError(ErrorCode.GEMINI_UNAVAILABLE, "Gemini request failed") from exc

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
        try:
            with timed("gemini.embed", timings, model=self.embedding_model, count=len(texts)):
                response = await self._client.aio.models.embed_content(
                    model=self.embedding_model, contents=texts, config=config
                )
        except Exception as exc:
            logger.warning("gemini embed failed", extra={"error": type(exc).__name__})
            raise AppError(ErrorCode.GEMINI_UNAVAILABLE, "Gemini embedding request failed") from exc
        return [list(e.values or []) for e in response.embeddings or []]

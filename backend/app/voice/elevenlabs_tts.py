import logging
from collections.abc import AsyncIterator

import httpx

from app.config import Settings
from app.errors import AppError, ErrorCode
from app.observability import timed
from app.schemas.audio import SynthesizedAudio
from app.voice.speech_text import normalize_speech_text

logger = logging.getLogger(__name__)


class ElevenLabsTTSProvider:
    """ElevenLabs text-to-speech via REST (buffered MP3 + optional stream)."""

    name = "elevenlabs"

    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        if settings.elevenlabs_api_key is None or not settings.elevenlabs_voice_id:
            raise ValueError("ElevenLabs TTS requires ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID")
        self._api_key = settings.elevenlabs_api_key.get_secret_value()
        self.voice_id = settings.elevenlabs_voice_id
        self.model = settings.elevenlabs_tts_model
        self.base_url = settings.elevenlabs_base_url.rstrip("/")
        self.http = http

    def _headers(self) -> dict[str, str]:
        return {"xi-api-key": self._api_key, "accept": "audio/mpeg"}

    def _body(
        self, text: str, *, previous_text: str | None = None, next_text: str | None = None
    ) -> dict[str, object]:
        spoken = normalize_speech_text(text)
        body: dict[str, object] = {"text": spoken, "model_id": self.model}
        # Prosody context when chunking multi-sentence answers.
        if previous_text:
            body["previous_text"] = normalize_speech_text(previous_text)
        if next_text:
            body["next_text"] = normalize_speech_text(next_text)
        return body

    async def synthesize(self, text: str) -> SynthesizedAudio:
        url = f"{self.base_url}/v1/text-to-speech/{self.voice_id}"
        spoken = normalize_speech_text(text)
        try:
            with timed("elevenlabs.tts", model=self.model, chars=len(spoken)):
                resp = await self.http.post(
                    url,
                    params={"output_format": "mp3_44100_128"},
                    headers=self._headers(),
                    json=self._body(text),
                )
                resp.raise_for_status()
        except httpx.TimeoutException as exc:
            logger.warning("elevenlabs tts timeout", extra={"error": type(exc).__name__})
            raise AppError(ErrorCode.ELEVENLABS_UNAVAILABLE, "Text-to-speech timed out") from exc
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "elevenlabs tts http error",
                extra={"status": exc.response.status_code, "error": type(exc).__name__},
            )
            raise AppError(ErrorCode.ELEVENLABS_UNAVAILABLE, "Text-to-speech provider failed") from exc
        except httpx.HTTPError as exc:
            logger.warning("elevenlabs tts failed", extra={"error": type(exc).__name__})
            raise AppError(ErrorCode.ELEVENLABS_UNAVAILABLE, "Text-to-speech provider failed") from exc
        return SynthesizedAudio(audio=resp.content, media_type="audio/mpeg", provider=self.name)

    async def synthesize_stream(
        self, text: str, *, previous_text: str | None = None, next_text: str | None = None
    ) -> AsyncIterator[bytes]:
        """Stream MP3 bytes from ElevenLabs `/stream` endpoint."""
        url = f"{self.base_url}/v1/text-to-speech/{self.voice_id}/stream"
        spoken = normalize_speech_text(text)
        try:
            with timed("elevenlabs.tts.stream", model=self.model, chars=len(spoken)):
                async with self.http.stream(
                    "POST",
                    url,
                    params={"output_format": "mp3_44100_128"},
                    headers=self._headers(),
                    json=self._body(text, previous_text=previous_text, next_text=next_text),
                ) as resp:
                    try:
                        resp.raise_for_status()
                    except httpx.HTTPStatusError as exc:
                        logger.warning(
                            "elevenlabs tts stream http error",
                            extra={"status": exc.response.status_code},
                        )
                        raise AppError(
                            ErrorCode.ELEVENLABS_UNAVAILABLE, "Text-to-speech stream failed"
                        ) from exc
                    async for chunk in resp.aiter_bytes():
                        if chunk:
                            yield chunk
        except AppError:
            raise
        except httpx.TimeoutException as exc:
            logger.warning("elevenlabs tts stream timeout")
            raise AppError(ErrorCode.ELEVENLABS_UNAVAILABLE, "Text-to-speech timed out") from exc
        except httpx.HTTPError as exc:
            logger.warning("elevenlabs tts stream failed", extra={"error": type(exc).__name__})
            raise AppError(ErrorCode.ELEVENLABS_UNAVAILABLE, "Text-to-speech stream failed") from exc

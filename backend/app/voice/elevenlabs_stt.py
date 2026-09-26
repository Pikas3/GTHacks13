import logging

import httpx

from app.config import Settings
from app.errors import AppError, ErrorCode
from app.observability import timed
from app.schemas.audio import TranscriptionResult

logger = logging.getLogger(__name__)


class ElevenLabsSTTProvider:
    """ElevenLabs speech-to-text (Scribe) via REST. Audio bytes are never logged.

    TODO(voice): Evaluate realtime/streaming STT for partial transcripts while the HCP speaks.
    """

    name = "elevenlabs"

    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        if settings.elevenlabs_api_key is None:
            raise ValueError("ElevenLabs STT requires ELEVENLABS_API_KEY")
        self._api_key = settings.elevenlabs_api_key.get_secret_value()
        self.model = settings.elevenlabs_stt_model
        self.base_url = settings.elevenlabs_base_url
        self.http = http

    async def transcribe(self, audio: bytes, content_type: str, filename: str = "audio.webm") -> TranscriptionResult:
        try:
            with timed("elevenlabs.stt", model=self.model, bytes=len(audio)):
                resp = await self.http.post(
                    f"{self.base_url}/v1/speech-to-text",
                    headers={"xi-api-key": self._api_key},
                    data={"model_id": self.model},
                    files={"file": (filename, audio, content_type)},
                )
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("elevenlabs stt failed", extra={"error": type(exc).__name__})
            raise AppError(ErrorCode.AUDIO_TRANSCRIPTION_FAILED, "Speech-to-text provider failed") from exc
        body = resp.json()
        text = (body.get("text") or "").strip()
        if not text:
            raise AppError(ErrorCode.AUDIO_TRANSCRIPTION_FAILED, "No speech detected in the recording")
        return TranscriptionResult(
            text=text,
            confidence=body.get("language_probability"),
            language=body.get("language_code"),
            provider=self.name,
        )

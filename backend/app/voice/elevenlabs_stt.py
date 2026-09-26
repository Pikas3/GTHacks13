import logging

import httpx

from app.config import Settings
from app.errors import AppError, ErrorCode
from app.observability import timed
from app.schemas.audio import TranscriptionResult
from app.voice.audio_format import resolve_audio_format

logger = logging.getLogger(__name__)

# Bytes below this are almost certainly an empty/accidental tap (post-header).
MIN_AUDIO_BYTES = 256


class ElevenLabsSTTProvider:
    """ElevenLabs speech-to-text (Scribe) via REST. Audio bytes are never logged.

    Realtime/streaming STT (WebSocket scribe realtime) was evaluated for push-to-talk:
    for short hold-to-talk utterances the extra WebSocket handshake + PCM conversion
    does not clearly beat batch `/v1/speech-to-text` once the user releases the orb.
    Keep batch STT; revisit if we move to always-listening partial transcripts.
    """

    name = "elevenlabs"

    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        if settings.elevenlabs_api_key is None:
            raise ValueError("ElevenLabs STT requires ELEVENLABS_API_KEY")
        self._api_key = settings.elevenlabs_api_key.get_secret_value()
        self.model = settings.elevenlabs_stt_model
        self.base_url = settings.elevenlabs_base_url.rstrip("/")
        self.http = http

    async def transcribe(
        self, audio: bytes, content_type: str, filename: str = "audio.webm"
    ) -> TranscriptionResult:
        if len(audio) < MIN_AUDIO_BYTES:
            raise AppError(ErrorCode.AUDIO_TRANSCRIPTION_FAILED, "Recording too short — hold the orb and try again")

        fmt = resolve_audio_format(content_type, filename)
        try:
            with timed("elevenlabs.stt", model=self.model, bytes=len(audio), content_type=fmt.content_type):
                resp = await self.http.post(
                    f"{self.base_url}/v1/speech-to-text",
                    headers={"xi-api-key": self._api_key},
                    data={"model_id": self.model},
                    files={"file": (fmt.filename, audio, fmt.content_type)},
                )
                resp.raise_for_status()
        except httpx.TimeoutException as exc:
            logger.warning("elevenlabs stt timeout", extra={"bytes": len(audio)})
            raise AppError(ErrorCode.AUDIO_TRANSCRIPTION_FAILED, "Speech-to-text timed out") from exc
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "elevenlabs stt http error",
                extra={"status": exc.response.status_code, "bytes": len(audio)},
            )
            raise AppError(ErrorCode.AUDIO_TRANSCRIPTION_FAILED, "Speech-to-text provider failed") from exc
        except httpx.HTTPError as exc:
            logger.warning("elevenlabs stt failed", extra={"error": type(exc).__name__, "bytes": len(audio)})
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

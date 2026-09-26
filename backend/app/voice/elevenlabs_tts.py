import logging

import httpx

from app.config import Settings
from app.errors import AppError, ErrorCode
from app.observability import timed
from app.schemas.audio import SynthesizedAudio

logger = logging.getLogger(__name__)


class ElevenLabsTTSProvider:
    """ElevenLabs text-to-speech via REST (returns a single MP3 buffer).

    TODO(voice): Add streaming ElevenLabs TTS (/stream endpoint or websocket) to cut
    time-to-first-audio, and pass previous_text for smoother multi-sentence prosody.
    """

    name = "elevenlabs"

    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        if settings.elevenlabs_api_key is None or not settings.elevenlabs_voice_id:
            raise ValueError("ElevenLabs TTS requires ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID")
        self._api_key = settings.elevenlabs_api_key.get_secret_value()
        self.voice_id = settings.elevenlabs_voice_id
        self.model = settings.elevenlabs_tts_model
        self.base_url = settings.elevenlabs_base_url
        self.http = http

    async def synthesize(self, text: str) -> SynthesizedAudio:
        url = f"{self.base_url}/v1/text-to-speech/{self.voice_id}"
        try:
            with timed("elevenlabs.tts", model=self.model, chars=len(text)):
                resp = await self.http.post(
                    url,
                    params={"output_format": "mp3_44100_128"},
                    headers={"xi-api-key": self._api_key, "accept": "audio/mpeg"},
                    json={"text": text, "model_id": self.model},
                )
                resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("elevenlabs tts failed", extra={"error": type(exc).__name__})
            raise AppError(ErrorCode.ELEVENLABS_UNAVAILABLE, "Text-to-speech provider failed") from exc
        return SynthesizedAudio(audio=resp.content, media_type="audio/mpeg", provider=self.name)

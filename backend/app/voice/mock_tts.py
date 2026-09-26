import io
import wave
from collections.abc import AsyncIterator

from app.schemas.audio import SynthesizedAudio
from app.voice.speech_text import normalize_speech_text


def _silent_wav(duration_s: float = 0.4, sample_rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sample_rate)
        w.writeframes(b"\x00\x00" * int(duration_s * sample_rate))
    return buf.getvalue()


class MockTTSProvider:
    """Returns a short silent WAV placeholder (browser-playable). No network, no key."""

    name = "mock"

    def __init__(self) -> None:
        self._audio = _silent_wav()

    async def synthesize(self, text: str) -> SynthesizedAudio:
        _ = normalize_speech_text(text)  # exercise same path as real TTS
        return SynthesizedAudio(
            audio=self._audio, media_type="audio/wav", provider=self.name, is_placeholder=True
        )

    async def synthesize_stream(
        self, text: str, *, previous_text: str | None = None, next_text: str | None = None
    ) -> AsyncIterator[bytes]:
        _ = (text, previous_text, next_text)
        yield self._audio

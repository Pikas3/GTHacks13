from typing import AsyncIterator, Protocol

from app.schemas.audio import SynthesizedAudio, TranscriptionResult


class TextToSpeechProvider(Protocol):
    name: str

    async def synthesize(self, text: str) -> SynthesizedAudio: ...


class StreamingTextToSpeechProvider(Protocol):
    """Optional capability — not all TTS providers implement streaming."""

    name: str

    async def synthesize_stream(
        self, text: str, *, previous_text: str | None = None, next_text: str | None = None
    ) -> AsyncIterator[bytes]: ...


class SpeechToTextProvider(Protocol):
    name: str

    async def transcribe(
        self, audio: bytes, content_type: str, filename: str = "audio.webm"
    ) -> TranscriptionResult: ...

from typing import Protocol

from app.schemas.audio import SynthesizedAudio, TranscriptionResult


class TextToSpeechProvider(Protocol):
    name: str

    async def synthesize(self, text: str) -> SynthesizedAudio: ...


class SpeechToTextProvider(Protocol):
    name: str

    async def transcribe(
        self, audio: bytes, content_type: str, filename: str = "audio.webm"
    ) -> TranscriptionResult: ...

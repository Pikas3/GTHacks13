from pydantic import BaseModel, Field


class TranscriptionResult(BaseModel):
    text: str
    confidence: float | None = None
    language: str | None = None
    provider: str


class SynthesizeRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)


class SynthesizedAudio(BaseModel):
    """Internal result of TTS. Returned to clients as raw audio bytes, not JSON."""

    audio: bytes
    media_type: str
    provider: str
    is_placeholder: bool = False

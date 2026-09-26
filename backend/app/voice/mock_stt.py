from app.schemas.audio import TranscriptionResult


class MockSTTProvider:
    """Ignores the audio and returns configurable fixture text (MOCK_STT_TEXT)."""

    name = "mock"

    def __init__(self, fixture_text: str) -> None:
        self.fixture_text = fixture_text

    async def transcribe(
        self,
        audio: bytes,
        content_type: str,
        filename: str = "audio.webm",
        *,
        override_text: str | None = None,
    ) -> TranscriptionResult:
        _ = (audio, content_type, filename)
        text = (override_text or self.fixture_text).strip() or self.fixture_text
        return TranscriptionResult(text=text, confidence=1.0, language="en", provider=self.name)

"""Short-lived in-memory speech buffers for streaming TTS playback.

POST /audio/speech stores normalized text + kicks off (or caches) synthesis;
GET /audio/speech/{id} streams audio bytes. Text never appears in a URL query string.
"""

from __future__ import annotations

import asyncio
import secrets
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field

from app.errors import AppError, ErrorCode
from app.voice.interfaces import TextToSpeechProvider
from app.voice.speech_text import first_sentence, normalize_speech_text

TTL_SECONDS = 120
MAX_ENTRIES = 64


@dataclass
class SpeechEntry:
    text: str
    provider: str
    media_type: str
    is_placeholder: bool
    created_at: float = field(default_factory=time.monotonic)
    chunks: list[bytes] = field(default_factory=list)
    done: asyncio.Event = field(default_factory=asyncio.Event)
    error: Exception | None = None


class SpeechStore:
    def __init__(self) -> None:
        self._entries: dict[str, SpeechEntry] = {}
        self._lock = asyncio.Lock()

    def _purge_unlocked(self) -> None:
        now = time.monotonic()
        expired = [k for k, v in self._entries.items() if now - v.created_at > TTL_SECONDS]
        for k in expired:
            self._entries.pop(k, None)
        while len(self._entries) > MAX_ENTRIES:
            oldest = min(self._entries.items(), key=lambda kv: kv[1].created_at)[0]
            self._entries.pop(oldest, None)

    async def create(self, text: str, tts: TextToSpeechProvider) -> tuple[str, SpeechEntry]:
        spoken = normalize_speech_text(text)
        if not spoken:
            raise AppError(ErrorCode.VALIDATION_ERROR, "Empty speech text")
        speech_id = secrets.token_urlsafe(16)
        # Prefer streaming when available; fall back to buffered synthesize.
        media_type = "audio/mpeg" if getattr(tts, "name", "") == "elevenlabs" else "audio/wav"
        is_placeholder = getattr(tts, "name", "") == "mock"
        entry = SpeechEntry(
            text=spoken,
            provider=getattr(tts, "name", "unknown"),
            media_type=media_type if not is_placeholder else "audio/wav",
            is_placeholder=is_placeholder,
        )
        async with self._lock:
            self._purge_unlocked()
            self._entries[speech_id] = entry
        asyncio.create_task(self._fill(speech_id, spoken, tts))
        return speech_id, entry

    async def _fill(self, speech_id: str, text: str, tts: TextToSpeechProvider) -> None:
        entry = self._entries.get(speech_id)
        if entry is None:
            return
        try:
            stream_fn = getattr(tts, "synthesize_stream", None)
            if callable(stream_fn):
                first, rest = first_sentence(text)
                if first and rest and hasattr(tts, "synthesize"):
                    # Prefer first-sentence first for time-to-first-audio, then remainder
                    # with previous_text context when the provider supports it.
                    async for chunk in stream_fn(first, previous_text=None, next_text=rest):
                        entry.chunks.append(chunk)
                    async for chunk in stream_fn(rest, previous_text=first, next_text=None):
                        entry.chunks.append(chunk)
                else:
                    async for chunk in stream_fn(text):
                        entry.chunks.append(chunk)
            else:
                result = await tts.synthesize(text)
                entry.media_type = result.media_type
                entry.is_placeholder = result.is_placeholder
                entry.chunks.append(result.audio)
        except Exception as exc:  # noqa: BLE001 — stored for stream consumers
            entry.error = exc
        finally:
            entry.done.set()

    async def get(self, speech_id: str) -> SpeechEntry:
        async with self._lock:
            self._purge_unlocked()
            entry = self._entries.get(speech_id)
        if entry is None:
            raise AppError(ErrorCode.INVALID_RESOURCE, "Speech clip not found or expired")
        return entry

    async def stream(self, speech_id: str) -> AsyncIterator[bytes]:
        entry = await self.get(speech_id)
        idx = 0
        while True:
            while idx < len(entry.chunks):
                yield entry.chunks[idx]
                idx += 1
            if entry.done.is_set():
                break
            await asyncio.sleep(0.02)
        if entry.error is not None:
            if isinstance(entry.error, AppError):
                raise entry.error
            raise AppError(ErrorCode.ELEVENLABS_UNAVAILABLE, "Text-to-speech failed") from entry.error
        # Drain any final chunks
        while idx < len(entry.chunks):
            yield entry.chunks[idx]
            idx += 1


speech_store = SpeechStore()

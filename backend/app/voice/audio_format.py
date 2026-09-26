"""Normalize browser MediaRecorder MIME types for ElevenLabs uploads.

Chrome typically sends ``audio/webm;codecs=opus``; Safari ``audio/mp4`` / AAC;
Firefox ``audio/ogg;codecs=opus``. ElevenLabs expects a base type + matching extension.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AudioFormat:
    content_type: str
    extension: str
    filename: str


_BASE_MAP: dict[str, tuple[str, str]] = {
    "audio/webm": ("audio/webm", "webm"),
    "video/webm": ("audio/webm", "webm"),
    "audio/mp4": ("audio/mp4", "mp4"),
    "audio/m4a": ("audio/mp4", "mp4"),
    "audio/x-m4a": ("audio/mp4", "mp4"),
    "audio/aac": ("audio/mp4", "mp4"),
    "audio/mpeg": ("audio/mpeg", "mp3"),
    "audio/mp3": ("audio/mpeg", "mp3"),
    "audio/wav": ("audio/wav", "wav"),
    "audio/x-wav": ("audio/wav", "wav"),
    "audio/ogg": ("audio/ogg", "ogg"),
    "application/ogg": ("audio/ogg", "ogg"),
}


def normalize_content_type(raw: str | None) -> str:
    """Strip codec parameters: ``audio/webm;codecs=opus`` → ``audio/webm``."""
    if not raw:
        return "application/octet-stream"
    base = raw.split(";", 1)[0].strip().lower()
    mapped = _BASE_MAP.get(base)
    return mapped[0] if mapped else base


def resolve_audio_format(content_type: str | None, filename: str | None = None) -> AudioFormat:
    """Pick content type + filename extension ElevenLabs can accept."""
    normalized = normalize_content_type(content_type)
    mapped = _BASE_MAP.get(normalized)
    if mapped:
        ctype, ext = mapped
    else:
        # Fall back to extension from the uploaded filename when MIME is opaque.
        name = (filename or "").lower()
        if name.endswith(".webm"):
            ctype, ext = "audio/webm", "webm"
        elif name.endswith(".mp4") or name.endswith(".m4a"):
            ctype, ext = "audio/mp4", "mp4"
        elif name.endswith(".ogg"):
            ctype, ext = "audio/ogg", "ogg"
        elif name.endswith(".wav"):
            ctype, ext = "audio/wav", "wav"
        elif name.endswith(".mp3"):
            ctype, ext = "audio/mpeg", "mp3"
        else:
            ctype, ext = normalized or "application/octet-stream", "webm"
    return AudioFormat(content_type=ctype, extension=ext, filename=f"recording.{ext}")

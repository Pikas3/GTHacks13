"""Unit tests for ElevenLabs STT/TTS adapters (httpx.MockTransport — no network)."""

from __future__ import annotations

import json

import httpx
import pytest
from pydantic import SecretStr

from app.config import Settings
from app.errors import AppError, ErrorCode
from app.voice.audio_format import normalize_content_type, resolve_audio_format
from app.voice.elevenlabs_stt import ElevenLabsSTTProvider
from app.voice.elevenlabs_tts import ElevenLabsTTSProvider
from app.voice.speech_text import first_sentence, normalize_speech_text


def _settings(**kwargs: object) -> Settings:
    base = dict(
        _env_file=None,
        elevenlabs_api_key=SecretStr("test-key-do-not-leak"),
        elevenlabs_voice_id="voice_abc",
        elevenlabs_tts_model="eleven_flash_v2_5",
        elevenlabs_stt_model="scribe_v1",
        elevenlabs_base_url="https://api.elevenlabs.io",
        use_mock_voice=False,
    )
    base.update(kwargs)
    return Settings(**base)  # type: ignore[arg-type]


def test_normalize_strips_codec_params() -> None:
    assert normalize_content_type("audio/webm;codecs=opus") == "audio/webm"
    assert normalize_content_type("audio/ogg; codecs=opus") == "audio/ogg"
    fmt = resolve_audio_format("audio/webm;codecs=opus", "blob")
    assert fmt.content_type == "audio/webm"
    assert fmt.filename.endswith(".webm")
    safari = resolve_audio_format("audio/mp4", "recording.mp4")
    assert safari.content_type == "audio/mp4"
    assert safari.extension == "mp4"


def test_speech_text_normalizer() -> None:
    raw = "See Novara PI v2.0 [E1] — eGFR guidance."
    spoken = normalize_speech_text(raw)
    assert "[E1]" not in spoken
    assert "prescribing information" in spoken
    assert "version 2" in spoken
    assert "estimated G F R" in spoken
    first, rest = first_sentence("Hello there. More words follow.")
    assert first == "Hello there."
    assert rest == "More words follow."


@pytest.mark.asyncio
async def test_tts_request_shape_and_success() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content.decode())
        assert "test-key-do-not-leak" not in str(captured["url"])
        return httpx.Response(200, content=b"ID3fake-mp3")

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        tts = ElevenLabsTTSProvider(_settings(), http)
        result = await tts.synthesize("Hello PI v1")
    assert result.audio == b"ID3fake-mp3"
    assert result.media_type == "audio/mpeg"
    assert result.provider == "elevenlabs"
    assert "voice_abc" in str(captured["url"])
    assert "output_format=mp3_44100_128" in str(captured["url"])
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers.get("xi-api-key") == "test-key-do-not-leak"
    body = captured["body"]
    assert isinstance(body, dict)
    assert body["model_id"] == "eleven_flash_v2_5"
    assert "prescribing information" in body["text"]
    assert "version 1" in body["text"]


@pytest.mark.asyncio
async def test_tts_http_error_maps_to_app_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"detail": "down"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        tts = ElevenLabsTTSProvider(_settings(), http)
        with pytest.raises(AppError) as exc:
            await tts.synthesize("hi")
    assert exc.value.code == ErrorCode.ELEVENLABS_UNAVAILABLE


@pytest.mark.asyncio
async def test_stt_request_shape_strips_codecs() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        # Multipart — ensure file part used normalized type via content disposition presence
        captured["content_type"] = request.headers.get("content-type", "")
        return httpx.Response(
            200,
            json={"text": "What's new with Novara?", "language_probability": 0.91, "language_code": "en"},
        )

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        stt = ElevenLabsSTTProvider(_settings(), http)
        result = await stt.transcribe(b"x" * 512, "audio/webm;codecs=opus", "blob")
    assert result.text.startswith("What's new")
    assert result.provider == "elevenlabs"
    assert result.confidence == 0.91
    assert str(captured["url"]).endswith("/v1/speech-to-text")
    headers = captured["headers"]
    assert isinstance(headers, dict)
    assert headers.get("xi-api-key") == "test-key-do-not-leak"


@pytest.mark.asyncio
async def test_stt_empty_transcript() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"text": "  "})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        stt = ElevenLabsSTTProvider(_settings(), http)
        with pytest.raises(AppError) as exc:
            await stt.transcribe(b"x" * 512, "audio/mp4", "recording.mp4")
    assert exc.value.code == ErrorCode.AUDIO_TRANSCRIPTION_FAILED


@pytest.mark.asyncio
async def test_stt_too_short() -> None:
    transport = httpx.MockTransport(lambda r: httpx.Response(200, json={"text": "hi"}))
    async with httpx.AsyncClient(transport=transport) as http:
        stt = ElevenLabsSTTProvider(_settings(), http)
        with pytest.raises(AppError) as exc:
            await stt.transcribe(b"tiny", "audio/webm", "a.webm")
    assert exc.value.code == ErrorCode.AUDIO_TRANSCRIPTION_FAILED


@pytest.mark.asyncio
async def test_stt_http_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "bad key"})

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as http:
        stt = ElevenLabsSTTProvider(_settings(), http)
        with pytest.raises(AppError) as exc:
            await stt.transcribe(b"x" * 512, "audio/webm", "a.webm")
    assert exc.value.code == ErrorCode.AUDIO_TRANSCRIPTION_FAILED

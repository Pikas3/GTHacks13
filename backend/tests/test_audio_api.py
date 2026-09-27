"""Audio API: mock path, mock_text override, speech create/stream."""

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_mock_audio_endpoints_work_without_keys() -> None:
    settings = Settings(_env_file=None, use_mock_voice=True, mock_stt_text="What about renal impairment?")
    with TestClient(create_app(settings)) as client:
        stt = client.post("/api/audio/transcribe", files={"audio": ("a.webm", b"\x00\x01", "audio/webm")})
        tts = client.post("/api/audio/synthesize", json={"text": "Hello PI v2.0 [E1]"})
    assert stt.json()["text"] == "What about renal impairment?"
    assert tts.status_code == 200
    assert tts.headers["content-type"] == "audio/wav"
    assert tts.headers["x-tts-placeholder"] == "true"


def test_mock_text_override_on_transcribe() -> None:
    settings = Settings(_env_file=None, use_mock_voice=True, mock_stt_text="default fixture")
    with TestClient(create_app(settings)) as client:
        resp = client.post(
            "/api/audio/transcribe",
            files={"audio": ("a.webm", b"\x00\x01", "audio/webm")},
            data={"mock_text": "What changed with Cardexa?"},
        )
    assert resp.status_code == 200
    assert resp.json()["text"] == "What changed with Cardexa?"
    assert resp.json()["provider"] == "mock"


def test_speech_create_and_stream_mock() -> None:
    settings = Settings(_env_file=None, use_mock_voice=True)
    with TestClient(create_app(settings)) as client:
        created = client.post("/api/audio/speech", json={"text": "Hello from Lepius."})
        assert created.status_code == 201
        body = created.json()
        assert body["is_placeholder"] is True
        assert body["provider"] == "mock"
        streamed = client.get(f"/api/audio/speech/{body['speech_id']}")
        assert streamed.status_code == 200
        assert streamed.headers["x-tts-placeholder"] == "true"
        assert len(streamed.content) > 0

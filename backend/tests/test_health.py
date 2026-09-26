from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_health_reports_degraded_without_database() -> None:
    settings = Settings(
        _env_file=None,
        database_url="postgresql+asyncpg://nobody:nothing@127.0.0.1:1/none",
        use_mock_ai=True,
        use_mock_voice=True,
    )
    with TestClient(create_app(settings)) as client:
        resp = client.get("/api/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "degraded"
    assert body["database"] == "unavailable"
    assert body["ai_mode"] == "mock"
    assert body["gemini_model"] == settings.gemini_model


def test_database_errors_are_normalized() -> None:
    settings = Settings(_env_file=None, database_url="postgresql+asyncpg://x:y@127.0.0.1:1/none")
    with TestClient(create_app(settings)) as client:
        resp = client.get("/api/hcps")
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "DATABASE_UNAVAILABLE"


def test_mock_audio_endpoints_work_without_keys() -> None:
    settings = Settings(_env_file=None, use_mock_voice=True, mock_stt_text="What about renal impairment?")
    with TestClient(create_app(settings)) as client:
        stt = client.post("/api/audio/transcribe", files={"audio": ("a.webm", b"\x00\x01", "audio/webm")})
        tts = client.post("/api/audio/synthesize", json={"text": "Hello"})
    assert stt.json()["text"] == "What about renal impairment?"
    assert tts.status_code == 200
    assert tts.headers["content-type"] == "audio/wav"
    assert tts.headers["x-tts-placeholder"] == "true"

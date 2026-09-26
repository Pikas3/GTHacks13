"""GeminiClient retry/backoff unit tests with a stubbed SDK client."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import BaseModel, SecretStr

from app.ai.gemini_client import GeminiClient, _is_retryable
from app.config import Settings
from app.errors import AppError, ErrorCode


class _Out(BaseModel):
    value: str = "ok"


def _settings(**overrides) -> Settings:
    base = dict(
        google_api_key=SecretStr("test-key"),
        gemini_model="gemini-test",
        gemini_embedding_model="embed-test",
        gemini_embedding_dimension=8,
        gemini_timeout_s=2.0,
        use_mock_ai=False,
    )
    base.update(overrides)
    return Settings(**base)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> GeminiClient:
    fake_genai = MagicMock()
    fake_models = MagicMock()
    fake_genai.Client.return_value = SimpleNamespace(
        aio=SimpleNamespace(models=fake_models),
    )
    monkeypatch.setattr("app.ai.gemini_client.genai", fake_genai)
    monkeypatch.setattr("app.ai.gemini_client.types", MagicMock())
    gc = GeminiClient(_settings())
    gc._models = fake_models  # type: ignore[attr-defined]
    return gc


def test_is_retryable_detects_429_and_timeouts() -> None:
    assert _is_retryable(TimeoutError())
    assert _is_retryable(Exception("429 rate limit"))
    err_503 = Exception("service unavailable")
    err_503.code = 503  # type: ignore[attr-defined]
    assert _is_retryable(err_503)
    assert not _is_retryable(ValueError("bad schema"))


async def test_generate_retries_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_models = MagicMock()
    calls = {"n": 0}

    async def flaky(**_kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            err = Exception("503 unavailable")
            err.code = 503  # type: ignore[attr-defined]
            raise err
        return SimpleNamespace(parsed=_Out(value="ok"), text='{"value":"ok"}')

    fake_models.generate_content = AsyncMock(side_effect=flaky)
    fake_genai = MagicMock()
    fake_genai.Client.return_value = SimpleNamespace(aio=SimpleNamespace(models=fake_models))
    monkeypatch.setattr("app.ai.gemini_client.genai", fake_genai)
    monkeypatch.setattr("app.ai.gemini_client.types", MagicMock())
    monkeypatch.setattr("app.ai.gemini_client.asyncio.sleep", AsyncMock())

    gc = GeminiClient(_settings())
    result = await gc.generate_structured(prompt="hi", schema=_Out)
    assert result.value == "ok"
    assert calls["n"] == 3


async def test_generate_gives_up_on_non_retryable(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_models = MagicMock()
    fake_models.generate_content = AsyncMock(side_effect=ValueError("invalid argument"))
    fake_genai = MagicMock()
    fake_genai.Client.return_value = SimpleNamespace(aio=SimpleNamespace(models=fake_models))
    monkeypatch.setattr("app.ai.gemini_client.genai", fake_genai)
    monkeypatch.setattr("app.ai.gemini_client.types", MagicMock())

    gc = GeminiClient(_settings())
    with pytest.raises(AppError) as exc:
        await gc.generate_structured(prompt="hi", schema=_Out)
    assert exc.value.code == ErrorCode.GEMINI_UNAVAILABLE
    assert fake_models.generate_content.await_count == 1

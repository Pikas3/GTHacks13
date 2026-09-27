"""One-off live TTS smoke test. Reads credentials from repo-root .env only."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings  # noqa: E402
from app.voice.elevenlabs_tts import ElevenLabsTTSProvider  # noqa: E402


async def main() -> None:
    settings = Settings()
    print("voice_mocked", settings.voice_is_mocked)
    print("voice_id_set", bool(settings.elevenlabs_voice_id))
    print("key_set", settings.elevenlabs_api_key is not None)
    if settings.voice_is_mocked:
        print("SKIP: voice is mocked")
        return
    async with httpx.AsyncClient(timeout=30.0) as http:
        tts = ElevenLabsTTSProvider(settings, http)
        result = await tts.synthesize(
            "Hello from Impiricus Lepius. Novara prescribing information version 2."
        )
        print("bytes", len(result.audio), "type", result.media_type, "provider", result.provider)


if __name__ == "__main__":
    asyncio.run(main())

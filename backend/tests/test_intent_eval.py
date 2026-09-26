"""Intent eval harness over demo_queries.json (mock always; Gemini when RUN_LIVE_AI=1)."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from app.ai.intent import GeminiIntentClassifier, MockIntentClassifier
from app.config import get_settings
from app.schemas.conversation import ConversationContext
from app.schemas.enums import IntentType, TemporalReference

FIXTURE = Path(__file__).parent / "fixtures" / "demo_queries.json"


def _cases() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _context(raw: dict) -> ConversationContext:
    return ConversationContext(**{k: v for k, v in raw.items() if v is not None})


@pytest.mark.parametrize("case", _cases(), ids=lambda c: c["id"])
async def test_mock_intent_eval_harness(case: dict) -> None:
    expected = case["expected"]
    result = await MockIntentClassifier().classify(case["query"], _context(case.get("context") or {}))
    assert result.intent == IntentType(expected["intent"])
    if "product" in expected:
        assert result.product == expected["product"]
    if "topic" in expected:
        assert result.topic == expected["topic"]
    if "temporal_reference" in expected:
        assert result.temporal_reference == TemporalReference(expected["temporal_reference"])


@pytest.mark.skipif(os.getenv("RUN_LIVE_AI") != "1", reason="Set RUN_LIVE_AI=1 with GOOGLE_API_KEY to run")
async def test_live_gemini_intent_eval_accuracy() -> None:
    settings = get_settings()
    if settings.ai_is_mocked or not settings.google_api_key:
        pytest.skip("live Gemini not configured")
    from app.ai.gemini_client import GeminiClient

    classifier = GeminiIntentClassifier(GeminiClient(settings))
    cases = _cases()
    hits = 0
    for i, case in enumerate(cases):
        # Free-tier generate limits are tight (~15 RPM); pace live calls.
        if i:
            await asyncio.sleep(4.5)
        result = await classifier.classify(case["query"], _context(case.get("context") or {}))
        if result.intent == IntentType(case["expected"]["intent"]):
            hits += 1
    accuracy = hits / len(cases)
    assert accuracy >= 0.9, f"live intent accuracy {accuracy:.0%} < 90% ({hits}/{len(cases)})"

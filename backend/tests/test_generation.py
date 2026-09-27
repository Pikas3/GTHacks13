"""Grounding post-condition guards for GeminiResponseGenerator."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

from app.ai.generation import GeminiResponseGenerator, GeneratedAnswer, GenerationRequest, enforce_grounding_guards
from app.schemas.lepius import EvidenceReference, HCPContext
from app.schemas.conversation import ConversationContext
from app.schemas.enums import IntentType, ResourceType
from app.schemas.hcp import HCPRead


def _evidence(*ids: str) -> list[EvidenceReference]:
    return [
        EvidenceReference(
            id=eid,
            resource_id=uuid4(),
            chunk_id=uuid4(),
            title="Novara PI",
            product="Novara",
            resource_type=ResourceType.PRESCRIBING_INFORMATION,
            version="2.0",
            section="Renal Impairment",
            published_at=datetime(2026, 8, 4, tzinfo=UTC),
            excerpt="Regimen A-R for moderate renal impairment.",
        )
        for eid in ids
    ]


def test_enforce_strips_invented_citations_and_truncates_speech() -> None:
    long_speech = " ".join(["word"] * 60) + " [E9] leftover"
    answer = GeneratedAnswer(
        text="Claim [E1] and invented [E9] plus [E2].",
        speech_text=long_speech,
        cited_evidence_ids=["E1", "E9", "E2"],
        insufficient_evidence=False,
    )
    out = enforce_grounding_guards(answer, _evidence("E1", "E2"))
    assert "[E9]" not in out.text
    assert "[E1]" in out.text and "[E2]" in out.text
    assert "E9" not in out.cited_evidence_ids
    assert "[" not in out.speech_text
    assert len(out.speech_text.split()) <= 45
    assert not out.insufficient_evidence


def test_enforce_forces_insufficient_when_no_evidence() -> None:
    answer = GeneratedAnswer(text="Something invented.", speech_text="Something invented.", insufficient_evidence=False)
    out = enforce_grounding_guards(answer, [])
    assert out.insufficient_evidence


async def test_gemini_generator_applies_guards() -> None:
    client = AsyncMock()
    client.generate_structured = AsyncMock(
        return_value=GeneratedAnswer(
            text="Bad cite [E99] and good [E1].",
            speech_text=" ".join(["spoken"] * 50),
            cited_evidence_ids=["E99", "E1"],
        )
    )
    gen = GeminiResponseGenerator(client)
    req = GenerationRequest(
        query="renal?",
        intent=IntentType.QUESTION_ANSWERING,
        product="Novara",
        hcp_context=HCPContext(
            hcp=HCPRead(
                id=uuid4(),
                external_id="SYN",
                name="Dr. Test",
                specialty="Oncology",
            )
        ),
        conversation=ConversationContext(),
        evidence=_evidence("E1"),
    )
    out = await gen.generate(req)
    assert "[E99]" not in out.text
    assert "[E1]" in out.text
    assert len(out.speech_text.split()) <= 45

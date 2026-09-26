"""Semantic diff alignment + cache behavior."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

from app.ai.semantic_diff import GeminiSemanticDiffService, MockSemanticDiffService, align_sections
from app.schemas.diff import SectionChange, SemanticDiff
from app.schemas.enums import ChangeType, Importance, ResourceType
from app.schemas.resource import ResourceChunkRead, ResourceDetail


def _detail(title: str, version: str, sections: dict[str, str]) -> ResourceDetail:
    rid = uuid4()
    chunks = [
        ResourceChunkRead(id=uuid4(), resource_id=rid, chunk_index=i, text=text, section=heading)
        for i, (heading, text) in enumerate(sections.items())
    ]
    return ResourceDetail(
        id=rid,
        title=title,
        product="Novara",
        resource_type=ResourceType.PRESCRIBING_INFORMATION,
        version=version,
        published_at=datetime(2026, 8, 1, tzinfo=UTC),
        chunks=chunks,
    )


def test_align_sections_exact_and_similarity() -> None:
    old = {"Renal Impairment": "dose reduce for kidney", "Safety": "alpha events"}
    new = {"Renal Impairment": "dose reduce for kidney and monitor", "Safety Overview": "alpha and beta events"}
    pairs = align_sections(old, new)
    headings = {h for h, _, _ in pairs}
    assert "Renal Impairment" in headings
    # Safety ≈ Safety Overview via bag-of-words
    assert any(h in {"Safety", "Safety Overview"} for h in headings)


async def test_mock_diff_marks_renal_updated_high(resources) -> None:
    # Use seeded novara pi v1/v2 via keys on fake repo
    by_title_ver = {(r.title, r.version): r for r in resources.resources.values()}
    old = await resources.get_detail(by_title_ver[("Novara Prescribing Information", "1.0")].id)
    new = await resources.get_detail(by_title_ver[("Novara Prescribing Information", "2.0")].id)
    assert old and new
    diff = await MockSemanticDiffService().compare(old, new)
    renal = next(c for c in diff.changes if c.topic == "Renal Impairment")
    assert renal.change_type == ChangeType.UPDATED
    assert renal.importance == Importance.HIGH


async def test_gemini_diff_caches_and_only_sends_changed_pairs() -> None:
    client = AsyncMock()
    client.generate_structured = AsyncMock(
        return_value=SemanticDiff(
            resource="PI",
            old_version="1.0",
            new_version="2.0",
            changes=[
                SectionChange(
                    topic="Renal Impairment",
                    change_type=ChangeType.UPDATED,
                    importance=Importance.HIGH,
                    summary="Renal guidance expanded.",
                )
            ],
        )
    )
    svc = GeminiSemanticDiffService(client)
    old = _detail("PI", "1.0", {"Renal Impairment": "old renal", "Safety": "same"})
    new = _detail("PI", "2.0", {"Renal Impairment": "new renal", "Safety": "same"})
    first = await svc.compare(old, new)
    await svc.compare(old, new)
    assert first.changes[0].importance == Importance.HIGH
    assert client.generate_structured.await_count == 1  # cache hit on second
    prompt = client.generate_structured.await_args.kwargs["prompt"]
    assert "Renal Impairment" in prompt
    # Unchanged Safety section should not be in the Gemini prompt payload.
    assert "## Safety\n(same)" not in prompt and "## Safety\nsame" not in prompt

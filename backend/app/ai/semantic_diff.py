"""Semantic comparison of two versions of a resource (e.g. PI v1 -> v2)."""

from typing import Protocol

from app.ai.gemini_client import GeminiClient
from app.ai.prompts import DIFF_PROMPT, DIFF_SYSTEM
from app.schemas.diff import SectionChange, SemanticDiff
from app.schemas.enums import ChangeType, Importance
from app.schemas.resource import ResourceDetail

# Heuristic for the mock diff only. TODO(diff): let Gemini grade importance.
HIGH_IMPORTANCE_TERMS = ("renal", "hepatic", "warning", "contraindication", "boxed")


class SemanticDiffService(Protocol):
    async def compare(
        self, old: ResourceDetail, new: ResourceDetail, timings: dict[str, float] | None = None
    ) -> SemanticDiff: ...


def _sections(detail: ResourceDetail) -> dict[str, str]:
    out: dict[str, str] = {}
    for c in detail.chunks:
        key = c.section or "General"
        out[key] = (out.get(key, "") + " " + c.text).strip()
    return out


def _importance(section: str) -> Importance:
    return Importance.HIGH if any(t in section.lower() for t in HIGH_IMPORTANCE_TERMS) else Importance.MEDIUM


class MockSemanticDiffService:
    """Deterministic section-level diff: compares chunk text per section heading."""

    async def compare(
        self, old: ResourceDetail, new: ResourceDetail, timings: dict[str, float] | None = None
    ) -> SemanticDiff:
        a, b = _sections(old), _sections(new)
        changes: list[SectionChange] = []
        for section, new_text in b.items():
            old_text = a.get(section)
            if old_text is None:
                changes.append(
                    SectionChange(
                        topic=section,
                        change_type=ChangeType.ADDED,
                        importance=_importance(section),
                        summary=f"New section '{section}' added in v{new.version}.",
                        new_evidence=new_text[:400],
                    )
                )
            elif old_text != new_text:
                changes.append(
                    SectionChange(
                        topic=section,
                        change_type=ChangeType.UPDATED,
                        importance=_importance(section),
                        summary=f"The '{section}' section was updated between v{old.version} and v{new.version}.",
                        old_evidence=old_text[:400],
                        new_evidence=new_text[:400],
                    )
                )
        for section, old_text in a.items():
            if section not in b:
                changes.append(
                    SectionChange(
                        topic=section,
                        change_type=ChangeType.REMOVED,
                        importance=Importance.LOW,
                        summary=f"Section '{section}' no longer appears in v{new.version}.",
                        old_evidence=old_text[:400],
                    )
                )
        changes.sort(key=lambda c: c.importance != Importance.HIGH)
        return SemanticDiff(resource=new.title, old_version=old.version, new_version=new.version, changes=changes)


class GeminiSemanticDiffService:
    """Minimal Gemini-backed diff.

    TODO(diff): Implement structured Gemini semantic diff per section (align sections first,
    then ask Gemini only about changed pairs) and attach chunk IDs as evidence.
    """

    def __init__(self, client: GeminiClient) -> None:
        self.client = client

    async def compare(
        self, old: ResourceDetail, new: ResourceDetail, timings: dict[str, float] | None = None
    ) -> SemanticDiff:
        def render(d: ResourceDetail) -> str:
            return "\n".join(f"## {s}\n{t}" for s, t in _sections(d).items())

        prompt = DIFF_PROMPT.format(
            title=new.title,
            old_version=old.version,
            new_version=new.version,
            old_text=render(old),
            new_text=render(new),
        )
        return await self.client.generate_structured(
            prompt=prompt,
            schema=SemanticDiff,
            system_instruction=DIFF_SYSTEM,
            temperature=0.0,
            operation="gemini.diff",
            timings=timings,
        )

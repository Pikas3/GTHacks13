"""Semantic comparison of two versions of a resource (e.g. PI v1 -> v2)."""

from __future__ import annotations

import math
import re
from typing import Protocol
from uuid import UUID

from app.ai.gemini_client import GeminiClient
from app.ai.prompts import DIFF_PROMPT, DIFF_SYSTEM
from app.schemas.diff import SectionChange, SemanticDiff
from app.schemas.enums import ChangeType, Importance
from app.schemas.resource import ResourceDetail

# Heuristic for the mock diff only (and Gemini fallback when importance is missing).
HIGH_IMPORTANCE_TERMS = ("renal", "hepatic", "warning", "contraindication", "boxed", "dosing")
_TOKEN = re.compile(r"[a-z0-9]+")


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


def _bow(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for t in _TOKEN.findall(text.lower()):
        counts[t] = counts.get(t, 0) + 1
    return counts


def _cosine(a: dict[str, int], b: dict[str, int]) -> float:
    if not a or not b:
        return 0.0
    keys = set(a) | set(b)
    dot = sum(a.get(k, 0) * b.get(k, 0) for k in keys)
    na = math.sqrt(sum(v * v for v in a.values())) or 1.0
    nb = math.sqrt(sum(v * v for v in b.values())) or 1.0
    return dot / (na * nb)


def align_sections(
    old: dict[str, str], new: dict[str, str], *, sim_threshold: float = 0.45
) -> list[tuple[str, str | None, str | None]]:
    """Align sections by exact heading, then by bag-of-words similarity for leftovers."""
    pairs: list[tuple[str, str | None, str | None]] = []
    used_old: set[str] = set()
    used_new: set[str] = set()

    for heading in sorted(set(old) & set(new)):
        pairs.append((heading, old[heading], new[heading]))
        used_old.add(heading)
        used_new.add(heading)

    remaining_old = [(h, t) for h, t in old.items() if h not in used_old]
    remaining_new = [(h, t) for h, t in new.items() if h not in used_new]
    old_vecs = [(h, t, _bow(t)) for h, t in remaining_old]
    new_vecs = [(h, t, _bow(t)) for h, t in remaining_new]

    for nh, nt, nv in new_vecs:
        best_i, best_sim = -1, 0.0
        for i, (oh, _ot, ov) in enumerate(old_vecs):
            if oh in used_old:
                continue
            sim = _cosine(ov, nv)
            if sim > best_sim:
                best_i, best_sim = i, sim
        if best_i >= 0 and best_sim >= sim_threshold:
            oh, ot, _ = old_vecs[best_i]
            pairs.append((nh, ot, nt))
            used_old.add(oh)
            used_new.add(nh)
        else:
            pairs.append((nh, None, nt))
            used_new.add(nh)

    for oh, ot in remaining_old:
        if oh not in used_old:
            pairs.append((oh, ot, None))

    return pairs


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
    """Section-aligned Gemini diff with in-process cache keyed by (old_id, new_id)."""

    def __init__(self, client: GeminiClient) -> None:
        self.client = client
        self._cache: dict[tuple[UUID, UUID], SemanticDiff] = {}

    async def compare(
        self, old: ResourceDetail, new: ResourceDetail, timings: dict[str, float] | None = None
    ) -> SemanticDiff:
        cache_key = (old.id, new.id)
        if cache_key in self._cache:
            return self._cache[cache_key]

        old_secs, new_secs = _sections(old), _sections(new)
        aligned = align_sections(old_secs, new_secs)
        changed_pairs = [(h, o, n) for h, o, n in aligned if (o or "") != (n or "")]
        if not changed_pairs:
            result = SemanticDiff(resource=new.title, old_version=old.version, new_version=new.version, changes=[])
            self._cache[cache_key] = result
            return result

        def render_side(pairs: list[tuple[str, str | None, str | None]], which: str) -> str:
            blocks: list[str] = []
            for heading, o, n in pairs:
                text = o if which == "old" else n
                if text is None:
                    blocks.append(f"## {heading}\n(absent)")
                else:
                    blocks.append(f"## {heading}\n{text}")
            return "\n\n".join(blocks)

        prompt = DIFF_PROMPT.format(
            title=new.title,
            old_version=old.version,
            new_version=new.version,
            old_text=render_side(changed_pairs, "old"),
            new_text=render_side(changed_pairs, "new"),
        )
        result = await self.client.generate_structured(
            prompt=prompt,
            schema=SemanticDiff,
            system_instruction=DIFF_SYSTEM,
            temperature=0.0,
            operation="gemini.diff",
            timings=timings,
        )
        # Ensure resource/version metadata and fill missing importance heuristically.
        fixed_changes: list[SectionChange] = []
        for c in result.changes:
            importance = c.importance or _importance(c.topic)
            fixed_changes.append(c.model_copy(update={"importance": importance}))
        result = SemanticDiff(
            resource=new.title,
            old_version=old.version,
            new_version=new.version,
            changes=fixed_changes,
        )
        self._cache[cache_key] = result
        return result

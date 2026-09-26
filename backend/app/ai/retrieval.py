"""Personalized retrieval over approved resource chunks.

The retriever receives a `RetrievalPlan` (built by the orchestrator's context resolution) and
returns ranked `RetrievalResult`s. Ranking rules live HERE, never in API handlers.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel

from app.ai.embeddings import EmbeddingProvider
from app.ai.vocabulary import ENTITY_ALIASES
from app.db.repositories.interfaces import ResourceRepository
from app.observability import timed
from app.schemas.ambient import HCPContext
from app.schemas.conversation import ConversationContext
from app.schemas.enums import ResourceType
from app.schemas.resource import ChunkHit
from app.schemas.retrieval import RetrievalPlan, RetrievalResult, ScoreBreakdown

# Preference key → resource types / section keywords that should be boosted.
_PREF_RESOURCE_TYPES: dict[str, frozenset[ResourceType]] = {
    "clinical_evidence": frozenset({ResourceType.CLINICAL_STUDY}),
    "long_term_outcomes": frozenset({ResourceType.CLINICAL_STUDY}),
    "patient_access": frozenset({ResourceType.ACCESS_GUIDE}),
    "patient_resources": frozenset({ResourceType.EDUCATIONAL_RESOURCE, ResourceType.ACCESS_GUIDE}),
    "dosing_information": frozenset({ResourceType.PRESCRIBING_INFORMATION}),
    "safety": frozenset({ResourceType.PRESCRIBING_INFORMATION, ResourceType.EDUCATIONAL_RESOURCE}),
}
_PREF_SECTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "dosing_information": ("dosing", "dose", "administration", "titration"),
    "safety": ("safety", "adverse", "warning", "contraindication"),
    "patient_access": ("access", "coverage", "prior authorization", "copay"),
    "clinical_evidence": ("efficacy", "endpoint", "trial", "study"),
    "long_term_outcomes": ("long-term", "follow-up", "durability", "ltfu"),
}


class ResourceRetriever(Protocol):
    async def search(
        self,
        plan: RetrievalPlan,
        hcp_context: HCPContext,
        conversation_context: ConversationContext,
        timings: dict[str, float] | None = None,
    ) -> list[RetrievalResult]: ...


class RankingWeights(BaseModel):
    """Hackathon heuristic weights. Tune freely; keep them in one place."""

    semantic: float = 0.42
    lexical: float = 0.12
    entity_match: float = 0.12
    topic_match: float = 0.12
    preference: float = 0.08
    recency: float = 0.04
    interest: float = 0.04
    previously_viewed: float = -0.03  # slight preference for unseen material
    new_since_last_view: float = 0.12
    recency_half_life_days: float = 180.0
    max_chunks_per_resource: int = 2
    rrf_k: int = 60


def _topic_terms(topic: str | None) -> tuple[str, ...]:
    if not topic:
        return ()
    _, aliases = ENTITY_ALIASES.get(topic, (None, ()))
    return (topic.lower(), *aliases)


def _rrf_scores(ranked_lists: list[list[ChunkHit]], k: int) -> dict[UUID, float]:
    """Reciprocal-rank fusion over chunk ids."""
    scores: dict[UUID, float] = {}
    for hits in ranked_lists:
        for rank, hit in enumerate(hits, start=1):
            scores[hit.chunk.id] = scores.get(hit.chunk.id, 0.0) + 1.0 / (k + rank)
    return scores


def _preference_boost(hit: ChunkHit, ctx: HCPContext) -> float:
    if not ctx.preferences:
        return 0.0
    section = (hit.chunk.section or "").lower()
    text = hit.chunk.text.lower()
    haystack = f"{section} {text}"
    best = 0.0
    for pref in ctx.preferences:
        key = pref.key.lower()
        types = _PREF_RESOURCE_TYPES.get(key)
        type_hit = 1.0 if types and hit.resource.resource_type in types else 0.0
        keywords = _PREF_SECTION_KEYWORDS.get(key, ())
        section_hit = 1.0 if keywords and any(kw in haystack for kw in keywords) else 0.0
        signal = max(type_hit, section_hit * 0.85)
        if signal > 0:
            best = max(best, pref.weight * signal)
    return best


class HybridResourceRetriever:
    """pgvector + lexical candidate generation, RRF fusion, personalized re-ranking."""

    def __init__(
        self,
        resources: ResourceRepository,
        embedder: EmbeddingProvider,
        *,
        candidate_pool: int = 40,
        weights: RankingWeights | None = None,
    ) -> None:
        self.resources = resources
        self.embedder = embedder
        self.candidate_pool = candidate_pool
        self.weights = weights or RankingWeights()

    async def search(
        self,
        plan: RetrievalPlan,
        hcp_context: HCPContext,
        conversation_context: ConversationContext,
        timings: dict[str, float] | None = None,
    ) -> list[RetrievalResult]:
        query_text = " ".join(filter(None, [plan.query, plan.product, plan.topic]))
        embedding = await self.embedder.embed_query(query_text, timings=timings)
        search_kwargs = dict(
            limit=self.candidate_pool,
            product=plan.product,
            published_after=plan.published_after,
            exclude_superseded=not plan.include_superseded,
        )
        with timed("retrieval.vector_search", timings, strategy=plan.strategy):
            vector_hits = await self.resources.vector_search(embedding, **search_kwargs)
        with timed("retrieval.lexical_search", timings, strategy=plan.strategy):
            lexical_hits = await self.resources.lexical_search(query_text, **search_kwargs)

        by_id: dict[UUID, ChunkHit] = {h.chunk.id: h for h in vector_hits}
        for h in lexical_hits:
            by_id.setdefault(h.chunk.id, h)

        rrf = _rrf_scores([vector_hits, lexical_hits], self.weights.rrf_k)
        # Normalize RRF into ~[0,1] using the theoretical max of two rank-1 contributions.
        rrf_ceil = 2.0 / (self.weights.rrf_k + 1)
        fused: list[ChunkHit] = []
        for chunk_id, rrf_score in sorted(rrf.items(), key=lambda kv: kv[1], reverse=True):
            hit = by_id[chunk_id]
            fused.append(
                ChunkHit(
                    chunk=hit.chunk,
                    resource=hit.resource,
                    similarity=max(hit.similarity, 0.0),
                    lexical_score=min(rrf_score / rrf_ceil, 1.0) if rrf_ceil else 0.0,
                )
            )

        ranked = sorted(
            (self._score(h, plan, hcp_context) for h in fused),
            key=lambda r: r.score,
            reverse=True,
        )
        return self._diversify(ranked, plan.limit)

    def _score(self, hit: ChunkHit, plan: RetrievalPlan, ctx: HCPContext) -> RetrievalResult:
        w = self.weights
        resource, chunk = hit.resource, hit.chunk
        haystack = f"{chunk.section or ''} {chunk.text}".lower()
        age_days = max((datetime.now(UTC) - resource.published_at).days, 0)
        last_seen = ctx.last_entity_review.timestamp if ctx.last_entity_review else None
        viewed = resource.id in ctx.viewed_resource_ids
        is_new = bool(last_seen and resource.published_at > last_seen)
        pref = _preference_boost(hit, ctx)

        b = ScoreBreakdown(
            semantic=max(hit.similarity, 0.0),
            lexical=hit.lexical_score,
            entity_match=1.0 if plan.product and resource.product.lower() == plan.product.lower() else 0.0,
            recency=math.exp(-age_days / w.recency_half_life_days),
            interest=max(ctx.interest_score(resource.product), ctx.interest_score(plan.topic)),
            preference=pref,
            previously_viewed=1.0 if viewed else 0.0,
            new_since_last_view=1.0 if is_new else 0.0,
        )
        topic_match = 1.0 if any(t in haystack for t in _topic_terms(plan.topic)) else 0.0
        score = (
            w.semantic * b.semantic
            + w.lexical * b.lexical
            + w.entity_match * b.entity_match
            + w.topic_match * topic_match
            + w.preference * b.preference
            + w.recency * b.recency
            + w.interest * b.interest
            + w.previously_viewed * b.previously_viewed
            + w.new_since_last_view * b.new_since_last_view
        )
        return RetrievalResult(
            chunk=chunk,
            resource=resource,
            score=round(score, 4),
            breakdown=b,
            previously_viewed=viewed,
            is_new_since_last_view=is_new,
        )

    def _diversify(self, ranked: list[RetrievalResult], limit: int) -> list[RetrievalResult]:
        per_resource: dict[object, int] = {}
        out: list[RetrievalResult] = []
        for r in ranked:
            n = per_resource.get(r.resource.id, 0)
            if n >= self.weights.max_chunks_per_resource:
                continue
            per_resource[r.resource.id] = n + 1
            out.append(r)
            if len(out) >= limit:
                break
        return out

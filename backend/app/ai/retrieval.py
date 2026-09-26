"""Personalized retrieval over approved resource chunks.

The retriever receives a `RetrievalPlan` (built by the orchestrator's context resolution) and
returns ranked `RetrievalResult`s. Ranking rules live HERE, never in API handlers.
"""

import math
from datetime import UTC, datetime
from typing import Protocol

from pydantic import BaseModel

from app.ai.embeddings import EmbeddingProvider
from app.ai.vocabulary import ENTITY_ALIASES
from app.db.repositories.interfaces import ResourceRepository
from app.observability import timed
from app.schemas.ambient import HCPContext
from app.schemas.conversation import ConversationContext
from app.schemas.resource import ChunkHit
from app.schemas.retrieval import RetrievalPlan, RetrievalResult, ScoreBreakdown


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

    semantic: float = 0.50
    entity_match: float = 0.15
    topic_match: float = 0.15
    recency: float = 0.05
    interest: float = 0.05
    previously_viewed: float = -0.03  # slight preference for unseen material
    new_since_last_view: float = 0.13
    recency_half_life_days: float = 180.0
    max_chunks_per_resource: int = 2


def _topic_terms(topic: str | None) -> tuple[str, ...]:
    if not topic:
        return ()
    _, aliases = ENTITY_ALIASES.get(topic, (None, ()))
    return (topic.lower(), *aliases)


class HybridResourceRetriever:
    """pgvector candidate generation + lightweight personalized re-ranking.

    TODO(ai-rag): Implement personalized hybrid retrieval ranking — add lexical/BM25 scoring
    (Postgres full-text), learn weights from demo queries, and use HCP preferences
    (e.g. `clinical_evidence` vs `patient_access`) to boost resource types.
    """

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
        with timed("retrieval.vector_search", timings, strategy=plan.strategy):
            hits = await self.resources.vector_search(
                embedding,
                limit=self.candidate_pool,
                product=plan.product,
                published_after=plan.published_after,
                exclude_superseded=not plan.include_superseded,
            )
        ranked = sorted((self._score(h, plan, hcp_context) for h in hits), key=lambda r: r.score, reverse=True)
        return self._diversify(ranked, plan.limit)

    def _score(self, hit: ChunkHit, plan: RetrievalPlan, ctx: HCPContext) -> RetrievalResult:
        w = self.weights
        resource, chunk = hit.resource, hit.chunk
        haystack = f"{chunk.section or ''} {chunk.text}".lower()
        age_days = max((datetime.now(UTC) - resource.published_at).days, 0)
        last_seen = ctx.last_entity_review.timestamp if ctx.last_entity_review else None
        viewed = resource.id in ctx.viewed_resource_ids
        is_new = bool(last_seen and resource.published_at > last_seen)

        b = ScoreBreakdown(
            semantic=max(hit.similarity, 0.0),
            entity_match=1.0 if plan.product and resource.product.lower() == plan.product.lower() else 0.0,
            recency=math.exp(-age_days / w.recency_half_life_days),
            interest=max(ctx.interest_score(resource.product), ctx.interest_score(plan.topic)),
            previously_viewed=1.0 if viewed else 0.0,
            new_since_last_view=1.0 if is_new else 0.0,
        )
        topic_match = 1.0 if any(t in haystack for t in _topic_terms(plan.topic)) else 0.0
        score = (
            w.semantic * b.semantic
            + w.entity_match * b.entity_match
            + w.topic_match * topic_match
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

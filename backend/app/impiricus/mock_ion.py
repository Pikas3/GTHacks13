"""MockIONService — stands in for Impiricus's existing HCP intelligence platform.

Everything here is a simplified, transparent stand-in built on the prototype database.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from app.db.repositories.interfaces import HCPRepository, InteractionRepository, ResourceRepository
from app.errors import AppError, ErrorCode
from app.impiricus.signals import DEFAULT_HALF_LIFE_DAYS, decay_score, effective_interests, next_score
from app.schemas.ambient import HCPContext
from app.schemas.enums import REVIEW_EVENT_TYPES, EntityType
from app.schemas.hcp import HCPInterestRead
from app.schemas.intelligence import Recommendation
from app.schemas.signals import EngagementSignal


class MockIONService:
    def __init__(
        self,
        hcps: HCPRepository,
        interactions: InteractionRepository,
        resources: ResourceRepository,
        *,
        half_life_days: float = DEFAULT_HALF_LIFE_DAYS,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.hcps = hcps
        self.interactions = interactions
        self.resources = resources
        self.half_life_days = half_life_days
        self.clock = clock

    async def get_hcp_context(self, hcp_id: UUID, entity: str | None = None) -> HCPContext:
        hcp = await self.hcps.get_hcp(hcp_id)
        if hcp is None:
            raise AppError(ErrorCode.INVALID_HCP, f"Unknown HCP {hcp_id}")
        return HCPContext(
            hcp=hcp,
            preferences=await self.hcps.get_preferences(hcp_id),
            interests=await self.get_topic_affinities(hcp_id),
            recent_interactions=await self.interactions.recent(hcp_id, limit=10),
            viewed_resource_ids=await self.interactions.viewed_resource_ids(hcp_id),
            last_entity_review=(
                await self.interactions.last_with_entity(hcp_id, entity, event_types=set(REVIEW_EVENT_TYPES))
                if entity
                else None
            ),
        )

    async def record_signal(self, signal: EngagementSignal) -> EngagementSignal:
        at = signal.timestamp or self.clock()
        interests = await self.hcps.get_interests(signal.hcp_id)
        current = next((i for i in interests if i.entity.lower() == signal.entity.lower()), None)
        # Decay the stored score up to now, then add this event's weight.
        old = decay_score(current.score, current.last_interaction_at, at, self.half_life_days) if current else 0.0
        new = next_score(old, signal.weight)
        await self.hcps.upsert_interest(signal.hcp_id, signal.entity, signal.entity_type, new, at)
        return signal.model_copy(update={"new_score": new})

    async def get_topic_affinities(self, hcp_id: UUID) -> list[HCPInterestRead]:
        """Current (time-decayed) interest scores, highest first."""
        return effective_interests(await self.hcps.get_interests(hcp_id), self.clock(), self.half_life_days)

    async def get_recommended_resource(self, hcp_id: UUID, limit: int = 3) -> list[Recommendation]:
        """Newest unseen resources for the HCP's highest-affinity products.

        Affinity-based tip for the Impiricus panel; retrieval personalization lives in HybridResourceRetriever.
        """
        affinities = await self.get_topic_affinities(hcp_id)
        viewed = await self.interactions.viewed_resource_ids(hcp_id)
        product_scores = {a.entity.lower(): a.score for a in affinities if a.entity_type == EntityType.PRODUCT}
        topic_names = [a.entity for a in affinities if a.entity_type != EntityType.PRODUCT][:2]
        catalog = await self.resources.list_resources()
        superseded = {r.supersedes_resource_id for r in catalog if r.supersedes_resource_id}
        recs: list[Recommendation] = []
        for r in catalog:
            if r.id in viewed or r.id in superseded or not r.is_approved:
                continue
            affinity = product_scores.get(r.product.lower(), 0.0)
            if affinity <= 0:
                continue
            topics = f" and interest in {', '.join(topic_names)}" if topic_names else ""
            recs.append(
                Recommendation(
                    resource=r,
                    score=round(affinity, 3),
                    reason=f"Not yet viewed; {r.product} affinity {affinity:.2f}{topics}.",
                )
            )
        recs.sort(key=lambda x: (x.score, x.resource.published_at), reverse=True)
        return recs[:limit]

    async def get_recent_signals(self, hcp_id: UUID, limit: int = 20) -> list[EngagementSignal]:
        events = await self.interactions.recent(hcp_id, limit=limit)
        signals: list[EngagementSignal] = []
        for ev in events:
            for raw in ev.metadata.get("signals", []):
                signals.append(EngagementSignal.model_validate(raw))
        return signals[:limit]

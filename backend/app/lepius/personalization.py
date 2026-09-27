"""Turns interactions into engagement signals and interest-score updates (via the ION layer)."""

from datetime import UTC, datetime
from uuid import UUID

from app.db.repositories.interfaces import InteractionRepository, ResourceRepository
from app.impiricus.interfaces import IONService
from app.impiricus.signals import build_signals
from app.schemas.lepius import EngagementEventRequest
from app.schemas.enums import EntityType, EventType, IntentType
from app.schemas.intent import ExtractedEntity
from app.schemas.interaction import InteractionEventCreate, InteractionEventRead
from app.schemas.signals import EngagementSignal


class PersonalizationService:
    def __init__(self, ion: IONService) -> None:
        self.ion = ion

    async def apply(
        self,
        *,
        hcp_id: UUID,
        event_type: EventType,
        entities: list[ExtractedEntity],
        topic: str | None,
        intent: IntentType | None,
        at: datetime | None = None,
    ) -> list[EngagementSignal]:
        signals = build_signals(
            hcp_id=hcp_id,
            event_type=event_type,
            entities=entities,
            topic=topic,
            intent=intent,
            at=at or datetime.now(UTC),
        )
        return [await self.ion.record_signal(s) for s in signals]


class EngagementService:
    """Records client-reported engagement (e.g. SOURCE_OPEN from an evidence card)."""

    def __init__(
        self,
        interactions: InteractionRepository,
        resources: ResourceRepository,
        personalization: PersonalizationService,
    ) -> None:
        self.interactions = interactions
        self.resources = resources
        self.personalization = personalization

    async def record(self, req: EngagementEventRequest) -> tuple[InteractionEventRead, list[EngagementSignal]]:
        entity = req.entity
        if req.resource_id and not entity:
            resource = await self.resources.get_resource(req.resource_id)
            entity = resource.product if resource else None
        entities = [ExtractedEntity(name=entity, type=EntityType.PRODUCT)] if entity else []
        now = datetime.now(UTC)
        signals = await self.personalization.apply(
            hcp_id=req.hcp_id, event_type=req.event_type, entities=entities, topic=req.topic, intent=None, at=now
        )
        event = await self.interactions.record(
            InteractionEventCreate(
                hcp_id=req.hcp_id,
                session_id=req.session_id,
                event_type=req.event_type,
                timestamp=now,
                entity=entity,
                topic=req.topic,
                resource_id=req.resource_id,
                metadata={"signals": [s.model_dump(mode="json") for s in signals]},
            )
        )
        return event, signals

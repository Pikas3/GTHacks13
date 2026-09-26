"""Structured personal memory.

Memory is a set of explicit queries over the interaction_event time series and the resource
catalog — NOT an LLM conversation dump.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.db.repositories.interfaces import InteractionRepository, ResourceRepository
from app.schemas.enums import REVIEW_EVENT_TYPES, EventType
from app.schemas.interaction import InteractionEventRead, TimelineEntry
from app.schemas.resource import ResourceRead


class WhatsNew(BaseModel):
    entity: str
    last_interaction: InteractionEventRead | None = None
    new_resources: list[ResourceRead] = Field(default_factory=list)
    # (previous version, new version) pairs where a new resource supersedes an older one
    superseded_pairs: list[tuple[ResourceRead, ResourceRead]] = Field(default_factory=list)


def timeline_label(ev: InteractionEventRead) -> str:
    title = ev.resource_title or "a resource"
    match ev.event_type:
        case EventType.RESOURCE_VIEW:
            return f"Viewed {title}"
        case EventType.SOURCE_OPEN:
            return f"Opened source: {title}"
        case EventType.RESOURCE_SAVED:
            return f"Saved {title}"
        case EventType.SESSION_STARTED:
            return "Started an Ambient session"
        case EventType.VOICE_QUERY | EventType.TEXT_QUERY | EventType.FOLLOW_UP:
            return f'Asked "{ev.query_text}"' if ev.query_text else f"Asked about {ev.topic or ev.entity}"
        case _:
            return ev.event_type.value.replace("_", " ").title()


class MemoryService:
    def __init__(self, interactions: InteractionRepository, resources: ResourceRepository) -> None:
        self.interactions = interactions
        self.resources = resources

    async def get_recent_interactions(self, hcp_id: UUID, limit: int = 20) -> list[InteractionEventRead]:
        return await self.interactions.recent(hcp_id, limit=limit)

    async def get_last_interaction_with_entity(self, hcp_id: UUID, entity: str) -> InteractionEventRead | None:
        return await self.interactions.last_with_entity(hcp_id, entity)

    async def get_last_review_of_entity(self, hcp_id: UUID, entity: str) -> InteractionEventRead | None:
        """Last time the HCP viewed/opened/saved material about `entity` (anchor for "what's new")."""
        return await self.interactions.last_with_entity(hcp_id, entity, event_types=set(REVIEW_EVENT_TYPES))

    async def get_viewed_resources(self, hcp_id: UUID, entity: str | None = None) -> list[ResourceRead]:
        ids = await self.interactions.viewed_resource_ids(hcp_id, entity)
        return await self.resources.get_many(list(ids))

    async def get_recent_topics(self, hcp_id: UUID, limit: int = 5) -> list[str]:
        return [t.entity for t in await self.interactions.top_entities(hcp_id, limit=limit)]

    async def get_resources_new_since(
        self, hcp_id: UUID, entity: str, timestamp: datetime | None
    ) -> list[ResourceRead]:
        return await self.resources.published_after(entity, timestamp)

    async def get_timeline(
        self, hcp_id: UUID, limit: int = 20, exclude_session_id: UUID | None = None
    ) -> list[TimelineEntry]:
        events = await self.interactions.recent(hcp_id, limit=limit)
        if exclude_session_id is not None:
            events = [e for e in events if e.session_id != exclude_session_id]
        return [
            TimelineEntry(
                id=e.id,
                timestamp=e.timestamp,
                event_type=e.event_type,
                label=timeline_label(e),
                entity=e.entity,
                topic=e.topic,
                resource_id=e.resource_id,
            )
            for e in events
            if e.event_type != EventType.SESSION_STARTED
        ]

    async def whats_new(self, hcp_id: UUID, entity: str, since: InteractionEventRead | None) -> WhatsNew:
        """'What's changed since I last looked at <entity>?'

        1. caller identified the entity; 2. `since` is the last interaction with it;
        3. find approved resources published after that timestamp;
        4. pair each new resource with the version it supersedes (for semantic diff).
        """
        new_resources = await self.get_resources_new_since(hcp_id, entity, since.timestamp if since else None)
        pairs: list[tuple[ResourceRead, ResourceRead]] = []
        for r in new_resources:
            prev = await self.resources.get_superseded(r.id)
            if prev is not None:
                pairs.append((prev, r))
        return WhatsNew(entity=entity, last_interaction=since, new_resources=new_resources, superseded_pairs=pairs)

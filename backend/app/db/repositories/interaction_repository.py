"""Engagement events on the `interaction_event` Timescale hypertable.

Example time-series queries live here (recent events, counts by topic, engagement over time,
top entities, activity since a timestamp, timeline). `time_bucket` is used when TimescaleDB is
installed; otherwise we fall back to `date_trunc` so plain PostgreSQL still works.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InteractionEvent, Resource
from app.schemas.enums import EventType
from app.schemas.intelligence import EngagementBucket, TopicAffinity
from app.schemas.interaction import InteractionEventCreate, InteractionEventRead

_RESOURCE_LABEL = (Resource.title + " v" + Resource.version).label("resource_label")

_BUCKETS = {"1 hour": "hour", "1 day": "day", "1 week": "week"}

_FIELDS = [
    "id",
    "timestamp",
    "hcp_id",
    "session_id",
    "event_type",
    "query_text",
    "response_text",
    "intent",
    "entity",
    "topic",
    "resource_id",
]


def _to_read(row: InteractionEvent, resource_title: str | None = None) -> InteractionEventRead:
    data = {f: getattr(row, f) for f in _FIELDS}
    return InteractionEventRead.model_validate(
        {**data, "metadata": row.metadata_ or {}, "resource_title": resource_title}
    )


class SqlInteractionRepository:
    def __init__(self, session: AsyncSession, *, use_timescale: bool = False) -> None:
        self.session = session
        self.use_timescale = use_timescale

    async def record(self, event: InteractionEventCreate) -> InteractionEventRead:
        row = InteractionEvent(
            timestamp=event.timestamp or datetime.now(UTC),
            hcp_id=event.hcp_id,
            session_id=event.session_id,
            event_type=event.event_type.value,
            query_text=event.query_text,
            response_text=event.response_text,
            intent=event.intent.value if event.intent else None,
            entity=event.entity,
            topic=event.topic,
            resource_id=event.resource_id,
            metadata_=event.metadata,
        )
        self.session.add(row)
        await self.session.flush()
        return _to_read(row)

    async def recent(
        self, hcp_id: UUID, *, limit: int = 20, since: datetime | None = None
    ) -> list[InteractionEventRead]:
        stmt = (
            select(InteractionEvent, _RESOURCE_LABEL)
            .outerjoin(Resource, Resource.id == InteractionEvent.resource_id)
            .where(InteractionEvent.hcp_id == hcp_id)
            .order_by(InteractionEvent.timestamp.desc())
            .limit(limit)
        )
        if since is not None:
            stmt = stmt.where(InteractionEvent.timestamp > since)
        return [_to_read(ev, title) for ev, title in (await self.session.execute(stmt)).all()]

    async def last_with_entity(
        self,
        hcp_id: UUID,
        entity: str,
        *,
        before: datetime | None = None,
        event_types: set[EventType] | None = None,
    ) -> InteractionEventRead | None:
        """Most recent interaction touching `entity` — either tagged directly or via a viewed resource."""
        stmt = (
            select(InteractionEvent, _RESOURCE_LABEL)
            .outerjoin(Resource, Resource.id == InteractionEvent.resource_id)
            .where(
                InteractionEvent.hcp_id == hcp_id,
                (InteractionEvent.entity.ilike(entity)) | (Resource.product.ilike(entity)),
            )
            .order_by(InteractionEvent.timestamp.desc())
            .limit(1)
        )
        if before is not None:
            stmt = stmt.where(InteractionEvent.timestamp < before)
        if event_types:
            stmt = stmt.where(InteractionEvent.event_type.in_([e.value for e in event_types]))
        row = (await self.session.execute(stmt)).first()
        return _to_read(row[0], row[1]) if row else None

    async def viewed_resource_ids(self, hcp_id: UUID, entity: str | None = None) -> set[UUID]:
        stmt = (
            select(InteractionEvent.resource_id)
            .join(Resource, Resource.id == InteractionEvent.resource_id)
            .where(
                InteractionEvent.hcp_id == hcp_id,
                InteractionEvent.event_type.in_([EventType.RESOURCE_VIEW, EventType.SOURCE_OPEN]),
            )
            .distinct()
        )
        if entity:
            stmt = stmt.where(Resource.product.ilike(entity))
        return {r for r in await self.session.scalars(stmt) if r is not None}

    async def top_entities(
        self, hcp_id: UUID, *, since: datetime | None = None, limit: int = 10
    ) -> list[TopicAffinity]:
        """Most frequently queried entities/topics (event counts by topic)."""
        label = func.coalesce(InteractionEvent.topic, InteractionEvent.entity).label("label")
        stmt = (
            select(label, func.count().label("n"))
            .where(InteractionEvent.hcp_id == hcp_id, label.is_not(None))
            .group_by(label)
            .order_by(func.count().desc())
            .limit(limit)
        )
        if since is not None:
            stmt = stmt.where(InteractionEvent.timestamp > since)
        rows = (await self.session.execute(stmt)).all()
        total = sum(n for _, n in rows) or 1
        return [TopicAffinity(entity=lbl, score=round(n / total, 3), interaction_count=n) for lbl, n in rows]

    async def engagement_over_time(
        self, hcp_id: UUID, *, bucket: str = "1 day", since: datetime | None = None
    ) -> list[EngagementBucket]:
        if bucket not in _BUCKETS:
            raise ValueError(f"bucket must be one of {list(_BUCKETS)}")
        if self.use_timescale:
            bucket_expr = func.time_bucket(literal_column(f"INTERVAL '{bucket}'"), InteractionEvent.timestamp)
        else:
            bucket_expr = func.date_trunc(_BUCKETS[bucket], InteractionEvent.timestamp)
        b = bucket_expr.label("bucket")
        topic = func.coalesce(InteractionEvent.topic, InteractionEvent.entity, "general").label("topic")
        stmt = (
            select(b, topic, func.count().label("n"))
            .where(InteractionEvent.hcp_id == hcp_id)
            .group_by(b, topic)
            .order_by(b)
        )
        if since is not None:
            stmt = stmt.where(InteractionEvent.timestamp > since)
        # TODO(database): read from the `hcp_topic_engagement_daily` continuous aggregate when present.
        rows = (await self.session.execute(stmt)).all()
        return [EngagementBucket(bucket=bk, topic=t, event_count=n) for bk, t, n in rows]

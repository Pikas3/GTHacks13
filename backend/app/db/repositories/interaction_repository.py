"""Engagement events on the `interaction_event` Timescale hypertable.

Example time-series queries live here (recent events, counts by topic, engagement over time,
top entities, activity since a timestamp, timeline). `time_bucket` is used when TimescaleDB is
installed; otherwise we fall back to `date_trunc` so plain PostgreSQL still works. Daily engagement is
read from the `hcp_topic_engagement_daily` continuous aggregate when present.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import BigInteger, DateTime, String, column, func, literal_column, select, table
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import InteractionEvent, Resource
from app.db.session import TOPIC_CAGG
from app.schemas.enums import EventType
from app.schemas.intelligence import TRENDING_WINDOWS, EngagementBucket, TopicAffinity, TrendingTopic
from app.schemas.interaction import InteractionEventCreate, InteractionEventRead

_RESOURCE_LABEL = (Resource.title + " v" + Resource.version).label("resource_label")

_TOPIC_LABEL = func.coalesce(InteractionEvent.topic, InteractionEvent.entity, "general")

# Continuous aggregate created by migrations 0002/0003 (daily buckets, excludes SESSION_STARTED).
_TOPIC_CAGG = table(
    TOPIC_CAGG,
    column("bucket", DateTime(timezone=True)),
    column("hcp_id"),
    column("topic", String),
    column("event_count", BigInteger),
)

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
    def __init__(self, session: AsyncSession, *, use_timescale: bool = False, use_topic_cagg: bool = False) -> None:
        self.session = session
        self.use_timescale = use_timescale
        self.use_topic_cagg = use_topic_cagg

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
        """Event counts per (time bucket, topic) for one HCP.

        Daily/weekly reads come from the real-time `hcp_topic_engagement_daily` continuous aggregate when
        it exists; hourly buckets (finer than the aggregate) and plain PostgreSQL use the raw hypertable.
        """
        if bucket not in _BUCKETS:
            raise ValueError(f"bucket must be one of {list(_BUCKETS)}")
        if self.use_topic_cagg and bucket != "1 hour":
            return await self._engagement_from_cagg(hcp_id, bucket=bucket, since=since)
        if self.use_timescale:
            bucket_expr = func.time_bucket(literal_column(f"INTERVAL '{bucket}'"), InteractionEvent.timestamp)
        else:
            bucket_expr = func.date_trunc(_BUCKETS[bucket], InteractionEvent.timestamp)
        b = bucket_expr.label("bucket")
        topic = _TOPIC_LABEL.label("topic")
        stmt = (
            select(b, topic, func.count().label("n"))
            .where(InteractionEvent.hcp_id == hcp_id, InteractionEvent.event_type != EventType.SESSION_STARTED)
            .group_by(b, topic)
            .order_by(b, topic)
        )
        if since is not None:
            stmt = stmt.where(InteractionEvent.timestamp > since)
        rows = (await self.session.execute(stmt)).all()
        return [EngagementBucket(bucket=bk, topic=t, event_count=n) for bk, t, n in rows]

    async def _engagement_from_cagg(
        self, hcp_id: UUID, *, bucket: str, since: datetime | None
    ) -> list[EngagementBucket]:
        c = _TOPIC_CAGG.c
        b = (
            c.bucket if bucket == "1 day" else func.time_bucket(literal_column(f"INTERVAL '{bucket}'"), c.bucket)
        ).label("bucket")
        stmt = (
            select(b, c.topic, func.sum(c.event_count).label("n"))
            .where(c.hcp_id == hcp_id)
            .group_by(b, c.topic)
            .order_by(b, c.topic)
        )
        if since is not None:
            stmt = stmt.where(c.bucket >= func.time_bucket(literal_column("INTERVAL '1 day'"), since))
        rows = (await self.session.execute(stmt)).all()
        return [EngagementBucket(bucket=bk, topic=t, event_count=int(n)) for bk, t, n in rows]

    async def trending_topics(self, *, window: str = "7 days", limit: int = 10) -> list[TrendingTopic]:
        """Most-engaged topics across ALL HCPs in a trailing time window.

        The time predicate lets Timescale exclude hypertable chunks outside the window.
        """
        if window not in TRENDING_WINDOWS:
            raise ValueError(f"window must be one of {list(TRENDING_WINDOWS)}")
        label = _TOPIC_LABEL.label("topic")
        stmt = (
            select(
                label,
                func.count().label("n"),
                func.count(func.distinct(InteractionEvent.hcp_id)).label("hcps"),
                func.max(InteractionEvent.timestamp).label("last_seen"),
            )
            .where(
                InteractionEvent.timestamp > func.now() - literal_column(f"INTERVAL '{window}'"),
                InteractionEvent.event_type != EventType.SESSION_STARTED,
                func.coalesce(InteractionEvent.topic, InteractionEvent.entity).is_not(None),
            )
            .group_by(label)
            .order_by(func.count().desc(), label)
            .limit(limit)
        )
        rows = (await self.session.execute(stmt)).all()
        return [TrendingTopic(topic=t, event_count=n, hcp_count=h, last_seen=ls) for t, n, h, ls in rows]

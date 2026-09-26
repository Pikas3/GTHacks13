import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class InteractionEvent(Base):
    """Time-series engagement event. Converted to a Timescale hypertable on `timestamp`
    by migration 0001 when the timescaledb extension is available.

    Timescale requires the partitioning column in every unique index, hence the composite PK.
    """

    __tablename__ = "interaction_event"
    __table_args__ = (
        Index("ix_interaction_event_hcp_ts", "hcp_id", "timestamp"),
        Index("ix_interaction_event_hcp_entity_ts", "hcp_id", "entity", "timestamp"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    timestamp: Mapped[datetime] = mapped_column(primary_key=True, server_default=func.now())
    hcp_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("hcp.id", ondelete="CASCADE"))
    session_id: Mapped[uuid.UUID | None]
    event_type: Mapped[str] = mapped_column(String(40))
    query_text: Mapped[str | None] = mapped_column(Text)
    response_text: Mapped[str | None] = mapped_column(Text)
    intent: Mapped[str | None] = mapped_column(String(40))
    entity: Mapped[str | None] = mapped_column(String(200))
    topic: Mapped[str | None] = mapped_column(String(200))
    # No FK: hypertables referencing regular tables is fine, but keeping events append-only and
    # decoupled from resource lifecycle is simpler for a demo.
    resource_id: Mapped[uuid.UUID | None]
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", default=dict, server_default="{}")

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from app.schemas.common import Schema
from app.schemas.enums import EventType, IntentType


class InteractionEventCreate(Schema):
    hcp_id: UUID
    session_id: UUID | None = None
    event_type: EventType
    timestamp: datetime | None = None  # defaults to now()
    query_text: str | None = None
    response_text: str | None = None
    intent: IntentType | None = None
    entity: str | None = None
    topic: str | None = None
    resource_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class InteractionEventRead(InteractionEventCreate):
    id: UUID
    timestamp: datetime
    resource_title: str | None = None


class TimelineEntry(Schema):
    """A human-readable line in the HCP's interaction timeline."""

    id: UUID
    timestamp: datetime
    event_type: EventType
    label: str
    entity: str | None = None
    topic: str | None = None
    resource_id: UUID | None = None

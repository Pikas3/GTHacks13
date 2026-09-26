from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import Schema
from app.schemas.enums import ConversationRole, IntentType


class ConversationContext(BaseModel):
    """Structured, persisted conversational state (conversation_session.context + active_* columns)."""

    active_entity: str | None = None
    active_topic: str | None = None
    active_resource_id: UUID | None = None
    last_intent: IntentType | None = None
    last_evidence_resource_ids: list[UUID] = Field(default_factory=list)
    last_resolved_query: str | None = None
    turn_count: int = 0


class ConversationTurnRead(Schema):
    id: UUID
    role: ConversationRole
    content: str
    created_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionCreate(BaseModel):
    hcp_id: UUID


class SessionRead(Schema):
    id: UUID
    hcp_id: UUID
    started_at: datetime
    last_activity_at: datetime
    context: ConversationContext = Field(default_factory=ConversationContext)


class SessionDetail(SessionRead):
    turns: list[ConversationTurnRead] = []

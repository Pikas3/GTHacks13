"""Lepius query contract — the primary frontend <-> backend API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.conversation import ConversationContext
from app.schemas.diff import SemanticDiff
from app.schemas.enums import EventType, InputMode, IntentType, ResourceType
from app.schemas.hcp import HCPInterestRead, HCPPreferenceRead, HCPRead
from app.schemas.intent import ExtractedEntity
from app.schemas.interaction import InteractionEventRead, TimelineEntry
from app.schemas.signals import EngagementSignal


class HCPContext(BaseModel):
    """Everything personalization-relevant we know about the HCP for this query."""

    hcp: HCPRead
    preferences: list[HCPPreferenceRead] = Field(default_factory=list)
    interests: list[HCPInterestRead] = Field(default_factory=list)
    recent_interactions: list[InteractionEventRead] = Field(default_factory=list)
    viewed_resource_ids: set[UUID] = Field(default_factory=set)
    # Last time the HCP *reviewed* material about the active entity (view/open/save),
    # which anchors "what's changed since I last looked at it?".
    last_entity_review: InteractionEventRead | None = None

    def interest_score(self, entity: str | None) -> float:
        if not entity:
            return 0.0
        needle = entity.lower()
        return max((i.score for i in self.interests if i.entity.lower() == needle), default=0.0)


class EvidenceReference(BaseModel):
    id: str = Field(description="Stable citation label used in answer text, e.g. 'E1'.")
    resource_id: UUID
    chunk_id: UUID
    title: str
    product: str
    resource_type: ResourceType
    version: str
    section: str | None = None
    page: int | None = None
    published_at: datetime
    excerpt: str
    source_url: str | None = None
    is_new: bool = False
    score: float | None = None


class LepiusRequest(BaseModel):
    hcp_id: UUID
    session_id: UUID | None = Field(default=None, description="Omit to start a new session.")
    query: str = Field(min_length=1, max_length=2000)
    input_mode: InputMode = InputMode.TEXT


class LepiusAnswer(BaseModel):
    text: str
    speech_text: str
    insufficient_evidence: bool = False


class LepiusResponse(BaseModel):
    session_id: UUID
    query: str
    resolved_query: str
    intent: IntentType
    entities: list[ExtractedEntity] = Field(default_factory=list)
    response: LepiusAnswer
    context: ConversationContext
    evidence: list[EvidenceReference] = Field(default_factory=list)
    changes: list[SemanticDiff] = Field(default_factory=list)
    history: list[TimelineEntry] = Field(default_factory=list)
    suggested_followups: list[str] = Field(default_factory=list)
    signals_generated: list[EngagementSignal] = Field(default_factory=list)
    timings_ms: dict[str, float] = Field(default_factory=dict)


class EngagementEventRequest(BaseModel):
    """Client-reported engagement (e.g. HCP opened a source)."""

    hcp_id: UUID
    session_id: UUID | None = None
    event_type: EventType
    resource_id: UUID | None = None
    entity: str | None = None
    topic: str | None = None

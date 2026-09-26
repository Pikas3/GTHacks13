from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.enums import EventType
from app.schemas.hcp import HCPInterestRead
from app.schemas.interaction import TimelineEntry
from app.schemas.resource import ResourceRead
from app.schemas.signals import EngagementSignal


class TopicAffinity(BaseModel):
    entity: str
    score: float
    interaction_count: int


class Recommendation(BaseModel):
    resource: ResourceRead
    reason: str
    score: float


class EngagementBucket(BaseModel):
    bucket: datetime
    topic: str
    event_count: int


class IntelligenceSignals(BaseModel):
    hcp_id: UUID
    signals: list[EngagementSignal] = Field(default_factory=list)
    affinities: list[HCPInterestRead] = Field(default_factory=list)


class IntelligenceRecommendations(BaseModel):
    hcp_id: UUID
    recommendations: list[Recommendation] = Field(default_factory=list)


class EngagementSeries(BaseModel):
    hcp_id: UUID
    bucket: str
    points: list[EngagementBucket] = Field(default_factory=list)
    top_entities: list[TopicAffinity] = Field(default_factory=list)


TrendingWindow = Literal["1 day", "7 days", "30 days", "90 days"]
TRENDING_WINDOWS: tuple[str, ...] = ("1 day", "7 days", "30 days", "90 days")


class TrendingTopic(BaseModel):
    topic: str
    event_count: int
    hcp_count: int
    last_seen: datetime


class TrendingTopics(BaseModel):
    """Cross-HCP topic activity in a trailing window (Impiricus-level view, synthetic HCPs only)."""

    window: str
    topics: list[TrendingTopic] = Field(default_factory=list)


class ActivitySince(BaseModel):
    """Everything one HCP did after a point in time."""

    hcp_id: UUID
    since: datetime
    event_count: int
    by_type: dict[EventType, int] = Field(default_factory=dict)
    events: list[TimelineEntry] = Field(default_factory=list)

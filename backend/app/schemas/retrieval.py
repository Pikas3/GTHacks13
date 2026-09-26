from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.schemas.resource import ResourceChunkRead, ResourceRead


class RetrievalStrategy(StrEnum):
    SEMANTIC = "SEMANTIC"  # standard grounded QA
    WHATS_NEW = "WHATS_NEW"  # restrict to resources newer than the HCP's last look
    HISTORY_ONLY = "HISTORY_ONLY"  # answer from structured memory, no retrieval
    SOURCE_LOOKUP = "SOURCE_LOOKUP"  # re-surface evidence from the previous turn


class RetrievalPlan(BaseModel):
    strategy: RetrievalStrategy = RetrievalStrategy.SEMANTIC
    query: str
    product: str | None = None
    topic: str | None = None
    published_after: datetime | None = None
    include_superseded: bool = False  # True only for version comparisons
    limit: int = 8


class ScoreBreakdown(BaseModel):
    semantic: float = 0.0
    entity_match: float = 0.0
    recency: float = 0.0
    interest: float = 0.0
    previously_viewed: float = 0.0
    new_since_last_view: float = 0.0


class RetrievalResult(BaseModel):
    chunk: ResourceChunkRead
    resource: ResourceRead
    score: float
    breakdown: ScoreBreakdown = Field(default_factory=ScoreBreakdown)
    previously_viewed: bool = False
    is_new_since_last_view: bool = False

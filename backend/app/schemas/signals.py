from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.enums import EntityType, EventType, IntentType


class EngagementSignal(BaseModel):
    """A structured engagement signal derived from one interaction.

    NOTE: hackathon heuristic only — not a representation of real Impiricus scoring.
    """

    hcp_id: UUID
    entity: str
    entity_type: EntityType
    topic: str | None = None
    intent: IntentType | None = None
    event_type: EventType
    weight: float
    new_score: float | None = None
    timestamp: datetime | None = None

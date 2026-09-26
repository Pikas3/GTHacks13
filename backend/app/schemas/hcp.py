from datetime import datetime
from uuid import UUID

from app.schemas.common import Schema
from app.schemas.enums import EntityType


class HCPRead(Schema):
    id: UUID
    external_id: str
    name: str
    specialty: str
    organization: str | None = None
    region: str | None = None


class HCPPreferenceRead(Schema):
    key: str
    value: str
    weight: float


class HCPInterestRead(Schema):
    entity: str
    entity_type: EntityType
    score: float
    interaction_count: int
    last_interaction_at: datetime | None = None


class HCPDetail(HCPRead):
    preferences: list[HCPPreferenceRead] = []
    interests: list[HCPInterestRead] = []

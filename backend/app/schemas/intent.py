"""Structured intent extraction contract (Gemini structured output + mock)."""

from pydantic import BaseModel, Field

from app.schemas.enums import EntityType, IntentType, TemporalReference


class ExtractedEntity(BaseModel):
    name: str = Field(description="Canonical entity name, e.g. 'Novara' or 'renal impairment'.")
    type: EntityType


class IntentResult(BaseModel):
    intent: IntentType = IntentType.UNKNOWN
    entities: list[ExtractedEntity] = Field(default_factory=list)
    topic: str | None = Field(default=None, description="Clinical/resource topic, e.g. 'dosing'.")
    temporal_reference: TemporalReference = TemporalReference.NONE
    requires_history: bool = False
    requires_retrieval: bool = True
    rewritten_query: str | None = Field(
        default=None, description="Standalone query with pronouns resolved, if applicable."
    )

    @property
    def product(self) -> str | None:
        return next((e.name for e in self.entities if e.type == EntityType.PRODUCT), None)

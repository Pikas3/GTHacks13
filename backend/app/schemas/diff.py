from pydantic import BaseModel, Field

from app.schemas.enums import ChangeType, Importance


class SectionChange(BaseModel):
    topic: str
    change_type: ChangeType
    importance: Importance
    summary: str
    old_evidence: str | None = None
    new_evidence: str | None = None


class SemanticDiff(BaseModel):
    resource: str
    old_version: str
    new_version: str
    changes: list[SectionChange] = Field(default_factory=list)

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import Field

from app.schemas.common import Schema
from app.schemas.enums import ResourceType


class ResourceRead(Schema):
    id: UUID
    title: str
    product: str
    resource_type: ResourceType
    version: str
    published_at: datetime
    supersedes_resource_id: UUID | None = None
    source_url: str | None = None
    is_approved: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResourceChunkRead(Schema):
    id: UUID
    resource_id: UUID
    chunk_index: int
    text: str
    section: str | None = None
    page: int | None = None


class ResourceDetail(ResourceRead):
    chunks: list[ResourceChunkRead] = []


class ChunkHit(Schema):
    """A chunk returned by vector/lexical search with scores and parent resource."""

    chunk: ResourceChunkRead
    resource: ResourceRead
    similarity: float = 0.0
    lexical_score: float = 0.0

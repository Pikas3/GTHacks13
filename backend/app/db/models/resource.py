import uuid
from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import get_settings
from app.db.base import Base

# Vector dimension is configured centrally (GEMINI_EMBEDDING_DIMENSION). Changing it requires a
# new migration that alters resource_chunk.embedding and re-embedding all chunks.
EMBEDDING_DIMENSION = get_settings().gemini_embedding_dimension


class Resource(Base):
    """An approved (synthetic) resource: PI, clinical study, access guide, education."""

    __tablename__ = "resource"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(300))
    product: Mapped[str] = mapped_column(String(120), index=True)
    resource_type: Mapped[str] = mapped_column(String(40))
    version: Mapped[str] = mapped_column(String(40))
    published_at: Mapped[datetime] = mapped_column(index=True)
    supersedes_resource_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("resource.id", ondelete="SET NULL"))
    source_url: Mapped[str | None] = mapped_column(String(500))
    is_approved: Mapped[bool] = mapped_column(default=True)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    chunks: Mapped[list["ResourceChunk"]] = relationship(
        back_populates="resource", cascade="all, delete-orphan", order_by="ResourceChunk.chunk_index"
    )


class ResourceChunk(Base):
    __tablename__ = "resource_chunk"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    resource_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resource.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int]
    text: Mapped[str] = mapped_column(Text)
    section: Mapped[str | None] = mapped_column(String(200))
    page: Mapped[int | None]
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", default=dict, server_default="{}")
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSION))

    resource: Mapped[Resource] = relationship(back_populates="chunks")

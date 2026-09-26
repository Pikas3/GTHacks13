import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ConversationSession(Base):
    __tablename__ = "conversation_session"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    hcp_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("hcp.id", ondelete="CASCADE"), index=True)
    started_at: Mapped[datetime] = mapped_column(server_default=func.now())
    last_activity_at: Mapped[datetime] = mapped_column(server_default=func.now())
    active_entity: Mapped[str | None] = mapped_column(String(200))
    active_topic: Mapped[str | None] = mapped_column(String(200))
    active_resource_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("resource.id", ondelete="SET NULL"))
    context: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default="{}")

    turns: Mapped[list["ConversationTurn"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="ConversationTurn.created_at"
    )


class ConversationTurn(Base):
    __tablename__ = "conversation_turn"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversation_session.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", default=dict, server_default="{}")

    session: Mapped[ConversationSession] = relationship(back_populates="turns")

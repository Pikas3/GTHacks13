from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import ConversationSession, ConversationTurn
from app.schemas.conversation import (
    ConversationContext,
    ConversationTurnRead,
    SessionDetail,
    SessionRead,
)
from app.schemas.enums import ConversationRole


def _session_read(row: ConversationSession) -> SessionRead:
    ctx = ConversationContext.model_validate(row.context or {})
    return SessionRead(
        id=row.id,
        hcp_id=row.hcp_id,
        started_at=row.started_at,
        last_activity_at=row.last_activity_at,
        context=ctx,
    )


def _turn_read(row: ConversationTurn) -> ConversationTurnRead:
    return ConversationTurnRead(
        id=row.id,
        role=ConversationRole(row.role),
        content=row.content,
        created_at=row.created_at,
        metadata=row.metadata_ or {},
    )


class SqlConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_session(self, hcp_id: UUID) -> SessionRead:
        now = datetime.now(UTC)
        row = ConversationSession(
            hcp_id=hcp_id,
            started_at=now,
            last_activity_at=now,
            context=ConversationContext().model_dump(mode="json"),
        )
        self.session.add(row)
        await self.session.flush()
        return _session_read(row)

    async def get_session(self, session_id: UUID) -> SessionRead | None:
        row = await self.session.get(ConversationSession, session_id)
        return _session_read(row) if row else None

    async def get_detail(self, session_id: UUID) -> SessionDetail | None:
        row = await self.session.scalar(
            select(ConversationSession)
            .where(ConversationSession.id == session_id)
            .options(selectinload(ConversationSession.turns))
        )
        if row is None:
            return None
        return SessionDetail(**_session_read(row).model_dump(), turns=[_turn_read(t) for t in row.turns])

    async def update_context(self, session_id: UUID, context: ConversationContext) -> None:
        row = await self.session.get(ConversationSession, session_id)
        if row is None:
            return
        row.context = context.model_dump(mode="json")
        row.active_entity = context.active_entity
        row.active_topic = context.active_topic
        row.active_resource_id = context.active_resource_id
        row.last_activity_at = datetime.now(UTC)
        await self.session.flush()

    async def add_turn(
        self, session_id: UUID, role: ConversationRole, content: str, metadata: dict[str, Any] | None = None
    ) -> ConversationTurnRead:
        row = ConversationTurn(
            session_id=session_id,
            role=role.value,
            content=content,
            created_at=datetime.now(UTC),
            metadata_=metadata or {},
        )
        self.session.add(row)
        await self.session.flush()
        return _turn_read(row)

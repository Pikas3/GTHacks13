from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.dependencies import Repositories, get_repositories
from app.errors import AppError, ErrorCode
from app.schemas.conversation import SessionCreate, SessionDetail, SessionRead
from app.schemas.enums import EventType
from app.schemas.interaction import InteractionEventCreate

router = APIRouter(prefix="/sessions", tags=["sessions"])


@router.post("", response_model=SessionRead, status_code=status.HTTP_201_CREATED)
async def create_session(body: SessionCreate, repos: Repositories = Depends(get_repositories)) -> SessionRead:
    if await repos.hcps.get_hcp(body.hcp_id) is None:
        raise AppError(ErrorCode.INVALID_HCP, f"Unknown HCP {body.hcp_id}")
    session = await repos.conversations.create_session(body.hcp_id)
    await repos.interactions.record(
        InteractionEventCreate(hcp_id=body.hcp_id, session_id=session.id, event_type=EventType.SESSION_STARTED)
    )
    return session


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session(session_id: UUID, repos: Repositories = Depends(get_repositories)) -> SessionDetail:
    detail = await repos.conversations.get_detail(session_id)
    if detail is None:
        raise AppError(ErrorCode.INVALID_SESSION, f"Unknown session {session_id}")
    return detail

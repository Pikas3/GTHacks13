from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.ambient.memory import MemoryService
from app.dependencies import Repositories, get_ion, get_memory, get_repositories
from app.errors import AppError, ErrorCode
from app.impiricus.mock_ion import MockIONService
from app.schemas.hcp import HCPDetail, HCPInterestRead, HCPRead
from app.schemas.interaction import TimelineEntry

router = APIRouter(prefix="/hcps", tags=["hcps"])


@router.get("", response_model=list[HCPRead])
async def list_hcps(repos: Repositories = Depends(get_repositories)) -> list[HCPRead]:
    return await repos.hcps.list_hcps()


@router.get("/{hcp_id}", response_model=HCPDetail)
async def get_hcp(
    hcp_id: UUID, repos: Repositories = Depends(get_repositories), ion: MockIONService = Depends(get_ion)
) -> HCPDetail:
    detail = await repos.hcps.get_detail(hcp_id)
    if detail is None:
        raise AppError(ErrorCode.INVALID_HCP, f"Unknown HCP {hcp_id}")
    return detail.model_copy(update={"interests": await ion.get_topic_affinities(hcp_id)})


@router.get("/{hcp_id}/timeline", response_model=list[TimelineEntry])
async def get_timeline(
    hcp_id: UUID,
    limit: int = Query(30, ge=1, le=200),
    repos: Repositories = Depends(get_repositories),
    memory: MemoryService = Depends(get_memory),
) -> list[TimelineEntry]:
    if await repos.hcps.get_hcp(hcp_id) is None:
        raise AppError(ErrorCode.INVALID_HCP, f"Unknown HCP {hcp_id}")
    return await memory.get_timeline(hcp_id, limit=limit)


@router.get("/{hcp_id}/interests", response_model=list[HCPInterestRead])
async def get_interests(
    hcp_id: UUID, repos: Repositories = Depends(get_repositories), ion: MockIONService = Depends(get_ion)
) -> list[HCPInterestRead]:
    """Current interest scores (time-decayed; see INTEREST_HALF_LIFE_DAYS)."""
    if await repos.hcps.get_hcp(hcp_id) is None:
        raise AppError(ErrorCode.INVALID_HCP, f"Unknown HCP {hcp_id}")
    return await ion.get_topic_affinities(hcp_id)

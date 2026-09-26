"""Impiricus-facing intelligence views (the company side of the loop)."""

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.dependencies import Repositories, get_ion, get_repositories
from app.errors import AppError, ErrorCode
from app.impiricus.mock_ion import MockIONService
from app.schemas.intelligence import EngagementSeries, IntelligenceRecommendations, IntelligenceSignals

router = APIRouter(prefix="/intelligence", tags=["intelligence"])


async def _require_hcp(hcp_id: UUID, repos: Repositories) -> None:
    if await repos.hcps.get_hcp(hcp_id) is None:
        raise AppError(ErrorCode.INVALID_HCP, f"Unknown HCP {hcp_id}")


@router.get("/{hcp_id}/signals", response_model=IntelligenceSignals)
async def get_signals(
    hcp_id: UUID,
    limit: int = Query(20, ge=1, le=100),
    repos: Repositories = Depends(get_repositories),
    ion: MockIONService = Depends(get_ion),
) -> IntelligenceSignals:
    await _require_hcp(hcp_id, repos)
    return IntelligenceSignals(
        hcp_id=hcp_id,
        signals=await ion.get_recent_signals(hcp_id, limit=limit),
        affinities=await ion.get_topic_affinities(hcp_id),
    )


@router.get("/{hcp_id}/recommendations", response_model=IntelligenceRecommendations)
async def get_recommendations(
    hcp_id: UUID,
    repos: Repositories = Depends(get_repositories),
    ion: MockIONService = Depends(get_ion),
) -> IntelligenceRecommendations:
    await _require_hcp(hcp_id, repos)
    return IntelligenceRecommendations(hcp_id=hcp_id, recommendations=await ion.get_recommended_resource(hcp_id))


@router.get("/{hcp_id}/engagement", response_model=EngagementSeries)
async def get_engagement(
    hcp_id: UUID,
    bucket: Literal["1 hour", "1 day", "1 week"] = "1 day",
    repos: Repositories = Depends(get_repositories),
) -> EngagementSeries:
    """Engagement over time (Timescale time_bucket when available) + most-queried entities."""
    await _require_hcp(hcp_id, repos)
    return EngagementSeries(
        hcp_id=hcp_id,
        bucket=bucket,
        points=await repos.interactions.engagement_over_time(hcp_id, bucket=bucket),
        top_entities=await repos.interactions.top_entities(hcp_id),
    )

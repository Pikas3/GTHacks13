from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.lepius.orchestrator import LepiusOrchestrator
from app.lepius.personalization import EngagementService
from app.dependencies import get_engagement_service, get_orchestrator
from app.schemas.lepius import LepiusRequest, LepiusResponse, EngagementEventRequest
from app.schemas.interaction import InteractionEventRead
from app.schemas.signals import EngagementSignal

router = APIRouter(prefix="/lepius", tags=["lepius"])


@router.post("/query", response_model=LepiusResponse)
async def lepius_query(
    body: LepiusRequest, orchestrator: LepiusOrchestrator = Depends(get_orchestrator)
) -> LepiusResponse:
    """Main Lepius loop. All logic lives in LepiusOrchestrator."""
    return await orchestrator.process_query(body.hcp_id, body.session_id, body.query, body.input_mode)


class EngagementEventResponse(BaseModel):
    event: InteractionEventRead
    signals_generated: list[EngagementSignal]


@router.post("/events", response_model=EngagementEventResponse)
async def record_event(
    body: EngagementEventRequest, service: EngagementService = Depends(get_engagement_service)
) -> EngagementEventResponse:
    """Client-reported engagement, e.g. SOURCE_OPEN when an evidence card is opened."""
    event, signals = await service.record(body)
    return EngagementEventResponse(event=event, signals_generated=signals)

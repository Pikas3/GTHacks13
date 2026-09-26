import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text

from app.dependencies import ServiceContainer, get_container

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    status: str
    app_env: str
    database: str
    timescaledb: bool
    pgvector: bool
    topic_cagg: bool
    ai_mode: str
    voice_mode: str
    gemini_model: str
    embedding_model: str
    embedding_dimension: int


@router.get("/health", response_model=HealthResponse)
async def health(container: ServiceContainer = Depends(get_container)) -> HealthResponse:
    """Liveness + dependency status. Never fails: reports degraded state instead."""
    s = container.settings
    db_status = "ok"
    try:
        async with container.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        await container.ensure_capabilities()
    except Exception as exc:  # report, don't raise
        logger.warning("health: database unavailable", extra={"error": type(exc).__name__})
        db_status = "unavailable"
    return HealthResponse(
        status="ok" if db_status == "ok" else "degraded",
        app_env=s.app_env,
        database=db_status,
        timescaledb=container.capabilities.get("timescaledb", False),
        pgvector=container.capabilities.get("pgvector", False),
        topic_cagg=container.capabilities.get("topic_cagg", False),
        ai_mode=container.ai.mode,
        voice_mode=f"stt:{container.stt.name},tts:{container.tts.name}",
        gemini_model=s.gemini_model,
        embedding_model=s.gemini_embedding_model,
        embedding_dimension=s.gemini_embedding_dimension,
    )

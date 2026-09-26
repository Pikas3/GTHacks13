"""Async engine + session factory. Created once in the app lifespan (no module-level globals)."""

import asyncio
from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings


def create_engine(settings: Settings, *, for_migrations: bool = False) -> AsyncEngine:
    """Engine tuned for both local compose and Tiger Data cloud (SSL, small pool, recycling,
    server-side statement_timeout). `for_migrations` disables the statement timeout."""
    return create_async_engine(
        settings.async_database_url,
        echo=settings.db_echo,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_recycle=settings.db_pool_recycle_s,
        connect_args=settings.database_connect_args(for_migrations=for_migrations),
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


async def session_scope(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncSession]:
    """Unit-of-work: commit on success, rollback on error."""
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


TOPIC_CAGG = "hcp_topic_engagement_daily"
REFRESH_ATTEMPTS = 5
# Upper bound for manual refreshes of the daily cagg (see refresh_topic_cagg).
CURRENT_BUCKET_START = "time_bucket(INTERVAL '1 day', now())"


async def detect_capabilities(engine: AsyncEngine) -> dict[str, bool]:
    """Which Tiger Data / Postgres features are available. Used for graceful degradation."""
    async with engine.connect() as conn:
        rows = await conn.execute(text("SELECT extname FROM pg_extension WHERE extname IN ('timescaledb', 'vector')"))
        installed = {r[0] for r in rows}
        has_cagg = False
        if "timescaledb" in installed:
            has_cagg = bool(
                await conn.scalar(
                    text("SELECT 1 FROM timescaledb_information.continuous_aggregates WHERE view_name = :v"),
                    {"v": TOPIC_CAGG},
                )
            )
    return {"timescaledb": "timescaledb" in installed, "pgvector": "vector" in installed, "topic_cagg": has_cagg}


async def refresh_topic_cagg(engine: AsyncEngine) -> bool:
    """Fully refresh the daily topic-engagement continuous aggregate (e.g. after seeding/backfill).

    `refresh_continuous_aggregate` cannot run inside a transaction, hence AUTOCOMMIT.
    Returns False when the aggregate doesn't exist (plain PostgreSQL).

    The window ends at the start of the *current* bucket: materializing today's incomplete bucket
    would move the watermark to tomorrow, and later events today would then be invisible to
    real-time aggregation until the next refresh.
    """
    if not (await detect_capabilities(engine))["topic_cagg"]:
        return False
    for attempt in range(1, REFRESH_ATTEMPTS + 1):
        try:
            async with engine.connect() as conn:
                conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
                await conn.execute(
                    text(f"CALL refresh_continuous_aggregate('{TOPIC_CAGG}', NULL, {CURRENT_BUCKET_START})")
                )
            return True
        except DBAPIError as exc:
            # The background refresh policy may be running (e.g. right after `alembic upgrade`).
            if "concurrent refresh" not in str(exc.orig) or attempt == REFRESH_ATTEMPTS:
                raise
            await asyncio.sleep(0.5 * attempt)
    return True

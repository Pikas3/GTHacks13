"""Async engine + session factory. Created once in the app lifespan (no module-level globals)."""

from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import Settings


def create_engine(settings: Settings) -> AsyncEngine:
    return create_async_engine(
        settings.async_database_url,
        echo=settings.db_echo,
        pool_pre_ping=True,
        connect_args=settings.database_connect_args,
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


async def detect_capabilities(engine: AsyncEngine) -> dict[str, bool]:
    """Which Tiger Data / Postgres extensions are installed. Used for graceful degradation."""
    async with engine.connect() as conn:
        rows = await conn.execute(text("SELECT extname FROM pg_extension WHERE extname IN ('timescaledb', 'vector')"))
        installed = {r[0] for r in rows}
    return {"timescaledb": "timescaledb" in installed, "pgvector": "vector" in installed}

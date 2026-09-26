"""Async engine + session factory. Created once in the app lifespan (no module-level globals)."""

from collections.abc import AsyncIterator

from sqlalchemy import text
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


async def detect_extension_versions(engine: AsyncEngine) -> dict[str, str]:
    """Installed versions of the extensions we care about, e.g. {"timescaledb": "2.22.1", "vector": "0.8.0"}."""
    async with engine.connect() as conn:
        rows = await conn.execute(
            text("SELECT extname, extversion FROM pg_extension WHERE extname IN ('timescaledb', 'vector')")
        )
        return {name: version for name, version in rows}


async def detect_capabilities(engine: AsyncEngine) -> dict[str, bool]:
    """Which Tiger Data / Postgres extensions are installed. Used for graceful degradation."""
    installed = await detect_extension_versions(engine)
    return {"timescaledb": "timescaledb" in installed, "pgvector": "vector" in installed}

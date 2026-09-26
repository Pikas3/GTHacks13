"""Integration fixtures: a real Timescale/pgvector database, migrated with Alembic and seeded.

Skipped unless TEST_DATABASE_URL is set, e.g.
    TEST_DATABASE_URL=postgresql+asyncpg://ambient:ambient@localhost:5433/ambient_test make backend-itest

Safety: every test TRUNCATEs and reseeds, so the database name must contain "test". The database is
dropped and recreated once per run (needs CREATE DATABASE rights, which the local container has).
"""

import asyncio
import os
import subprocess
import sys
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import asyncpg
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.config import BACKEND_DIR, Settings
from app.db.session import create_engine, create_session_factory, detect_capabilities
from app.dependencies import build_ai_providers
from app.ingestion.seed import seed_database

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")


def _settings(url: str) -> Settings:
    return Settings(_env_file=None, database_url=url, use_mock_ai=True, use_mock_voice=True)


def _libpq_url(url: str, database: str | None = None) -> str:
    parts = urlsplit(url)
    path = f"/{database}" if database is not None else parts.path
    return urlunsplit(("postgresql", parts.netloc, path, parts.query, parts.fragment))


async def _recreate_database(url: str) -> None:
    name = urlsplit(url).path.lstrip("/")
    conn = await asyncpg.connect(_libpq_url(url, "postgres"))
    try:
        await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        await conn.execute(f'CREATE DATABASE "{name}"')
    finally:
        await conn.close()


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    if not TEST_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL not set")
    name = urlsplit(TEST_DATABASE_URL).path.lstrip("/")
    if "test" not in name:
        pytest.exit(f"Refusing to run destructive integration tests against database {name!r}", returncode=2)
    asyncio.run(_recreate_database(TEST_DATABASE_URL))
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env={**os.environ, "DATABASE_URL": TEST_DATABASE_URL},
        check=True,
        capture_output=True,
    )
    yield TEST_DATABASE_URL


@dataclass
class IntegrationDB:
    engine: AsyncEngine
    settings: Settings
    capabilities: dict[str, bool]

    def session(self) -> AsyncSession:
        return create_session_factory(self.engine)()


@pytest.fixture
async def db(database_url: str) -> AsyncIterator[IntegrationDB]:
    """Freshly seeded database per test (seeding with mock embeddings takes well under a second)."""
    settings = _settings(database_url)
    engine = create_engine(settings)
    await seed_database(engine, settings, reset=True)
    try:
        yield IntegrationDB(engine, settings, await detect_capabilities(engine))
    finally:
        await engine.dispose()


@pytest.fixture
def ai(db: IntegrationDB):
    return build_ai_providers(db.settings)

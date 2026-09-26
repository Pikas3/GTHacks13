"""Integration fixtures: a real Postgres/Timescale database, isolated in a throwaway schema.

Runs only when TEST_DATABASE_URL is set (`make backend-itest` defaults it to the local compose DB).
Each run creates schema `itest_<random>`, runs the real Alembic migrations into it (via
DB_SEARCH_PATH), and drops it afterwards. Schema isolation works on local compose *and* on a Tiger
Data service (which only has the one `tsdb` database), and never touches the demo data.
"""

import asyncio
import os
import subprocess
import sys
import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import BACKEND_DIR, Settings, get_settings
from app.ingestion.seed import seed_database, stable_id
from app.main import create_app

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
MORGAN_ID = stable_id("hcp", "SYN-HCP-001")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        if "tests/integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
            if not TEST_DATABASE_URL:
                item.add_marker(pytest.mark.skip(reason="TEST_DATABASE_URL not set"))


async def _admin_sql(settings: Settings, *statements: str) -> None:
    """Run statements without the itest search_path (extensions must live in `public`)."""
    engine = create_async_engine(
        settings.async_database_url,
        connect_args={k: v for k, v in settings.database_connect_args().items() if k != "server_settings"},
        isolation_level="AUTOCOMMIT",
    )
    try:
        async with engine.connect() as conn:
            for stmt in statements:
                await conn.execute(text(stmt))
    finally:
        await engine.dispose()


async def query(settings: Settings, sql: str, **params: object) -> list[tuple]:
    engine = create_async_engine(settings.async_database_url, connect_args=settings.database_connect_args())
    try:
        async with engine.connect() as conn:
            return [tuple(r) for r in await conn.execute(text(sql), params)]
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
def itest_settings() -> Iterator[Settings]:
    assert TEST_DATABASE_URL
    schema = f"itest_{uuid.uuid4().hex[:10]}"
    settings = Settings(
        _env_file=None,
        app_env="test",
        database_url=TEST_DATABASE_URL,
        db_search_path=schema,
        use_mock_ai=True,
        use_mock_voice=True,
        gemini_embedding_dimension=get_settings().gemini_embedding_dimension,
    )
    asyncio.run(
        _admin_sql(
            settings,
            "CREATE EXTENSION IF NOT EXISTS vector SCHEMA public",
            """DO $$ BEGIN CREATE EXTENSION IF NOT EXISTS timescaledb;
               EXCEPTION WHEN OTHERS THEN RAISE NOTICE 'no timescaledb'; END $$""",
            f"CREATE SCHEMA {schema}",
        )
    )
    env = {
        **os.environ,
        "DATABASE_URL": TEST_DATABASE_URL,
        "DB_SEARCH_PATH": schema,
        "USE_MOCK_AI": "true",
        "GEMINI_EMBEDDING_DIMENSION": str(settings.gemini_embedding_dimension),
    }
    try:
        subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_DIR,
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        migrated = asyncio.run(query(settings, "SELECT to_regclass(:t) IS NOT NULL", t=f"{schema}.interaction_event"))
        assert migrated == [(True,)], f"migrations did not run inside schema {schema}"
        yield settings
    except subprocess.CalledProcessError as exc:
        pytest.fail(f"alembic upgrade failed:\n{exc.stderr}")
    finally:
        # Drop Timescale objects explicitly first so their catalog entries/jobs go cleanly.
        asyncio.run(
            _admin_sql(
                settings,
                f"DROP MATERIALIZED VIEW IF EXISTS {schema}.hcp_topic_engagement_daily CASCADE",
                f"DROP TABLE IF EXISTS {schema}.interaction_event CASCADE",
                f"DROP SCHEMA IF EXISTS {schema} CASCADE",
            )
        )


@pytest.fixture
def seeded(itest_settings: Settings) -> Settings:
    """Fresh demo state for every test (`make seed` equivalent)."""
    asyncio.run(seed_database(itest_settings, reset=True))
    return itest_settings


@pytest.fixture
def client(seeded: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(seeded)) as c:
        yield c

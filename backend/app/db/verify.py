"""Check that DATABASE_URL points at a correctly migrated + seeded Tiger Data / Timescale database.

    python -m app.db.verify          # or: make db-verify

Prints extensions, the hypertable, the continuous aggregate, background jobs and row counts.
Exits non-zero if something the demo relies on is missing. Never prints the connection string.
"""

import asyncio
import sys
from urllib.parse import urlsplit

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from app.config import get_settings
from app.db.session import create_engine

TABLES = ["hcp", "hcp_interest", "resource", "resource_chunk", "interaction_event", "conversation_session"]


async def _rows(conn: AsyncConnection, sql: str) -> list[tuple]:
    return [tuple(r) for r in await conn.execute(text(sql))]


async def verify() -> list[str]:
    settings = get_settings()
    host = urlsplit(settings.async_database_url).hostname
    problems: list[str] = []
    engine = create_engine(settings)
    try:
        async with engine.connect() as conn:
            print(f"host: {host}  search_path: {settings.db_search_path or '(default)'}")
            print("server:", (await conn.execute(text("SHOW server_version"))).scalar())
            exts = dict(await _rows(conn, "SELECT extname, extversion FROM pg_extension ORDER BY 1"))
            print("extensions:", ", ".join(f"{k} {v}" for k, v in exts.items()))
            if "vector" not in exts:
                problems.append("pgvector extension missing")
            print("alembic:", (await conn.execute(text("SELECT version_num FROM alembic_version"))).scalar())

            if "timescaledb" in exts:
                hts = await _rows(
                    conn,
                    "SELECT hypertable_schema, hypertable_name, num_chunks FROM timescaledb_information.hypertables",
                )
                print("hypertables:", hts)
                if not any(h[1] == "interaction_event" for h in hts):
                    problems.append("interaction_event is not a hypertable")
                caggs = await _rows(
                    conn,
                    "SELECT view_schema, view_name, materialized_only "
                    "FROM timescaledb_information.continuous_aggregates",
                )
                print("continuous aggregates:", caggs)
                if not any(c[1] == "hcp_topic_engagement_daily" for c in caggs):
                    problems.append("hcp_topic_engagement_daily continuous aggregate missing")
                jobs = await _rows(
                    conn,
                    "SELECT job_id, proc_name, hypertable_name, schedule_interval "
                    "FROM timescaledb_information.jobs WHERE job_id >= 1000",
                )
                print("jobs:", jobs)
            else:
                print("timescaledb: NOT installed (plain PostgreSQL fallback: no hypertable / cagg)")

            for t in TABLES:
                n = (await conn.execute(text(f"SELECT count(*) FROM {t}"))).scalar()
                print(f"  {t:<22} {n}")
                if t in {"hcp", "resource", "resource_chunk"} and not n:
                    problems.append(f"{t} is empty (run `make seed`)")
    finally:
        await engine.dispose()
    return problems


def main() -> None:
    problems = asyncio.run(verify())
    if problems:
        print("\nPROBLEMS:\n  - " + "\n  - ".join(problems))
        sys.exit(1)
    print("\nOK")


if __name__ == "__main__":
    main()

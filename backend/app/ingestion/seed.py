"""Seed the database with SYNTHETIC HCPs, FICTIONAL product resources and demo history.

    python -m app.ingestion.seed            # upsert-free: fails if data exists
    python -m app.ingestion.seed --reset    # truncate all tables first (recommended)

IDs are deterministic (uuid5 of stable keys), so re-seeding keeps the same UUIDs.
"""

import argparse
import asyncio
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from app.config import Settings, get_settings
from app.db.models import HCP, HCPInterest, HCPPreference, InteractionEvent, Resource, ResourceChunk
from app.db.session import create_engine, create_session_factory, refresh_topic_cagg
from app.dependencies import build_ai_providers
from app.ingestion.chunker import chunk_sections
from app.ingestion.embedder import embed_chunks
from app.ingestion.parser import ParsedResource, parse_resource_file

logger = logging.getLogger("seed")
NAMESPACE = uuid.UUID("6f1c1d1e-0000-4000-8000-a0b1e27a1b00")

TABLES = [
    "interaction_event",
    "conversation_turn",
    "conversation_session",
    "resource_chunk",
    "resource",
    "hcp_interest",
    "hcp_preference",
    "hcp",
]


def stable_id(kind: str, key: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, f"{kind}:{key}")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


async def seed_hcps(session: AsyncSession, hcps: list[dict[str, Any]]) -> None:
    for h in hcps:
        hcp_id = stable_id("hcp", h["external_id"])
        session.add(
            HCP(
                id=hcp_id,
                external_id=h["external_id"],
                name=h["name"],
                specialty=h["specialty"],
                organization=h.get("organization"),
                region=h.get("region"),
            )
        )
        for p in h.get("preferences", []):
            session.add(HCPPreference(hcp_id=hcp_id, key=p["key"], value=p["value"], weight=p["weight"]))
        for i in h.get("interests", []):
            session.add(
                HCPInterest(
                    hcp_id=hcp_id,
                    entity=i["entity"],
                    entity_type=i["entity_type"],
                    score=i["score"],
                    interaction_count=i.get("interaction_count", 1),
                    last_interaction_at=datetime.fromisoformat(i["last_interaction_at"])
                    if i.get("last_interaction_at")
                    else None,
                )
            )
    await session.flush()


async def seed_resources(session: AsyncSession, settings: Settings, resource_dir: Path) -> dict[str, uuid.UUID]:
    embedder = build_ai_providers(settings).embedder
    parsed: list[ParsedResource] = [parse_resource_file(p) for p in sorted(resource_dir.glob("*.md"))]
    ids = {r.key: stable_id("resource", r.key) for r in parsed}
    # Insert in publication order so superseded versions exist before their successors.
    for r in sorted(parsed, key=lambda r: r.published_at):
        session.add(
            Resource(
                id=ids[r.key],
                title=r.title,
                product=r.product,
                resource_type=r.resource_type.value,
                version=r.version,
                published_at=r.published_at,
                supersedes_resource_id=ids.get(r.supersedes_key) if r.supersedes_key else None,
                source_url=r.source_url,
                is_approved=r.is_approved,
                metadata_={**r.metadata, "key": r.key, "synthetic": True},
            )
        )
        await session.flush()
        chunks = chunk_sections(r.sections)
        vectors = await embed_chunks(chunks, embedder, title=r.title)
        for c, v in zip(chunks, vectors, strict=True):
            session.add(
                ResourceChunk(
                    id=stable_id("chunk", f"{r.key}:{c.index}"),
                    resource_id=ids[r.key],
                    chunk_index=c.index,
                    text=c.text,
                    section=c.section,
                    page=c.page,
                    embedding=v,
                    metadata_={
                        "embedding_model": "mock-hash" if settings.ai_is_mocked else settings.gemini_embedding_model
                    },
                )
            )
        logger.info("seeded resource", extra={"key": r.key, "chunks": len(chunks)})
    await session.flush()
    return ids


async def seed_history(session: AsyncSession, events: list[dict[str, Any]], resource_ids: dict[str, uuid.UUID]) -> None:
    for e in events:
        session.add(
            InteractionEvent(
                id=uuid.uuid4(),
                timestamp=datetime.fromisoformat(e["timestamp"]),
                hcp_id=stable_id("hcp", e["hcp_external_id"]),
                event_type=e["event_type"],
                query_text=e.get("query_text"),
                intent=e.get("intent"),
                entity=e.get("entity"),
                topic=e.get("topic"),
                resource_id=resource_ids[e["resource_key"]] if e.get("resource_key") else None,
                metadata_={"seeded": True},
            )
        )
    await session.flush()


async def seed_database(engine: AsyncEngine, settings: Settings, *, reset: bool) -> int:
    """Load all seed data in one transaction, then refresh time-series aggregates.

    Returns the number of resources seeded. Used by the CLI and the integration tests.
    """
    seed_dir = settings.data_dir / "seed"
    async with create_session_factory(engine)() as session, session.begin():
        if reset:
            await session.execute(text(f"TRUNCATE {', '.join(TABLES)} CASCADE"))
        await seed_hcps(session, _load_json(seed_dir / "hcps.json"))
        resource_ids = await seed_resources(session, settings, seed_dir / "resources")
        await seed_history(session, _load_json(seed_dir / "history.json"), resource_ids)
    # TRUNCATE doesn't invalidate continuous aggregates and backfilled history may sit below the
    # refresh watermark, so rebuild the aggregate explicitly.
    await refresh_topic_cagg(engine)
    return len(resource_ids)


async def run(reset: bool) -> None:
    settings = get_settings()
    engine = create_engine(settings)
    try:
        count = await seed_database(engine, settings, reset=reset)
    finally:
        await engine.dispose()
    mode = "mock" if settings.ai_is_mocked else "gemini"
    print(f"Seeded {count} resources, embeddings={mode}, dim={settings.gemini_embedding_dimension}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="truncate all tables before seeding")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run(args.reset))


if __name__ == "__main__":
    main()

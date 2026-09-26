"""The DEMO_FLOW script against real SQL repositories, Timescale and pgvector (mock AI)."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from app.ambient.personalization import EngagementService, PersonalizationService
from app.dependencies import Repositories, build_orchestrator, build_repositories
from app.impiricus.mock_ion import MockIONService
from app.ingestion.seed import stable_id
from app.schemas.ambient import AmbientResponse, EngagementEventRequest
from app.schemas.enums import EventType, InputMode, IntentType

pytestmark = pytest.mark.integration

MORGAN = stable_id("hcp", "SYN-HCP-001")
WHATS_CHANGED = "What's changed with Novara since I last looked at it?"


async def ask(db, ai, query: str, session_id=None, mode: InputMode = InputMode.TEXT) -> AmbientResponse:
    """One API request = one DB transaction, exactly like the FastAPI dependency."""
    async with db.session() as session, session.begin():
        repos = build_repositories(session, db.capabilities)
        return await build_orchestrator(db.settings, ai, repos).process_query(MORGAN, session_id, query, mode)


async def with_repos(db, fn):
    async with db.session() as session, session.begin():
        return await fn(build_repositories(session, db.capabilities))


async def test_schema_uses_tiger_data_features(db) -> None:
    assert db.capabilities["pgvector"]
    if not db.capabilities["timescaledb"]:
        pytest.skip("plain PostgreSQL: hypertable/cagg checks not applicable")
    assert db.capabilities["topic_cagg"]
    async with db.engine.connect() as conn:
        hypertables = (
            await conn.execute(text("SELECT hypertable_name FROM timescaledb_information.hypertables"))
        ).scalars()
        assert "interaction_event" in set(hypertables)
        realtime = await conn.scalar(
            text(
                "SELECT NOT materialized_only FROM timescaledb_information.continuous_aggregates "
                "WHERE view_name = 'hcp_topic_engagement_daily'"
            )
        )
        assert realtime


async def test_whats_new_finds_resources_published_after_last_review(db, ai) -> None:
    resp = await ask(db, ai, WHATS_CHANGED, mode=InputMode.VOICE)
    assert resp.intent == IntentType.WHATS_NEW
    assert "July 2, 2026" in resp.response.text
    assert {(e.title, e.version) for e in resp.evidence} == {
        ("Novara Prescribing Information", "2.0"),
        ("Novara Trial A Long-Term Follow-Up", "1.0"),
    }
    renal = next(c for d in resp.changes for c in d.changes if c.topic == "Renal Impairment")
    assert renal.change_type == "UPDATED"


async def test_follow_up_resolves_product_across_requests(db, ai) -> None:
    first = await ask(db, ai, WHATS_CHANGED)
    follow = await ask(db, ai, "What about renal impairment?", session_id=first.session_id)
    assert follow.intent == IntentType.FOLLOW_UP
    assert follow.context.active_entity == "Novara"
    assert follow.evidence[0].section == "Renal Impairment"
    assert follow.evidence[0].version == "2.0"


async def test_source_open_moves_the_whats_new_anchor(db, ai) -> None:
    first = await ask(db, ai, WHATS_CHANGED)
    pi_v2 = next(e for e in first.evidence if e.version == "2.0")

    async def open_source(repos: Repositories):
        ion = MockIONService(repos.hcps, repos.interactions, repos.resources)
        service = EngagementService(repos.interactions, repos.resources, PersonalizationService(ion))
        return await service.record(
            EngagementEventRequest(
                hcp_id=MORGAN,
                session_id=first.session_id,
                event_type=EventType.SOURCE_OPEN,
                resource_id=pi_v2.resource_id,
            )
        )

    event, signals = await with_repos(db, open_source)
    assert event.entity == "Novara" and signals[0].weight == 0.10

    again = await ask(db, ai, WHATS_CHANGED)
    assert again.evidence == []
    assert again.response.insufficient_evidence
    assert "couldn't find new approved Novara resources" in again.response.text


async def test_signals_persist_to_hcp_interest(db, ai) -> None:
    before = {i.entity: i.score for i in await with_repos(db, lambda r: r.hcps.get_interests(MORGAN))}
    await ask(db, ai, "What about Novara in renal impairment?", mode=InputMode.VOICE)
    after = {i.entity: i for i in await with_repos(db, lambda r: r.hcps.get_interests(MORGAN))}
    assert after["Novara"].score == pytest.approx(before["Novara"] + 0.08)
    assert after["renal impairment"].score == pytest.approx(0.08)
    assert after["renal impairment"].interaction_count == 1


async def test_engagement_cagg_is_realtime_and_matches_raw(db, ai) -> None:
    if not db.capabilities["topic_cagg"]:
        pytest.skip("continuous aggregate requires TimescaleDB")
    await ask(db, ai, "What about Novara in renal impairment?")

    async def both(repos: Repositories):
        interactions = repos.interactions
        from_cagg = await interactions.engagement_over_time(MORGAN)
        interactions.use_topic_cagg = False
        from_raw = await interactions.engagement_over_time(MORGAN)
        return from_cagg, from_raw

    from_cagg, from_raw = await with_repos(db, both)
    as_set = lambda pts: {(p.bucket, p.topic, p.event_count) for p in pts}  # noqa: E731
    assert as_set(from_cagg) == as_set(from_raw)
    days = {p.bucket.date() for p in from_cagg}
    assert datetime(2026, 6, 14).date() in days, "history older than 90 days must not vanish"
    assert datetime.now(UTC).date() in days, "today's query must appear without waiting for a refresh"


async def test_trending_and_activity(db, ai) -> None:
    start = datetime.now(UTC)
    await ask(db, ai, "What about Novara in renal impairment?")
    trending = await with_repos(db, lambda r: r.interactions.trending_topics(window="1 day"))
    assert trending and trending[0].topic == "renal impairment" and trending[0].hcp_count == 1
    recent = await with_repos(db, lambda r: r.interactions.recent(MORGAN, since=start))
    assert {e.event_type for e in recent} == {EventType.SESSION_STARTED, EventType.TEXT_QUERY}


async def test_todays_events_stay_visible_after_a_refresh(db, ai) -> None:
    """Regression: a full refresh must not materialize today's incomplete bucket.

    If it does, the cagg watermark jumps to tomorrow and later events today fall below it, so they
    disappear from the real-time aggregate until the next refresh.
    """
    if not db.capabilities["topic_cagg"]:
        pytest.skip("continuous aggregate requires TimescaleDB")
    from app.db.session import refresh_topic_cagg

    await ask(db, ai, "What about Novara in renal impairment?")
    await refresh_topic_cagg(db.engine)  # e.g. `make seed`, a backfill, or a manual refresh
    await ask(db, ai, "What about Novara dosing?")

    points = await with_repos(db, lambda r: r.interactions.engagement_over_time(MORGAN))
    today = {p.topic: p.event_count for p in points if p.bucket.date() == datetime.now(UTC).date()}
    assert today.get("renal impairment") == 1
    assert today.get("dosing") == 1, f"event after refresh missing from cagg: {today}"


async def test_demo_works_on_compressed_history(db, ai) -> None:
    """Columnstore (0004): compressed chunks must stay readable, writable (backfill) and aggregatable."""
    if not db.capabilities["timescaledb"]:
        pytest.skip("compression requires TimescaleDB")
    from app.db.session import refresh_topic_cagg
    from app.schemas.interaction import InteractionEventCreate

    async with db.engine.connect() as conn:
        conn = await conn.execution_options(isolation_level="AUTOCOMMIT")
        await conn.execute(
            text(
                "SELECT compress_chunk(c, if_not_compressed => TRUE) "
                "FROM show_chunks('interaction_event', older_than => INTERVAL '30 days') c"
            )
        )
        compressed = await conn.scalar(
            text(
                "SELECT count(*) FROM timescaledb_information.chunks "
                "WHERE hypertable_name = 'interaction_event' AND is_compressed"
            )
        )
    assert compressed >= 1, "seeded June/July history should be in compressed chunks"

    # Reads over compressed history: the July 2 review still anchors "what's new".
    resp = await ask(db, ai, WHATS_CHANGED)
    assert "July 2, 2026" in resp.response.text and len(resp.evidence) == 2

    # Backfill into a compressed chunk, then refresh the aggregate.
    await with_repos(
        db,
        lambda r: r.interactions.record(
            InteractionEventCreate(
                hcp_id=MORGAN,
                event_type=EventType.TEXT_QUERY,
                timestamp=datetime(2026, 6, 14, 15, 0, tzinfo=UTC),
                query_text="backfilled",
                entity="Novara",
                topic="dosing",
            )
        ),
    )
    await refresh_topic_cagg(db.engine)
    points = await with_repos(db, lambda r: r.interactions.engagement_over_time(MORGAN))
    june = {p.topic: p.event_count for p in points if p.bucket.date() == datetime(2026, 6, 14).date()}
    assert june.get("dosing") == 1

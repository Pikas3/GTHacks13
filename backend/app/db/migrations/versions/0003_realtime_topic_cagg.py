"""Rebuild the daily topic-engagement continuous aggregate: real-time, complete, topic-only.

Problems with the aggregate created in 0002:
1. New caggs default to `materialized_only = true`, so events newer than the last refresh (the demo's
   own queries) never appeared. Real-time aggregation unions materialized buckets with a live query
   over rows past the watermark.
2. The refresh policy used `start_offset => 90 days`, so older history (the seeded 2026-06-14 events)
   was never materialized, and rows below the watermark aren't covered by real-time aggregation
   either, so they silently vanished. Demo volume is tiny, so the policy now refreshes the whole range.
3. `SESSION_STARTED` events (no topic) were counted as a "general" topic.

The initial refresh stops at the start of today's bucket: refreshing the incomplete current bucket
moves the watermark to tomorrow, which hides the rest of today's events from real-time aggregation.

A cagg's query can't be altered, so it is dropped and recreated. Skipped on plain PostgreSQL. Runs in
autocommit because cagg DDL, policies and refreshes can't run inside a transaction.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CAGG = "hcp_topic_engagement_daily"


def _has_timescale() -> bool:
    bind = op.get_bind()
    return bool(bind.execute(sa.text("SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'")).scalar())


def _create(*, materialized_only: bool, where: str, start_offset: str) -> None:
    op.execute(f"DROP MATERIALIZED VIEW IF EXISTS {CAGG}")
    op.execute(
        f"""
        CREATE MATERIALIZED VIEW {CAGG}
        WITH (timescaledb.continuous, timescaledb.materialized_only = {str(materialized_only).lower()}) AS
        SELECT
            time_bucket(INTERVAL '1 day', "timestamp") AS bucket,
            hcp_id,
            COALESCE(topic, entity, 'general') AS topic,
            count(*) AS event_count
        FROM interaction_event
        {where}
        GROUP BY bucket, hcp_id, COALESCE(topic, entity, 'general')
        WITH NO DATA
        """
    )
    op.execute(
        f"""
        SELECT add_continuous_aggregate_policy('{CAGG}',
            start_offset => {start_offset},
            end_offset => INTERVAL '1 hour',
            schedule_interval => INTERVAL '15 minutes')
        """
    )
    op.execute(f"CALL refresh_continuous_aggregate('{CAGG}', NULL, time_bucket(INTERVAL '1 day', now()))")


def upgrade() -> None:
    if not _has_timescale():
        return
    with op.get_context().autocommit_block():
        _create(materialized_only=False, where="WHERE event_type <> 'SESSION_STARTED'", start_offset="NULL")


def downgrade() -> None:
    if not _has_timescale():
        return
    with op.get_context().autocommit_block():
        _create(materialized_only=True, where="", start_offset="INTERVAL '90 days'")

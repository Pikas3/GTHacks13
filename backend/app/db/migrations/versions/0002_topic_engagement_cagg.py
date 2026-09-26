"""Optional Timescale continuous aggregate: daily HCP topic engagement.

Skipped automatically on plain PostgreSQL. Continuous aggregates cannot be created inside a
transaction, so this runs in an autocommit block.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_timescale() -> bool:
    bind = op.get_bind()
    return bool(bind.execute(sa.text("SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'")).scalar())


def upgrade() -> None:
    if not _has_timescale():
        return
    with op.get_context().autocommit_block():
        op.execute(
            """
            CREATE MATERIALIZED VIEW IF NOT EXISTS hcp_topic_engagement_daily
            WITH (timescaledb.continuous) AS
            SELECT
                time_bucket(INTERVAL '1 day', "timestamp") AS bucket,
                hcp_id,
                COALESCE(topic, entity, 'general') AS topic,
                count(*) AS event_count
            FROM interaction_event
            GROUP BY bucket, hcp_id, COALESCE(topic, entity, 'general')
            WITH NO DATA
            """
        )
        # TODO(database): tune refresh policy for demo freshness vs. cost.
        op.execute(
            """
            SELECT add_continuous_aggregate_policy('hcp_topic_engagement_daily',
                start_offset => INTERVAL '90 days',
                end_offset => INTERVAL '1 hour',
                schedule_interval => INTERVAL '15 minutes',
                if_not_exists => TRUE)
            """
        )


def downgrade() -> None:
    if not _has_timescale():
        return
    with op.get_context().autocommit_block():
        op.execute("DROP MATERIALIZED VIEW IF EXISTS hcp_topic_engagement_daily")

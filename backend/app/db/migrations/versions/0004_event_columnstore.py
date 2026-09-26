"""Compress (columnstore) old interaction_event chunks.

Engagement events are append-only and, once a few weeks old, only read by aggregate/time-range
queries. Columnstore compression cuts storage substantially at scale and speeds up those scans:
- `segmentby = hcp_id`: almost every query filters by HCP, so each compressed segment holds one HCP's
  events and whole segments are skipped for other HCPs.
- `orderby = timestamp DESC`: matches the timeline/"since I last looked" access pattern.
Chunks older than 30 days are converted by a background policy. Queries, inserts (e.g. seed backfill)
and TRUNCATE keep working on compressed chunks; the continuous aggregate is unaffected.

Retention (dropping old chunks) is deliberately NOT enabled: the continuous aggregate's refresh
policy covers the full range (0003), so dropping raw chunks would also erase their aggregated history.

Uses the columnstore API (TimescaleDB >= 2.18) and falls back to the older compression API. Skipped on
plain PostgreSQL.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "interaction_event"
COMPRESS_AFTER = "INTERVAL '30 days'"


def _has_timescale() -> bool:
    bind = op.get_bind()
    return bool(bind.execute(sa.text("SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'")).scalar())


def _has_columnstore_api() -> bool:
    bind = op.get_bind()
    return bool(bind.execute(sa.text("SELECT 1 FROM pg_proc WHERE proname = 'add_columnstore_policy'")).scalar())


def upgrade() -> None:
    if not _has_timescale():
        return
    op.execute(
        f"""
        ALTER TABLE {TABLE} SET (
            timescaledb.compress,
            timescaledb.compress_segmentby = 'hcp_id',
            timescaledb.compress_orderby = 'timestamp DESC'
        )
        """
    )
    if _has_columnstore_api():
        op.execute(f"CALL add_columnstore_policy('{TABLE}', after => {COMPRESS_AFTER}, if_not_exists => TRUE)")
    else:
        op.execute(
            f"SELECT add_compression_policy('{TABLE}', compress_after => {COMPRESS_AFTER}, if_not_exists => TRUE)"
        )


def downgrade() -> None:
    if not _has_timescale():
        return
    if _has_columnstore_api():
        op.execute(f"CALL remove_columnstore_policy('{TABLE}', if_exists => TRUE)")
    else:
        op.execute(f"SELECT remove_compression_policy('{TABLE}', if_exists => TRUE)")
    op.execute(f"SELECT decompress_chunk(c, if_compressed => TRUE) FROM show_chunks('{TABLE}') c")
    op.execute(f"ALTER TABLE {TABLE} SET (timescaledb.compress = false)")

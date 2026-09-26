"""Initial schema: HCP profile tables, resources + pgvector chunks, conversation state,
and the interaction_event time-series table (Timescale hypertable when available).

Revision ID: 0001
Revises:
Create Date: 2026-09-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql as pg

from app.config import get_settings

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBEDDING_DIM = get_settings().gemini_embedding_dimension

UUID = pg.UUID(as_uuid=True)
TS = sa.DateTime(timezone=True)
JSONB_EMPTY = {"server_default": sa.text("'{}'::jsonb"), "nullable": False}


def upgrade() -> None:
    # pgvector is required (available on Tiger Data and the timescaledb-ha image).
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # TimescaleDB is optional: try to enable it, degrade gracefully on plain PostgreSQL.
    op.execute(
        """
        DO $$
        BEGIN
            CREATE EXTENSION IF NOT EXISTS timescaledb;
        EXCEPTION WHEN OTHERS THEN
            RAISE NOTICE 'timescaledb not available; interaction_event stays a regular table';
        END $$;
        """
    )

    op.create_table(
        "hcp",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("external_id", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("specialty", sa.String(120), nullable=False),
        sa.Column("organization", sa.String(200)),
        sa.Column("region", sa.String(120)),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "hcp_preference",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("hcp_id", UUID, sa.ForeignKey("hcp.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("key", sa.String(120), nullable=False),
        sa.Column("value", sa.String(500), nullable=False),
        sa.Column("weight", sa.Float, nullable=False, server_default="0.5"),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", TS, server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "hcp_interest",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("hcp_id", UUID, sa.ForeignKey("hcp.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("entity", sa.String(200), nullable=False),
        sa.Column("entity_type", sa.String(40), nullable=False),
        sa.Column("score", sa.Float, nullable=False, server_default="0"),
        sa.Column("interaction_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_interaction_at", TS, server_default=sa.func.now()),
        sa.UniqueConstraint("hcp_id", "entity", name="uq_hcp_interest_hcp_entity"),
    )

    op.create_table(
        "resource",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("product", sa.String(120), nullable=False, index=True),
        sa.Column("resource_type", sa.String(40), nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("published_at", TS, nullable=False, index=True),
        sa.Column("supersedes_resource_id", UUID, sa.ForeignKey("resource.id", ondelete="SET NULL")),
        sa.Column("source_url", sa.String(500)),
        sa.Column("is_approved", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("metadata", pg.JSONB, **JSONB_EMPTY),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "resource_chunk",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("resource_id", UUID, sa.ForeignKey("resource.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("section", sa.String(200)),
        sa.Column("page", sa.Integer),
        sa.Column("metadata", pg.JSONB, **JSONB_EMPTY),
        sa.Column("embedding", Vector(EMBEDDING_DIM)),
    )
    # Approximate nearest-neighbour index for cosine similarity.
    op.execute(
        "CREATE INDEX ix_resource_chunk_embedding_hnsw ON resource_chunk USING hnsw (embedding vector_cosine_ops)"
    )

    op.create_table(
        "conversation_session",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("hcp_id", UUID, sa.ForeignKey("hcp.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("started_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("last_activity_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("active_entity", sa.String(200)),
        sa.Column("active_topic", sa.String(200)),
        sa.Column("active_resource_id", UUID, sa.ForeignKey("resource.id", ondelete="SET NULL")),
        sa.Column("context", pg.JSONB, **JSONB_EMPTY),
    )

    op.create_table(
        "conversation_turn",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "session_id",
            UUID,
            sa.ForeignKey("conversation_session.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("created_at", TS, server_default=sa.func.now(), nullable=False),
        sa.Column("metadata", pg.JSONB, **JSONB_EMPTY),
    )

    op.create_table(
        "interaction_event",
        sa.Column("id", UUID, nullable=False),
        sa.Column("timestamp", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("hcp_id", UUID, sa.ForeignKey("hcp.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", UUID),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("query_text", sa.Text),
        sa.Column("response_text", sa.Text),
        sa.Column("intent", sa.String(40)),
        sa.Column("entity", sa.String(200)),
        sa.Column("topic", sa.String(200)),
        sa.Column("resource_id", UUID),
        sa.Column("metadata", pg.JSONB, **JSONB_EMPTY),
        # Timescale requires the time column in every unique constraint.
        sa.PrimaryKeyConstraint("id", "timestamp", name="pk_interaction_event"),
    )
    op.create_index("ix_interaction_event_hcp_ts", "interaction_event", ["hcp_id", "timestamp"])
    op.create_index("ix_interaction_event_hcp_entity_ts", "interaction_event", ["hcp_id", "entity", "timestamp"])

    # Convert to a hypertable when TimescaleDB is present (no-op on plain PostgreSQL).
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'timescaledb') THEN
                PERFORM create_hypertable(
                    'interaction_event', 'timestamp',
                    chunk_time_interval => INTERVAL '7 days',
                    if_not_exists => TRUE,
                    migrate_data => TRUE
                );
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    for table in (
        "interaction_event",
        "conversation_turn",
        "conversation_session",
        "resource_chunk",
        "resource",
        "hcp_interest",
        "hcp_preference",
        "hcp",
    ):
        op.drop_table(table)

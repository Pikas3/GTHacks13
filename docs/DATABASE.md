# Database

Tiger Data / TimescaleDB-compatible PostgreSQL with **pgvector** (required) and **TimescaleDB** (optional,
used when present). Connect with `DATABASE_URL`. `postgres://…?sslmode=require` URLs from Tiger Data are
normalized automatically for asyncpg (`app/config.py`).

- Local: `make db-up` starts `timescale/timescaledb-ha:pg17` on **port 5433**. 5433 avoids a clash with any
  local Postgres on 5432.
- Cloud: set `DATABASE_URL` to your Tiger Data service, then `make migrate seed`.

## Tables

| Table | Kind | Notes |
|-------|------|-------|
| `hcp` | relational | synthetic profiles; `external_id` unique (`SYN-HCP-00x`) |
| `hcp_preference` | relational | key/value/weight (e.g. `clinical_evidence`, 0.8) |
| `hcp_interest` | relational | `(hcp_id, entity)` unique; `score` 0–1, `interaction_count`, `last_interaction_at` |
| `resource` | relational | `product`, `resource_type`, `version`, `published_at`, `supersedes_resource_id` (self-FK), `is_approved`, `metadata` JSONB |
| `resource_chunk` | relational + vector | `section`, `page`, `text`, `embedding vector(768)`, HNSW `vector_cosine_ops` index |
| `interaction_event` | **hypertable** on `timestamp` (7-day chunks) | PK `(id, timestamp)`; indexes `(hcp_id, timestamp)`, `(hcp_id, entity, timestamp)`; signals stored in `metadata.signals` |
| `conversation_session` | relational | `active_entity`, `active_topic`, `active_resource_id`, `context` JSONB (`ConversationContext`) |
| `conversation_turn` | relational | `role`, `content`, `metadata` |
| `hcp_topic_engagement_daily` | continuous aggregate | daily `(hcp_id, topic) → event_count`, refreshed every 15 min |

Migrations: `backend/app/db/migrations/versions/`

- `0001_initial_schema.py` creates the extensions, all tables, the HNSW index and `create_hypertable(...)`.
  The hypertable step only runs if `timescaledb` is installed.
- `0002_topic_engagement_cagg.py` creates the continuous aggregate and refresh policy. It is skipped on
  plain Postgres.

```bash
make migrate                                  # alembic upgrade head
cd backend && .venv/bin/alembic revision -m "add x"   # new migration (write ops by hand or --autogenerate)
```

## Embedding dimension

`GEMINI_EMBEDDING_DIMENSION` (default **768**) is the single source of truth. The ORM model, the migration
and `output_dimensionality` in the Gemini call all read it. To change it, add a migration that alters
`resource_chunk.embedding` (and rebuilds the HNSW index), then run `make seed` again. pgvector HNSW
supports up to 2000 dimensions.

## Example time-series queries

Implemented in `app/db/repositories/interaction_repository.py`. Raw SQL for exploration:

```sql
-- Recent HCP events (timeline)
SELECT timestamp, event_type, entity, topic, query_text
FROM interaction_event WHERE hcp_id = :hcp ORDER BY timestamp DESC LIMIT 20;

-- Activity since a timestamp
SELECT * FROM interaction_event WHERE hcp_id = :hcp AND timestamp > :since ORDER BY timestamp;

-- Last time the HCP *reviewed* Novara ("since I last looked at it")
SELECT e.timestamp FROM interaction_event e LEFT JOIN resource r ON r.id = e.resource_id
WHERE e.hcp_id = :hcp AND e.event_type IN ('RESOURCE_VIEW','SOURCE_OPEN','RESOURCE_SAVED')
  AND (e.entity ILIKE 'Novara' OR r.product ILIKE 'Novara')
ORDER BY e.timestamp DESC LIMIT 1;

-- Event counts by topic / most-queried entities
SELECT COALESCE(topic, entity) AS label, count(*) FROM interaction_event
WHERE hcp_id = :hcp GROUP BY 1 ORDER BY 2 DESC;

-- Engagement over time (Timescale)
SELECT time_bucket(INTERVAL '1 day', timestamp) AS bucket, COALESCE(topic, entity, 'general') AS topic, count(*)
FROM interaction_event WHERE hcp_id = :hcp GROUP BY 1, 2 ORDER BY 1;

-- Same, from the continuous aggregate
SELECT * FROM hcp_topic_engagement_daily WHERE hcp_id = :hcp ORDER BY bucket;

-- Vector search (what ResourceRepository.vector_search runs)
SELECT c.section, r.title, 1 - (c.embedding <=> :query_vec) AS similarity
FROM resource_chunk c JOIN resource r ON r.id = c.resource_id
WHERE r.product ILIKE 'Novara' AND r.is_approved
ORDER BY c.embedding <=> :query_vec LIMIT 8;
```

## Seeding

`make seed` runs `python -m app.ingestion.seed --reset`. It truncates everything, then loads:

- `data/seed/hcps.json`: 3 synthetic HCPs with preferences and starting interests
- `data/seed/resources/*.md`: 9 fictional resources, parsed into sections, chunked and embedded with the
  current provider
- `data/seed/history.json`: prior events (Dr. Morgan: PI v1 view on 2026-06-14, "long-term outcomes" query
  on 2026-06-14, Access Guide view on 2026-07-02)

IDs are deterministic (`uuid5`), so Dr. Morgan's ID stays the same across reseeds. **Re-seed to reset demo
state.**

TODO(database): add retention/compression policies on `interaction_event` if volume grows. Read
`engagement_over_time` from the continuous aggregate.

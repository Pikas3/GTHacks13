# Database

Tiger Data / TimescaleDB-compatible PostgreSQL with **pgvector** (required) and **TimescaleDB** (optional,
used when present). Connect with `DATABASE_URL`. `postgres://…?sslmode=require` URLs from Tiger Data are
normalized automatically for asyncpg (`app/config.py`).

- Local: `make db-up` starts `timescale/timescaledb-ha:pg17` on **port 5433**. 5433 avoids a clash with any
  local Postgres on 5432.
- Cloud: set `DATABASE_URL` to your Tiger Data service, then `make migrate seed db-verify`
  (details below).

## Tiger Data (cloud) deployment

1. In the Tiger Cloud console create a **Time-series and analytics** service (PostgreSQL 17 +
   TimescaleDB). pgvector ships with every service; migration 0001 runs `CREATE EXTENSION IF NOT EXISTS
   vector`, which `tsdbadmin` is allowed to do.
2. Copy the **service URL** (`postgres://tsdbadmin:…@<id>.<project>.tsdb.cloud.timescale.com:<port>/tsdb?sslmode=require`)
   into `.env` as `DATABASE_URL`. **Never commit it** (`.env` is git-ignored). The URL is normalized
   automatically: scheme → `postgresql+asyncpg`, `sslmode` → asyncpg `ssl=` (`require`, `verify-ca` and
   `verify-full` are passed through).
3. Run:

   ```bash
   make migrate seed db-verify
   ```

   `db-verify` (`python -m app.db.verify`) prints extension versions, hypertables, continuous aggregates,
   Timescale jobs and row counts, and exits non-zero if something is missing. Expected on Tiger Data:
   `vector` + `timescaledb` in the extension list; `interaction_event` in
   `timescaledb_information.hypertables`; `hcp_topic_engagement_daily` in
   `timescaledb_information.continuous_aggregates`; a refresh-policy job.
4. `make backend`, then `curl -s localhost:8000/api/health` should show `"database": "ok",
   "timescaledb": true, "pgvector": true`.
5. Optional: `make backend-itest TEST_DATABASE_URL="$DATABASE_URL"` runs the integration suite in a
   throwaway schema on the same service (demo data is untouched).

Manual check in `psql "$DATABASE_URL"`:

```sql
SELECT extname, extversion FROM pg_extension WHERE extname IN ('timescaledb', 'vector');
SELECT hypertable_name, num_chunks FROM timescaledb_information.hypertables;
SELECT view_name, materialized_only FROM timescaledb_information.continuous_aggregates;
SELECT job_id, proc_name, schedule_interval FROM timescaledb_information.jobs WHERE job_id >= 1000;
```

### Connection settings (all in `app/config.py`, overridable from `.env`)

| Setting | Default | Why |
|---------|---------|-----|
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` | 5 / 5 | Tiger Data plans cap connections, and backend + seed + teammates share them |
| `DB_POOL_RECYCLE_S` | 1800 | recycle before cloud idle timeouts drop connections (plus `pool_pre_ping`) |
| `DB_CONNECT_TIMEOUT_S` | 10 | fail fast instead of hanging a request when the service is paused/unreachable |
| `DB_STATEMENT_TIMEOUT_MS` | 15000 | server-side `statement_timeout` per connection; `0` disables. Migrations always run without it |
| `DB_SEARCH_PATH` | unset | put all tables (and `alembic_version`) in your own schema, e.g. one per teammate on a shared service. Extensions stay in `public`. Create the schema first: `CREATE SCHEMA dev_alex;` |
| `DB_USE_POOLER` | false | set `true` if `DATABASE_URL` uses Tiger's transaction-mode pooler; disables asyncpg prepared-statement caches |

Every connection also sets `application_name = impiricus-ambient`, so it is easy to find in
`pg_stat_activity`.

### Troubleshooting

| Symptom | Fix |
|---------|-----|
| `permission denied to create extension "vector"` | enable pgvector from the service's console (Extensions) or as `tsdbadmin`, then re-run `make migrate` |
| `/api/health` shows `timescaledb: false` on Tiger Data | the backend could not reach the DB at startup; capabilities are re-detected on the next request / health check once it is reachable |
| `ssl` / certificate errors | keep `?sslmode=require` in the URL; `verify-full` needs the CA in the system trust store |
| `prepared statement "__asyncpg_stmt_…" does not exist` | you are on the pooler URL: set `DB_USE_POOLER=true` or use the direct service URL |
| `canceling statement due to statement timeout` | raise `DB_STATEMENT_TIMEOUT_MS`, or look for a missing index |
| connection refused after a long idle period | the service may be paused; resume it in the console, then retry |

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

## Integration tests

```bash
make backend-itest                                   # default: local compose DB on :5433
make backend-itest TEST_DATABASE_URL="$DATABASE_URL" # or a Tiger Data service
```

`tests/integration/` is skipped unless `TEST_DATABASE_URL` is set, and `make backend-test` excludes it
(`-m "not integration"`). Each run creates schema `itest_<random>`, runs the real Alembic migrations into
it via `DB_SEARCH_PATH` (including the hypertable + continuous aggregate when Timescale is present),
re-seeds before every test, drives the `docs/DEMO_FLOW.md` script through the FastAPI app with mock AI,
and drops the schema at the end.

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

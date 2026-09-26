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
| `hcp_interest` | relational | `(hcp_id, entity)` unique; `score` 0–1 as of `last_interaction_at`, `interaction_count`. Read through `MockIONService`, which applies time decay (see below) |
| `resource` | relational | `product`, `resource_type`, `version`, `published_at`, `supersedes_resource_id` (self-FK), `is_approved`, `metadata` JSONB |
| `resource_chunk` | relational + vector | `section`, `page`, `text`, `embedding vector(768)`, HNSW `vector_cosine_ops` index |
| `interaction_event` | **hypertable** on `timestamp` (7-day chunks), **columnstore** after 30 days | PK `(id, timestamp)`; indexes `(hcp_id, timestamp)`, `(hcp_id, entity, timestamp)`; signals stored in `metadata.signals` |
| `conversation_session` | relational | `active_entity`, `active_topic`, `active_resource_id`, `context` JSONB (`ConversationContext`) |
| `conversation_turn` | relational | `role`, `content`, `metadata` |
| `hcp_topic_engagement_daily` | continuous aggregate (**real-time**) | daily `(hcp_id, topic) → event_count`, excludes `SESSION_STARTED`; policy refreshes the full range every 15 min; today's events come from real-time aggregation |

Migrations: `backend/app/db/migrations/versions/`

- `0001_initial_schema.py` creates the extensions, all tables, the HNSW index and `create_hypertable(...)`.
  The hypertable step only runs if `timescaledb` is installed.
- `0002_topic_engagement_cagg.py` creates the continuous aggregate and refresh policy. It is skipped on
  plain Postgres.
- `0003_realtime_topic_cagg.py` rebuilds that aggregate: real-time (`materialized_only = false`), full-range
  refresh policy, and no `SESSION_STARTED` rows. See "Continuous aggregate pitfalls" below for why.
- `0004_event_columnstore.py` enables compression (columnstore) on `interaction_event` with a 30-day policy.
  See "Compression" below.

```bash
make migrate                                  # alembic upgrade head
cd backend && .venv/bin/alembic revision -m "add x"   # new migration (write ops by hand or --autogenerate)
```

## Continuous aggregate pitfalls (found the hard way)

The Intelligence page reads daily engagement from `hcp_topic_engagement_daily` (see
`SqlInteractionRepository.engagement_over_time`). For the numbers to be right *during a live demo*:

1. **Real-time aggregation must be on.** New caggs default to `materialized_only = true`, which only shows
   what the last refresh materialized, so the demo's own queries don't appear. 0003 sets it to `false`.
2. **Old history must be materialized.** Rows below the watermark are never computed live, so a policy with
   `start_offset => 90 days` silently dropped the 2026-06-14 seed history. The policy now uses
   `start_offset => NULL` (fine at demo volume; revisit for production data).
3. **Never refresh the current bucket.** `refresh_continuous_aggregate(cagg, NULL, NULL)` materializes
   today's incomplete bucket and moves the watermark to tomorrow. Every later event today then falls below
   the watermark and disappears until the next refresh. Manual refreshes stop at
   `time_bucket('1 day', now())` (`app/db/session.py::refresh_topic_cagg`), and the policy's
   `end_offset => 1 hour` already avoids it.
4. **TRUNCATE doesn't invalidate caggs.** `make seed` truncates, so it ends with a refresh
   (`seed_database` → `refresh_topic_cagg`).
5. **Concurrent refreshes fail.** Right after a migration the policy job may already be refreshing, and a
   manual refresh fails with "due to a concurrent refresh". `refresh_topic_cagg` retries with backoff.

`tests/integration/test_demo_flow.py` covers 1–3: the aggregate must equal the raw hypertable query,
must include June history, and must keep showing today's events after a refresh.

A development DB migrated with the *earlier* version of 0003 may have its watermark stuck at tomorrow. Fix
it with `cd backend && .venv/bin/alembic downgrade 0002 && .venv/bin/alembic upgrade head && cd .. && make seed`.

## Compression (columnstore)

Migration 0004 enables columnstore compression on `interaction_event`:

- `segmentby = hcp_id`: nearly every query filters by HCP, so other HCPs' segments are skipped entirely.
- `orderby = timestamp DESC`: matches the timeline and "since I last looked" access pattern.
- A background policy (every 12 h) compresses chunks older than 30 days.

Why it matters at scale: engagement events are append-only and, once a few weeks old, only read by
time-range or aggregate queries. Columnstore typically shrinks such data by an order of magnitude and makes
those scans faster, which is what keeps "one database for everything" viable as event volume grows. At demo
volume the benefit is illustrative. `tests/integration/test_demo_flow.py::test_demo_works_on_compressed_history`
proves the demo still works on compressed history: reads, a backfilled insert into a compressed chunk, and
aggregate refresh. Reseeding after compression works too; TRUNCATE handles compressed chunks.

```sql
-- Compress eligible chunks now instead of waiting for the policy (the team cloud service already has this applied)
SELECT compress_chunk(c, if_not_compressed => TRUE) FROM show_chunks('interaction_event', older_than => INTERVAL '30 days') c;
SELECT count(*) FILTER (WHERE is_compressed) AS compressed, count(*) AS chunks
FROM timescaledb_information.chunks WHERE hypertable_name = 'interaction_event';
SELECT * FROM hypertable_columnstore_stats('interaction_event');
```

**Retention is deliberately not enabled.** The aggregate's refresh policy covers the full time range (0003),
so dropping old raw chunks would also erase their aggregated history on the next refresh. If retention is
ever needed, bound the aggregate policy's `start_offset` below the retention `drop_after` first.

## Interest decay

`hcp_interest.score` is stored "as of `last_interaction_at`". `MockIONService` applies exponential decay
whenever it reads or updates a score:
`effective = score × 0.5^(days since last interaction / INTEREST_HALF_LIFE_DAYS)`.
A new signal adds its weight to the *decayed* score, then stores the result with a fresh
`last_interaction_at`. No batch job is needed, and every read path (`/hcps/{id}`, `/hcps/{id}/interests`,
`/intelligence/*`, retrieval personalization) shows the same numbers.

Default half-life is 90 days (`0` disables it). With it on, Dr. Morgan's seeded HER2 score (0.82 on July 2)
reads ~0.42 on 2026-09-26. This is a transparent hackathon heuristic, not an Impiricus algorithm.

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

-- Same, from the (real-time) continuous aggregate
SELECT * FROM hcp_topic_engagement_daily WHERE hcp_id = :hcp ORDER BY bucket;

-- Trending topics across all HCPs in a trailing window (GET /api/intelligence/topics/trending)
SELECT COALESCE(topic, entity) AS topic, count(*) AS events, count(DISTINCT hcp_id) AS hcps, max(timestamp) AS last_seen
FROM interaction_event
WHERE timestamp > now() - INTERVAL '7 days' AND event_type <> 'SESSION_STARTED' AND COALESCE(topic, entity) IS NOT NULL
GROUP BY 1 ORDER BY 2 DESC LIMIT 10;

-- Chunk exclusion: time predicates let Timescale skip hypertable chunks outside the window.
-- With no events in the last week this plan shows "One-Time Filter: false" (no chunks scanned).
EXPLAIN (COSTS OFF) SELECT count(*) FROM interaction_event WHERE timestamp > now() - INTERVAL '7 days';

-- Vector search (what ResourceRepository.vector_search runs)
SELECT c.section, r.title, 1 - (c.embedding <=> :query_vec) AS similarity
FROM resource_chunk c JOIN resource r ON r.id = c.resource_id
WHERE r.product ILIKE 'Novara' AND r.is_approved
ORDER BY c.embedding <=> :query_vec LIMIT 8;
```

## Tiger Data cloud

Verified 2026-09-26 against the team service: PostgreSQL 18.6, TimescaleDB 2.30.1, pgvector 0.8.6
(pgvectorscale 0.9.0 is also available but unused).

1. Put the service's connection string in the repo-root `.env` as `DATABASE_URL=postgres://tsdbadmin:…@….tsdb.cloud.timescale.com:<port>/tsdb?sslmode=require`.
   **Never commit it.** `.env` is git-ignored; share the string out-of-band. The app rewrites the URL for
   asyncpg, turning `sslmode=require` into `ssl=require`.
2. `make migrate seed`, then `make backend`. `GET /api/health` should report
   `timescaledb: true, pgvector: true, topic_cagg: true`.
3. Verify with `psql "<connection string>"`:
   ```sql
   SELECT hypertable_name FROM timescaledb_information.hypertables;                        -- interaction_event
   SELECT view_name, materialized_only FROM timescaledb_information.continuous_aggregates; -- hcp_topic_engagement_daily | f
   SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector', 'timescaledb');
   SELECT proc_name, config FROM timescaledb_information.jobs WHERE proc_name LIKE 'policy_%';
   ```

Findings compared with the local container:

| Topic | Result |
|---|---|
| Extensions / privileges | `tsdbadmin` can `CREATE EXTENSION vector`; `timescaledb` is preinstalled. Migrations ran unchanged |
| SSL | `sslmode=require` works through the URL normalization in `app/config.py` |
| Connections | `max_connections = 105`. SQLAlchemy's default pool (5 + 10 overflow) per backend process is fine, but don't run many workers × large pools |
| `statement_timeout` | `0` (none), same as local. Left as is |
| Time zone | `Etc/UTC`, same as local, so `date_trunc` and `time_bucket` agree |
| **Latency** | ~31 ms round trip from a dev laptop. An Ambient query runs ~20 statements, so it takes **0.6–1.6 s** against the cloud versus ~0.1 s locally. For the demo, run the backend close to the DB (same cloud region) or accept the delay. Reducing round trips (batching the HCP context reads) is the code-side fix if needed |

Don't point `TEST_DATABASE_URL` at the cloud service. The integration suite drops and recreates its database
(and refuses any database name without "test").

## Integration tests

```bash
make backend-itest   # default TEST_DATABASE_URL=postgresql+asyncpg://ambient:ambient@localhost:5433/ambient_test
```

- **Fresh database:** the suite drops and recreates the test database, then runs `alembic upgrade head`
  in a subprocess.
- **Reseeded per test:** every test reseeds and then runs the demo script through the real `Sql*`
  repositories with mock AI.
- **What it covers:** WHATS_NEW, follow-up resolution across requests, SOURCE_OPEN moving the "last looked"
  anchor, interest-score persistence, the aggregate matching the raw hypertable query, trending/activity,
  and an HTTP smoke test.
- **Not run by default:** `make backend-test` deselects these tests, and plain `pytest` skips them when
  `TEST_DATABASE_URL` is unset.

## Seeding

`make seed` runs `python -m app.ingestion.seed --reset`. It truncates everything, then loads:

- `data/seed/hcps.json`: 3 synthetic HCPs with preferences and starting interests
- `data/seed/resources/*.md`: 9 fictional resources, parsed into sections, chunked and embedded with the
  current provider
- `data/seed/history.json`: prior events (Dr. Morgan: PI v1 view on 2026-06-14, "long-term outcomes" query
  on 2026-06-14, Access Guide view on 2026-07-02)

IDs are deterministic (`uuid5`), so Dr. Morgan's ID stays the same across reseeds. Seeding ends by
refreshing the continuous aggregate. **Re-seed to reset demo state.**

# Agent prompt — Team Member C: Backend / Database (Tiger Data)

You are a senior backend engineer joining a hackathon team building **Impiricus Ambient**, a
voice-native, context-aware assistant for healthcare professionals (HCPs). The repository skeleton
already runs end-to-end against a local TimescaleDB + pgvector container. Your job is to own the data
layer and the Ambient pipeline's backbone: Tiger Data (cloud) deployment, Timescale time-series
features, conversation state, structured memory, personalization, the Impiricus integration mock, and
the API — keeping every contract stable for the other three workstreams.

## Product context (read carefully)

Every HCP interaction flows through `AmbientOrchestrator`: load HCP → load session → classify intent →
resolve context → load memory → retrieve evidence → generate grounded answer → store turns → update
interest signals → record a time-series engagement event → return. The company-facing `/intelligence`
view reads back what was learned.

**Why Tiger Data is central to the pitch:** one PostgreSQL-compatible store holds
(1) relational HCP state, (2) temporal engagement history in a Timescale **hypertable**, and (3) pgvector
embeddings. Make that architectural story real and demonstrable, not just generic Postgres.

Constraints: synthetic HCPs and fictional products only; no real patient data; no auth infrastructure;
no Redis/Kafka/microservices/GraphQL; one database. The interest-scoring model is a transparent
hackathon heuristic (`new_score = min(1, old + event_weight)`) and must be labelled as such.

## Your ownership

You own (edit freely):
- `backend/app/db/**` (base, session, models, repositories, migrations)
- `backend/app/ambient/**` (orchestrator, context, memory, personalization)
- `backend/app/impiricus/**` (MockIONService, signals, interfaces)
- `backend/app/api/**`, `backend/app/main.py`, `backend/app/dependencies.py`, `backend/app/errors.py`,
  `backend/app/observability.py`
- `data/seed/hcps.json`, `data/seed/history.json`, `backend/app/ingestion/seed.py` (with B)
- `docker-compose.yml`, `Makefile`, `backend/Dockerfile`
- Tests: `test_health.py`, `test_memory.py`, `test_signals.py`, `test_orchestrator.py`, `tests/fakes.py`

Owned by others: `backend/app/ai/**` + `ingestion/` parsing/chunking (B), `backend/app/voice/**` (D),
`frontend/**` (A). B may propose changes to your Protocols and `ambient/context.py` — review them.

Shared contracts you are the **steward** of: `backend/app/schemas/**` ↔ `frontend/lib/types.ts`,
`docs/API.md`, `backend/app/db/repositories/interfaces.py`, `backend/app/config.py` + `.env.example`.

## Read these first (in order)

1. `README.md`, `docs/ARCHITECTURE.md`, `docs/DATABASE.md`, `docs/API.md`, `docs/TEAM_OWNERSHIP.md`
2. `backend/app/db/models/*`, `db/migrations/versions/0001_*.py`, `0002_*.py`
3. `backend/app/db/repositories/interfaces.py` then each `Sql*Repository`
4. `backend/app/ambient/orchestrator.py`, `memory.py`, `context.py`, `personalization.py`
5. `backend/app/impiricus/mock_ion.py`, `signals.py`
6. `backend/app/dependencies.py`, `main.py` (lifespan, error handlers), `observability.py`
7. `backend/tests/fakes.py`, `conftest.py`, `test_orchestrator.py`

## Current state (already working)

- SQLAlchemy 2 async + asyncpg; `ServiceContainer` built in the FastAPI lifespan (no module globals);
  request-scoped `AsyncSession` via `session_scope` (commit on success, rollback on error).
- `DATABASE_URL` normalization: `postgres://…?sslmode=require` (Tiger Data style) → asyncpg URL +
  `connect_args={"ssl": "require"}`.
- Migration 0001: `vector` extension (required), `timescaledb` (optional, in a DO/EXCEPTION block),
  all tables, HNSW `vector_cosine_ops` index, `interaction_event` PK `(id, timestamp)` +
  `create_hypertable(... chunk_time_interval => 7 days)` only when Timescale exists.
  Migration 0002: `hcp_topic_engagement_daily` continuous aggregate (`WITH NO DATA`) + refresh policy,
  skipped on plain Postgres. Both verified on `timescale/timescaledb-ha:pg17` (Timescale 2.x, pgvector 0.8).
- Repositories return Pydantic schemas (never ORM rows). `InteractionRepository` also serves memory
  queries: `recent`, `last_with_entity(event_types=…)`, `viewed_resource_ids`, `top_entities`,
  `engagement_over_time` (`time_bucket` when Timescale, else `date_trunc`).
- "Since I last looked" = last event of type `REVIEW_EVENT_TYPES` = {RESOURCE_VIEW, SOURCE_OPEN,
  RESOURCE_SAVED} touching the product. Asking a question does not count as looking.
- Signals: `EVENT_WEIGHTS` in `impiricus/signals.py`; signals are stored in `interaction_event.metadata.signals`
  and returned in `AmbientResponse.signals_generated`.
- Normalized errors (`AppError` + handlers for SQLAlchemy/OSError/validation/unhandled);
  `/api/health` never fails and reports DB/timescale/pgvector/AI/voice modes.
- Local DB runs on **port 5433** (the host may already have Postgres on 5432). Compose project name
  `impiricus-ambient`.

## Setup & run

```bash
make setup && make db-up migrate seed
make backend-test          # 38 unit tests on in-memory fakes, no DB needed
make backend               # :8000, OpenAPI at /docs
docker compose exec db psql -U ambient -d ambient   # poke around
```

## Tasks (in priority order — stop for review after each)

### P1 — Tiger Data for real
1. **Cloud deployment.** Point `DATABASE_URL` at a Tiger Data service (the team will provide the URL —
   never commit it), run `make migrate seed`, and verify: `timescaledb_information.hypertables` lists
   `interaction_event`; `timescaledb_information.continuous_aggregates` lists
   `hcp_topic_engagement_daily`; `pg_extension` has `vector`; `/api/health` shows `timescaledb: true,
   pgvector: true`. Fix anything that differs from local (privileges for `CREATE EXTENSION`, SSL, pool
   size, `statement_timeout`). Document exact steps in `docs/DATABASE.md`.
2. **Integration test suite.** Add `backend/tests/integration/` marked `@pytest.mark.integration`
   (skipped unless `TEST_DATABASE_URL` is set) that migrates a throwaway database, seeds it, and runs the
   demo script through the real `Sql*` repositories + mock AI: WHATS_NEW finds PI v2 + Trial A LTFU;
   follow-up resolves Novara; SOURCE_OPEN changes the next WHATS_NEW; signals update `hcp_interest`.
   Add `make backend-itest`. Keep `make backend-test` DB-free.

### P2 — Make the time-series story demonstrable
3. **Continuous aggregate for reads** (`TODO(database)` in `interaction_repository.py`,
   `0002_*.py`). Gotcha: on current Timescale versions new caggs default to
   `materialized_only = true`, and ours is created `WITH NO DATA`, so recent demo events won't appear
   until a refresh. Add migration **0003** that sets `ALTER MATERIALIZED VIEW hcp_topic_engagement_daily
   SET (timescaledb.materialized_only = false)` (real-time aggregation) and calls
   `refresh_continuous_aggregate` once; then make `engagement_over_time(bucket="1 day")` read the cagg
   when Timescale is present and fall back to the raw query otherwise. Never edit merged migrations.
4. **More time-series endpoints** (document in `docs/API.md` first): e.g. `GET /api/intelligence/{hcp_id}/activity?since=…`
   (activity since a timestamp) and cross-HCP `GET /api/intelligence/topics/trending?window=7 days`
   (most-queried entities across synthetic HCPs). These give the Intelligence page Timescale-powered
   content.
5. Optional, only if time allows: compression policy on `interaction_event` (`add_compression_policy`,
   `segmentby = hcp_id`) — explain in docs why it matters at scale.

### P3 — Conversation state, memory, personalization
6. **Session lifecycle:** a session idle > 30 min (configurable in `Settings`) should not be resumed —
   the orchestrator starts a new one and returns the new `session_id` (frontend already adopts whatever
   `session_id` comes back). Add `GET /api/hcps/{hcp_id}/sessions` (recent sessions with turn counts).
7. **"What did I look at last time?"** currently excludes the current session. Make it precise: return
   the HCP's **previous session's** reviews/questions (fall back to recent history if there was none),
   via a new `MemoryService` method with unit tests on the fakes.
8. **Interest decay** (`TODO(database)` in `impiricus/signals.py`): apply exponential decay on read or on
   write (e.g. half-life 30 days based on `last_interaction_at`) so stale interests fade. Keep it
   deterministic, in config, clearly labelled as a heuristic; update `test_signals.py`.
9. **Resource saves:** `POST /api/ambient/events` with `RESOURCE_SAVED` already works (+0.15). Add
   `GET /api/hcps/{hcp_id}/saved` and tell A so a "Save" button can be added to evidence cards.
10. **MockIONService** (`impiricus/`): keep the `IONService` Protocol as the seam to "real Impiricus".
    Add a short section in `docs/ARCHITECTURE.md` describing what a production integration would
    replace (context enrichment, signal ingestion, recommendations) — without claiming real algorithms.

### P4 — Hardening
11. Vector search with filters: with HNSW + `WHERE product = …` pgvector can return fewer than `LIMIT`
    rows on larger corpora. Since pgvector 0.8 you can `SET LOCAL hnsw.iterative_scan = relaxed_order`
    inside the search transaction; add it (guarded by capability detection) and an `EXPLAIN ANALYZE`
    note in `docs/DATABASE.md`.
12. Observability: ensure every request logs `request_id`, `session_id`, and per-stage latencies; add a
    `GET /api/debug/latency` (dev only, `APP_ENV=development`) that returns the last N `timings_ms` for a
    demo latency panel. Never log secrets or audio.
13. Error paths: add tests for `INVALID_SESSION` (session of another HCP), `INVALID_HCP`, DB down
    (503 `DATABASE_UNAVAILABLE`), and the `VALIDATION_ERROR` shape.
14. Docker: verify `docker compose --profile app up --build` works end-to-end (backend container runs
    migrations on start; seeding uses `DATA_DIR=/data`). Fix and document.

## Gotchas

- **Composite PK on the hypertable:** any unique index on `interaction_event` must include `timestamp`.
- **Timestamps:** events/turns get explicit Python `datetime.now(UTC)` values because `now()` is constant
  within a transaction — two turns inserted in one request would otherwise tie.
- **One `AsyncSession` per request is not concurrency-safe** — don't `asyncio.gather` repository calls.
- Every new repository method needs: Protocol in `interfaces.py`, SQL implementation, **and** an
  in-memory implementation in `tests/fakes.py` (the unit tests use fakes).
- `metadata` is a reserved attribute in SQLAlchemy declarative models — columns are mapped as
  `metadata_ = mapped_column("metadata", …)`.
- Changing `GEMINI_EMBEDDING_DIMENSION` requires a migration altering `resource_chunk.embedding` + the HNSW
  index, then a re-seed.
- `make seed` truncates and reloads with deterministic UUIDs — it's also the "reset demo" button.

## Contract changes

You are the gatekeeper. Any API-visible change: write it under "Proposed" in `docs/API.md`, announce it,
then land backend schema + `frontend/lib/types.ts` + `frontend/lib/mockApi.ts` (coordinate with A)
together. Protocol changes: update `interfaces.py`, SQL impl, and `tests/fakes.py` in one PR.

## Definition of done

- `make backend-test` green without a DB; `make backend-itest` green against a real Timescale DB.
- Works against **Tiger Data cloud** via `DATABASE_URL` and against local compose; `/api/health` accurate.
- `docs/DATABASE.md` and `docs/API.md` reflect every change; sample SQL there actually runs.
- The demo in `docs/DEMO_FLOW.md` works, and the Intelligence page shows fresh engagement buckets
  immediately after a query.
- Small commits on `feature/tigerdata`.

When you finish each priority, report: files changed, migrations added, how you verified (commands,
psql output), contract changes announced, and remaining `TODO(database)` items.

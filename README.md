# Impiricus Ambient

> **Hackathon prototype** (GTHacks 13, team Dinobox). Synthetic HCPs and **fictional** products only. Not a
> medical device, not a diagnostic or prescribing tool, not patient-facing.

Impiricus Ambient is a **voice-native, context-aware assistant for healthcare professionals (HCPs)**, built on
top of Impiricus's physician intelligence. An HCP asks a question out loud. Ambient knows who they are and
what they reviewed before, retrieves **approved** resources, tells them **what changed since they last
looked**, answers with cited evidence, speaks the answer, and turns the interaction into structured
engagement signals.

```
HCP question → intent → HCP context → trusted retrieval → grounded answer → (speech)
             → record interaction → update interest signals → better personalization next time
```

## Architecture

```mermaid
flowchart LR
    Mic[Voice / text] --> STT[ElevenLabs STT]
    STT --> Orch[AmbientOrchestrator]
    Orch --> Intent[Gemini intent<br/>structured JSON]
    Orch --> Mem[Structured memory]
    Orch --> Ret[pgvector retrieval<br/>+ personalized re-rank]
    Orch --> Gen[Gemini grounded answer<br/>+ evidence IDs]
    Gen --> TTS[ElevenLabs TTS]
    Orch --> Sig[Engagement signals]
    Mem & Ret & Sig <--> TD[(Tiger Data<br/>Postgres · Timescale · pgvector)]
    TD --> Intel[Intelligence view]
```

More in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), including why a single Tiger Data store covers
relational, time-series and vector data.

## Tech stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 16 (App Router), React 19, strict TypeScript, Tailwind v4, shadcn/ui-style components, Framer Motion, Recharts |
| Backend | Python 3.12, FastAPI, Pydantic v2, SQLAlchemy 2 (async, asyncpg), Alembic |
| Data | Tiger Data / TimescaleDB (hypertable + continuous aggregate) + pgvector (HNSW) |
| AI | Google Gemini (`GEMINI_MODEL`, `GEMINI_EMBEDDING_MODEL`) via `google-genai`, structured output |
| Voice | ElevenLabs TTS + STT (REST), browser `MediaRecorder` push-to-talk |

## Quick start (mock mode, no API keys)

Prerequisites: Python 3.12+, Node 20+, Docker.

```bash
make setup      # .env files, backend venv, npm install
make db-up      # Timescale + pgvector on localhost:5433
make migrate    # alembic upgrade head
make seed       # synthetic HCPs, fictional resources (+ embeddings), demo history
make backend    # http://localhost:8000  (OpenAPI docs at /docs)
make frontend   # http://localhost:3000  (separate terminal)
```

Open `http://localhost:3000/ambient`, keep **Dr. Maya Morgan** selected, and type or say
*"What's changed with Novara since I last looked at it?"*. Then open `/intelligence`.

### Running pieces individually

| Task | Command |
|---|---|
| Database up / down / wipe | `make db-up` · `make db-down` · `make db-reset` |
| Migrations | `make migrate` (or `cd backend && .venv/bin/alembic upgrade head`) |
| Seed / reset demo state | `make seed` (truncates and reloads; IDs are deterministic) |
| Backend | `make backend` (or `cd backend && .venv/bin/uvicorn app.main:app --reload`) |
| Frontend | `make frontend` (or `cd frontend && npm run dev`) |
| Everything in Docker | `docker compose --profile app up --build` |
| Tiger Data cloud | set `DATABASE_URL` in `.env` to your service URL, then `make migrate seed` |

## Mock mode vs real providers

The project **runs without paid API keys**. Each provider falls back to a mock when its flag is on **or**
its key is missing:

| Env | Mock behavior |
|---|---|
| `USE_MOCK_AI=true` | Keyword intent classifier, hashed embeddings (real pgvector search), template answers built only from retrieved evidence, section-level diff |
| `USE_MOCK_VOICE=true` | STT returns `MOCK_STT_TEXT`; TTS returns silent placeholder audio |
| `NEXT_PUBLIC_USE_MOCK_API=true` (frontend/.env.local) | Frontend runs on in-browser fixtures with no backend at all |

To go real, set `GOOGLE_API_KEY` + `USE_MOCK_AI=false` and/or `ELEVENLABS_API_KEY` + `ELEVENLABS_VOICE_ID`
+ `USE_MOCK_VOICE=false`. **Run `make seed` again after changing `USE_MOCK_AI`**, because mock and Gemini
embeddings are not compatible. `GET /api/health` shows which modes are active.

## Environment variables

All backend config is in `backend/app/config.py` (Pydantic Settings, reads the repo-root `.env`). The
frontend reads only `NEXT_PUBLIC_*` via `frontend/lib/env.ts`. See [`.env.example`](.env.example):

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://ambient:ambient@localhost:5433/ambient` | Tiger Data / local Timescale. `postgres://…?sslmode=require` is accepted |
| `GOOGLE_API_KEY` | — | Gemini |
| `GEMINI_MODEL` / `GEMINI_EMBEDDING_MODEL` | `gemini-3.8-flash` / `gemini-embedding-2` | Model IDs (never hardcoded elsewhere) |
| `GEMINI_EMBEDDING_DIMENSION` | `768` | pgvector column size ([docs/DATABASE.md](docs/DATABASE.md)) |
| `ELEVENLABS_API_KEY` / `ELEVENLABS_VOICE_ID` | — | Voice |
| `ELEVENLABS_TTS_MODEL` / `ELEVENLABS_STT_MODEL` | `eleven_flash_v2_5` / `scribe_v1` | Voice models |
| `USE_MOCK_AI` / `USE_MOCK_VOICE` | `true` | Mock-first switches |
| `MOCK_STT_TEXT` | demo question | What the mock "hears" |
| `INTEREST_HALF_LIFE_DAYS` | `90` | Interest-score decay half-life (`0` = off) |
| `FRONTEND_URL` / `BACKEND_URL` | `:3000` / `:8000` | CORS + links |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | Frontend → backend |
| `NEXT_PUBLIC_USE_MOCK_API` | `false` | Frontend-only fixtures |

## Tests

```bash
make test           # everything below
make backend-test   # pytest unit tests, no DB or API keys needed (in-memory fakes built from data/seed)
make backend-itest  # integration tests against a real Timescale + pgvector DB (recreates ambient_test)
make frontend-check # eslint + tsc --noEmit + vitest
```

Backend tests cover the health endpoint and error normalization, intent parsing (Gemini JSON → Pydantic,
mock classifier on every demo query), memory lookups, signal scoring, retrieval ranking and filters, and the
`AmbientOrchestrator` end to end with mocked dependencies.

## Major API endpoints

`GET /api/health` · `GET /api/hcps` · `GET /api/hcps/{id}` · `GET /api/hcps/{id}/timeline` ·
`GET /api/hcps/{id}/interests` · `GET /api/resources` · `GET /api/resources/{id}` · `POST /api/sessions` ·
`GET /api/sessions/{id}` · **`POST /api/ambient/query`** · `POST /api/ambient/events` ·
`POST /api/audio/transcribe` · `POST /api/audio/synthesize` · `GET /api/intelligence/{id}/signals` ·
`GET /api/intelligence/{id}/recommendations` · `GET /api/intelligence/{id}/engagement`

Full contracts, error codes and examples are in [docs/API.md](docs/API.md).

## Repository layout

```
├── backend/app
│   ├── api/            thin FastAPI routers
│   ├── ambient/        orchestrator, context resolution, structured memory, personalization
│   ├── ai/             Gemini client, intent, embeddings, retrieval, generation, semantic diff, prompts
│   ├── voice/          STT/TTS Protocols + ElevenLabs + mock
│   ├── impiricus/      MockIONService + signal scoring
│   ├── db/             models, repositories (Protocols + SQL), Alembic migrations
│   ├── ingestion/      parse → chunk → embed, seed CLI
│   └── schemas/        Pydantic contracts (mirrored in frontend/lib/types.ts)
├── frontend/           Next.js: app/ (ambient, intelligence), components/, hooks/, lib/
├── data/seed/          synthetic HCPs, fictional resources, demo history
└── docs/               ARCHITECTURE · API · DATABASE · TEAM_OWNERSHIP · DEMO_FLOW
```

## Team ownership

Four parallel workstreams: **Frontend** (`TODO(frontend)`), **AI/RAG** (`TODO(ai-rag)`, `TODO(diff)`),
**Backend/DB** (`TODO(database)`), **Voice** (`TODO(voice)`). Directory ownership, the interfaces each
person implements, and branch conventions are in [docs/TEAM_OWNERSHIP.md](docs/TEAM_OWNERSHIP.md).

## Demo

The 2–3 minute script is in [docs/DEMO_FLOW.md](docs/DEMO_FLOW.md): Dr. Morgan → *"What's changed with
Novara since I last looked at it?"* → evidence + diff + speech → *"What about renal impairment?"* → Intelligence
view shows the new signals.

## Security & privacy

- **No real patient data.** No PHI of any kind.
- **No real HCP personal data.** All profiles are synthetic ([data/synthetic/README.md](data/synthetic/README.md)).
- **Fictional products** (Novara, Cardexa, Lumetrex) with obvious placeholder content, so nothing can be
  mistaken for guidance about a real medicine.
- **No medical diagnosis, no autonomous treatment recommendations.** Answers are limited to retrieved
  approved-resource evidence and say so when evidence is insufficient.
- **No credentials committed.** `.env` is git-ignored and secrets are `SecretStr`. Logs never include keys
  or audio.
- The engagement scoring is a transparent hackathon heuristic and **does not represent real Impiricus
  algorithms**.

# Impiricus Ambient — developer shortcuts (hackathon prototype)
PYTHON ?= python3.12
VENV := backend/.venv
PY := $(abspath $(VENV))/bin/python

.PHONY: help setup backend-install frontend-install env db-up db-down db-reset migrate seed \
        backend frontend test backend-test backend-itest db-verify frontend-check lint

help:
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

setup: env backend-install frontend-install ## Install everything (backend venv + frontend node_modules)

env: ## Create .env and frontend/.env.local from examples if missing
	@test -f .env || cp .env.example .env
	@test -f frontend/.env.local || grep '^NEXT_PUBLIC_' .env.example > frontend/.env.local
	@echo "env files ready"

backend-install: ## Create backend virtualenv and install deps
	$(PYTHON) -m venv $(VENV)
	$(PY) -m pip install --upgrade pip
	$(PY) -m pip install -e "backend[dev]"

frontend-install: ## Install frontend deps
	cd frontend && npm install

db-up: ## Start local Timescale + pgvector database (port 5433)
	docker compose up -d db
	@echo "waiting for database..."
	@until docker compose exec -T db pg_isready -U ambient -d ambient >/dev/null 2>&1; do sleep 1; done
	@echo "database ready"

db-down: ## Stop local database
	docker compose down

db-reset: ## Destroy local database volume
	docker compose down -v

migrate: ## Run Alembic migrations against DATABASE_URL
	cd backend && $(PY) -m alembic upgrade head

db-verify: ## Check extensions, hypertable, continuous aggregate, jobs and row counts on DATABASE_URL
	cd backend && $(PY) -m app.db.verify

seed: ## Load synthetic HCPs, resources (with embeddings) and history
	cd backend && $(PY) -m app.ingestion.seed --reset

backend: ## Run FastAPI dev server on :8000
	cd backend && $(PY) -m uvicorn app.main:app --reload --port 8000

frontend: ## Run Next.js dev server on :3000
	cd frontend && npm run dev

test: backend-test frontend-check ## Run all tests and checks

backend-test: ## Run backend unit tests (no DB or API keys required)
	cd backend && $(PY) -m pytest -m "not integration"

# Integration tests migrate + seed a throwaway schema (itest_<random>) in this database and drop it
# afterwards, so pointing at the demo DB or a Tiger Data service is safe.
TEST_DATABASE_URL ?= postgresql+asyncpg://ambient:ambient@localhost:5433/ambient
backend-itest: ## Run integration tests against a real DB (TEST_DATABASE_URL, default local compose)
	cd backend && TEST_DATABASE_URL='$(TEST_DATABASE_URL)' $(PY) -m pytest -m integration tests/integration -v

frontend-check: ## Lint, typecheck and unit-test the frontend
	cd frontend && npm run lint && npm run typecheck && npm run test

lint: ## Lint backend (ruff) and frontend (eslint)
	cd backend && $(PY) -m ruff check app tests
	cd frontend && npm run lint

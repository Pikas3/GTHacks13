"""HTTP-level smoke test of the demo against a real database."""

import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.session import create_engine
from app.ingestion.seed import seed_database, stable_id
from app.main import create_app
from tests.integration.conftest import _settings

pytestmark = pytest.mark.integration

MORGAN = str(stable_id("hcp", "SYN-HCP-001"))


def _seed(url: str) -> None:
    async def go() -> None:
        engine: AsyncEngine = create_engine(_settings(url))
        try:
            await seed_database(engine, _settings(url), reset=True)
        finally:
            await engine.dispose()

    asyncio.run(go())


def test_demo_over_http(database_url: str) -> None:
    _seed(database_url)
    with TestClient(create_app(_settings(database_url))) as client:
        health = client.get("/api/health").json()
        assert health["database"] == "ok" and health["pgvector"]

        r = client.post(
            "/api/ambient/query",
            json={
                "hcp_id": MORGAN,
                "query": "What's changed with Novara since I last looked at it?",
                "input_mode": "voice",
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["intent"] == "WHATS_NEW" and len(body["evidence"]) == 2

        follow = client.post(
            "/api/ambient/query",
            json={"hcp_id": MORGAN, "session_id": body["session_id"], "query": "What about renal impairment?"},
        ).json()
        assert follow["context"]["active_entity"] == "Novara"

        engagement = client.get(f"/api/intelligence/{MORGAN}/engagement").json()
        assert any(p["topic"] == "renal impairment" for p in engagement["points"])

        activity = client.get(f"/api/intelligence/{MORGAN}/activity").json()
        assert activity["by_type"].get("VOICE_QUERY") == 1 and activity["by_type"].get("TEXT_QUERY") == 1

        trending = client.get("/api/intelligence/topics/trending", params={"window": "1 day"}).json()
        assert trending["window"] == "1 day" and trending["topics"]

        bad = client.get("/api/intelligence/topics/trending", params={"window": "2 years"})
        assert bad.status_code == 422 and bad.json()["error"]["code"] == "VALIDATION_ERROR"

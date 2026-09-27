"""HTTP-level smoke test of the demo against a real database."""

import pytest
from fastapi.testclient import TestClient

from app.ingestion.seed import stable_id

pytestmark = pytest.mark.integration

MORGAN = str(stable_id("hcp", "SYN-HCP-001"))


def test_demo_over_http(client: TestClient) -> None:
    health = client.get("/api/health").json()
    assert health["database"] == "ok" and health["pgvector"]

    r = client.post(
        "/api/lepius/query",
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
        "/api/lepius/query",
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

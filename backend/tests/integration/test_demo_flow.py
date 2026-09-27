"""The docs/DEMO_FLOW.md script against the real Sql* repositories, migrations and mock AI."""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from tests.integration.conftest import MORGAN_ID, query

WHATS_NEW_Q = "What's changed with Novara since I last looked at it?"


def ask(client: TestClient, q: str, session_id: str | None = None, mode: str = "voice") -> dict:
    resp = client.post(
        "/api/lepius/query",
        json={"hcp_id": str(MORGAN_ID), "session_id": session_id, "query": q, "input_mode": mode},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def interests(client: TestClient) -> dict[str, float]:
    return {i["entity"]: i["score"] for i in client.get(f"/api/hcps/{MORGAN_ID}/interests").json()}


def test_health_reports_real_capabilities(client: TestClient, seeded: Settings) -> None:
    body = client.get("/api/health").json()
    assert body["database"] == "ok"
    assert body["pgvector"] is True
    has_ts = bool(asyncio.run(query(seeded, "SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'")))
    assert body["timescaledb"] is has_ts


def test_timescale_objects_exist(seeded: Settings) -> None:
    if not asyncio.run(query(seeded, "SELECT 1 FROM pg_extension WHERE extname = 'timescaledb'")):
        pytest.skip("plain PostgreSQL: no hypertable / continuous aggregate")
    schema = seeded.db_search_path
    hts = asyncio.run(
        query(
            seeded,
            "SELECT hypertable_name FROM timescaledb_information.hypertables WHERE hypertable_schema = :s",
            s=schema,
        )
    )
    assert ("interaction_event",) in hts
    caggs = asyncio.run(
        query(
            seeded,
            "SELECT view_name FROM timescaledb_information.continuous_aggregates WHERE view_schema = :s",
            s=schema,
        )
    )
    assert ("hcp_topic_engagement_daily",) in caggs


def test_whats_new_finds_pi_v2_and_ltfu(client: TestClient) -> None:
    body = ask(client, WHATS_NEW_Q)
    assert body["intent"] == "WHATS_NEW"
    assert "July 2, 2026" in body["response"]["text"]
    found = {(e["title"], e["version"]) for e in body["evidence"]}
    assert ("Novara Prescribing Information", "2.0") in found
    assert ("Novara Trial A Long-Term Follow-Up", "1.0") in found
    assert all(e["is_new"] for e in body["evidence"])
    [diff] = body["changes"]
    assert any(c["topic"] == "Renal Impairment" for c in diff["changes"])


def test_follow_up_resolves_novara_from_session(client: TestClient) -> None:
    first = ask(client, WHATS_NEW_Q)
    follow = ask(client, "What about renal impairment?", first["session_id"])
    assert follow["session_id"] == first["session_id"]
    assert follow["intent"] == "FOLLOW_UP"
    assert follow["context"]["active_entity"] == "Novara"
    assert follow["resolved_query"].startswith("Novara")
    assert follow["evidence"] and follow["evidence"][0]["section"] == "Renal Impairment"
    turns = client.get(f"/api/sessions/{first['session_id']}").json()["turns"]
    assert len(turns) == 4


def test_asking_is_not_looking_but_source_open_is(client: TestClient) -> None:
    first = ask(client, WHATS_NEW_Q)
    again = ask(client, WHATS_NEW_Q, first["session_id"])
    assert {e["resource_id"] for e in again["evidence"]} == {e["resource_id"] for e in first["evidence"]}

    pi_v2 = next(e for e in first["evidence"] if e["version"] == "2.0")
    opened = client.post(
        "/api/lepius/events",
        json={
            "hcp_id": str(MORGAN_ID),
            "session_id": first["session_id"],
            "event_type": "SOURCE_OPEN",
            "resource_id": pi_v2["resource_id"],
        },
    )
    assert opened.status_code == 200, opened.text

    after = ask(client, WHATS_NEW_Q, first["session_id"])
    assert "July 2, 2026" not in after["response"]["text"]
    assert after["evidence"] == []  # nothing published since the review we just recorded


def test_signals_update_hcp_interest(client: TestClient) -> None:
    before = interests(client)
    body = ask(client, "What about renal impairment in Novara?")
    after_query = interests(client)
    novara = next(s for s in body["signals_generated"] if s["entity"] == "Novara")
    assert novara["weight"] == 0.08
    assert after_query["Novara"] == pytest.approx(min(1.0, before["Novara"] + 0.08))
    assert after_query["Novara"] == pytest.approx(novara["new_score"])

    ev = client.post(
        "/api/lepius/events",
        json={"hcp_id": str(MORGAN_ID), "event_type": "SOURCE_OPEN", "entity": "Novara"},
    ).json()
    assert ev["signals_generated"][0]["weight"] == 0.10
    assert interests(client)["Novara"] == pytest.approx(min(1.0, after_query["Novara"] + 0.10))

    feed = client.get(f"/api/intelligence/{MORGAN_ID}/signals").json()["signals"]
    assert feed[0]["event_type"] == "SOURCE_OPEN"


def test_recall_history_from_structured_memory(client: TestClient) -> None:
    body = ask(client, "What did I look at last time?")
    assert body["intent"] == "RECALL_HISTORY"
    assert body["history"][0]["label"].startswith("Viewed Novara Access Guide")


def test_engagement_includes_todays_events(client: TestClient) -> None:
    ask(client, WHATS_NEW_Q)
    body = client.get(f"/api/intelligence/{MORGAN_ID}/engagement", params={"bucket": "1 day"}).json()
    buckets = {p["bucket"][:10] for p in body["points"]}
    assert "2026-07-02" in buckets
    assert any(p["topic"] == "Novara" for p in body["points"] if p["bucket"][:10] not in {"2026-06-14", "2026-07-02"})

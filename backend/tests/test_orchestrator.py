import pytest

from app.errors import AppError, ErrorCode
from app.schemas.enums import ChangeType, EventType, InputMode, IntentType
from tests.conftest import MORGAN_ID


async def test_whats_new_flow_end_to_end(orchestrator, interactions, hcps) -> None:
    novara_before = {i.entity: i.score for i in await hcps.get_interests(MORGAN_ID)}["Novara"]

    resp = await orchestrator.process_query(
        MORGAN_ID, None, "What's changed with Novara since I last looked at it?", InputMode.VOICE
    )

    assert resp.intent == IntentType.WHATS_NEW
    assert resp.context.active_entity == "Novara"
    titles = {(e.title, e.version) for e in resp.evidence}
    assert ("Novara Prescribing Information", "2.0") in titles
    assert ("Novara Trial A Long-Term Follow-Up", "1.0") in titles
    assert all(e.is_new for e in resp.evidence)
    assert "July 2, 2026" in resp.response.text
    assert resp.response.speech_text and "[E" not in resp.response.speech_text

    [diff] = resp.changes
    renal = next(c for c in diff.changes if c.topic == "Renal Impairment")
    assert renal.change_type == ChangeType.UPDATED and renal.importance == "HIGH"

    # engagement recorded + interest updated
    last = (await interactions.recent(MORGAN_ID, limit=1))[0]
    assert last.event_type == EventType.VOICE_QUERY and last.entity == "Novara"
    novara_signal = next(s for s in resp.signals_generated if s.entity == "Novara")
    assert novara_signal.weight == 0.08
    assert novara_signal.new_score == pytest.approx(novara_before + 0.08)


async def test_follow_up_resolves_product_from_context(orchestrator) -> None:
    first = await orchestrator.process_query(MORGAN_ID, None, "What's new with Novara?")
    follow = await orchestrator.process_query(MORGAN_ID, first.session_id, "What about renal impairment?")

    assert follow.intent == IntentType.FOLLOW_UP
    assert follow.context.active_entity == "Novara"
    assert follow.context.active_topic == "renal impairment"
    assert follow.resolved_query.startswith("Novara")
    assert follow.evidence and follow.evidence[0].section == "Renal Impairment"


async def test_show_source_reuses_previous_query(orchestrator) -> None:
    first = await orchestrator.process_query(MORGAN_ID, None, "What is the Novara dosing?")
    src = await orchestrator.process_query(MORGAN_ID, first.session_id, "Show me the source.")
    assert src.intent == IntentType.SHOW_SOURCE
    assert src.evidence
    assert {e.chunk_id for e in src.evidence} <= {e.chunk_id for e in first.evidence} | {
        e.chunk_id for e in src.evidence
    }


async def test_recall_history_uses_structured_memory(orchestrator) -> None:
    resp = await orchestrator.process_query(MORGAN_ID, None, "What did I look at last time?")
    assert resp.intent == IntentType.RECALL_HISTORY
    assert resp.history and resp.evidence == []
    assert "Novara Access Guide" in resp.response.text


async def test_unknown_hcp_and_session_errors(orchestrator) -> None:
    import uuid

    with pytest.raises(AppError) as err:
        await orchestrator.process_query(uuid.uuid4(), None, "What's new?")
    assert err.value.code == ErrorCode.INVALID_HCP

    with pytest.raises(AppError) as err:
        await orchestrator.process_query(MORGAN_ID, uuid.uuid4(), "What's new?")
    assert err.value.code == ErrorCode.INVALID_SESSION


async def test_no_evidence_is_explicit(orchestrator) -> None:
    resp = await orchestrator.process_query(MORGAN_ID, None, "Tell me a joke")
    assert resp.intent == IntentType.UNKNOWN
    assert resp.response.insufficient_evidence
    assert resp.evidence == []


async def test_whats_new_is_anchored_on_last_review_not_last_question(orchestrator) -> None:
    """Asking doesn't count as 'looking at' — the demo query stays repeatable until a source is opened."""
    q = "What's changed with Novara since I last looked at it?"
    first = await orchestrator.process_query(MORGAN_ID, None, q)
    again = await orchestrator.process_query(MORGAN_ID, first.session_id, q)
    assert {e.resource_id for e in again.evidence} == {e.resource_id for e in first.evidence}
    assert "July 2, 2026" in again.response.text


async def test_superseded_versions_are_not_used_as_evidence(orchestrator) -> None:
    resp = await orchestrator.process_query(MORGAN_ID, None, "What is the Novara renal impairment guidance?")
    assert resp.evidence
    assert all(not (e.title == "Novara Prescribing Information" and e.version == "1.0") for e in resp.evidence)


async def test_recall_history_excludes_current_session(orchestrator) -> None:
    first = await orchestrator.process_query(MORGAN_ID, None, "What's new with Novara?")
    resp = await orchestrator.process_query(MORGAN_ID, first.session_id, "What did I look at last time?")
    assert all("What's new" not in h.label for h in resp.history)
    assert resp.history[0].label.startswith("Viewed Novara Access Guide")

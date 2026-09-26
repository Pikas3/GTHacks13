from datetime import UTC, datetime
from uuid import uuid4

from app.impiricus.signals import EVENT_WEIGHTS, build_signals, next_score
from app.schemas.enums import EntityType, EventType, IntentType
from app.schemas.intent import ExtractedEntity


def test_next_score_adds_weight_and_caps_at_one() -> None:
    assert next_score(0.5, 0.08) == 0.58
    assert next_score(0.97, 0.15) == 1.0
    assert next_score(0.0, -0.2) == 0.0


def test_event_weights_follow_documented_ordering() -> None:
    w = EVENT_WEIGHTS
    assert w[EventType.TEXT_QUERY] < w[EventType.VOICE_QUERY] < w[EventType.SOURCE_OPEN] < w[EventType.RESOURCE_SAVED]


def test_build_signals_one_per_entity_plus_topic() -> None:
    signals = build_signals(
        hcp_id=uuid4(),
        event_type=EventType.VOICE_QUERY,
        entities=[
            ExtractedEntity(name="Novara", type=EntityType.PRODUCT),
            ExtractedEntity(name="renal impairment", type=EntityType.POPULATION),
        ],
        topic="renal impairment",
        intent=IntentType.FOLLOW_UP,
        at=datetime.now(UTC),
    )
    assert [s.entity for s in signals] == ["Novara", "renal impairment"]
    assert all(s.weight == 0.08 for s in signals)


def test_zero_weight_events_generate_no_signals() -> None:
    assert (
        build_signals(
            hcp_id=uuid4(),
            event_type=EventType.SESSION_STARTED,
            entities=[],
            topic="x",
            intent=None,
            at=datetime.now(UTC),
        )
        == []
    )


async def test_record_signal_updates_interest(ion, hcps) -> None:
    from tests.conftest import MORGAN_ID

    before = {i.entity: i.score for i in await hcps.get_interests(MORGAN_ID)}["dosing"]
    [signal] = build_signals(
        hcp_id=MORGAN_ID,
        event_type=EventType.SOURCE_OPEN,
        entities=[],
        topic="dosing",
        intent=None,
        at=datetime.now(UTC),
    )
    recorded = await ion.record_signal(signal)
    assert recorded.new_score == round(before + 0.10, 4)


async def test_recommendations_skip_viewed_and_superseded(ion) -> None:
    from tests.conftest import MORGAN_ID

    recs = await ion.get_recommended_resource(MORGAN_ID, limit=10)
    labels = {(r.resource.title, r.resource.version) for r in recs}
    assert ("Novara Prescribing Information", "2.0") in labels
    assert ("Novara Prescribing Information", "1.0") not in labels  # viewed and superseded
    assert ("Novara Access Guide", "1.0") not in labels  # viewed

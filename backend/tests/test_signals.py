from datetime import UTC, datetime
from uuid import uuid4

from app.impiricus.signals import (
    DEFAULT_HALF_LIFE_DAYS,
    EVENT_WEIGHTS,
    build_signals,
    decay_score,
    effective_interests,
    next_score,
)
from app.schemas.enums import EntityType, EventType, IntentType
from app.schemas.hcp import HCPInterestRead
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


async def test_record_signal_decays_then_adds_weight(ion, hcps) -> None:
    from tests.conftest import MORGAN_ID, NOW

    stored = {i.entity: i for i in await hcps.get_interests(MORGAN_ID)}["dosing"]  # 0.48 on 2026-06-14
    [signal] = build_signals(
        hcp_id=MORGAN_ID, event_type=EventType.SOURCE_OPEN, entities=[], topic="dosing", intent=None, at=NOW
    )
    recorded = await ion.record_signal(signal)
    decayed = decay_score(stored.score, stored.last_interaction_at, NOW, DEFAULT_HALF_LIFE_DAYS)
    assert decayed < stored.score
    assert recorded.new_score == round(decayed + 0.10, 4)
    # Stored as-of now, so reading it back immediately applies no further decay.
    [after] = [i for i in await ion.get_topic_affinities(MORGAN_ID) if i.entity == "dosing"]
    assert after.score == recorded.new_score and after.interaction_count == stored.interaction_count + 1


async def test_recommendations_skip_viewed_and_superseded(ion) -> None:
    from tests.conftest import MORGAN_ID

    recs = await ion.get_recommended_resource(MORGAN_ID, limit=10)
    labels = {(r.resource.title, r.resource.version) for r in recs}
    assert ("Novara Prescribing Information", "2.0") in labels
    assert ("Novara Prescribing Information", "1.0") not in labels  # viewed and superseded
    assert ("Novara Access Guide", "1.0") not in labels  # viewed


def test_decay_score_halves_every_half_life() -> None:
    now = datetime(2026, 9, 26, tzinfo=UTC)
    last = datetime(2026, 6, 28, tzinfo=UTC)  # 90 days earlier
    assert decay_score(0.8, last, now, 90) == 0.4
    assert decay_score(0.8, now, now, 90) == 0.8
    assert decay_score(0.8, None, now, 90) == 0.8  # unknown age: leave as is
    assert decay_score(0.8, last, now, 0) == 0.8  # disabled


def test_effective_interests_reorders_by_decayed_score() -> None:
    now = datetime(2026, 9, 26, tzinfo=UTC)
    stale = HCPInterestRead(
        entity="HER2",
        entity_type=EntityType.BIOMARKER,
        score=0.8,
        interaction_count=9,
        last_interaction_at=datetime(2026, 3, 30, tzinfo=UTC),
    )
    fresh = HCPInterestRead(
        entity="dosing", entity_type=EntityType.TOPIC, score=0.3, interaction_count=1, last_interaction_at=now
    )
    ranked = effective_interests([stale, fresh], now, 90)
    assert [i.entity for i in ranked] == ["dosing", "HER2"]
    assert stale.score == 0.8, "input must not be mutated"

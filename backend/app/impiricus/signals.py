"""Deterministic engagement-signal scoring.

IMPORTANT: this is a transparent hackathon heuristic. It does NOT represent real Impiricus
algorithms. Weights are configuration, not learned values.
"""

from datetime import datetime
from uuid import UUID

from app.schemas.enums import EntityType, EventType, IntentType
from app.schemas.hcp import HCPInterestRead
from app.schemas.intent import ExtractedEntity
from app.schemas.signals import EngagementSignal

EVENT_WEIGHTS: dict[EventType, float] = {
    EventType.TEXT_QUERY: 0.05,
    EventType.VOICE_QUERY: 0.08,
    EventType.FOLLOW_UP: 0.05,
    EventType.RESOURCE_VIEW: 0.06,
    EventType.SOURCE_OPEN: 0.10,
    EventType.RESOURCE_SAVED: 0.15,
    EventType.RESPONSE_GENERATED: 0.0,
    EventType.SESSION_STARTED: 0.0,
}

MAX_SCORE = 1.0
DEFAULT_HALF_LIFE_DAYS = 90.0


def decay_score(score: float, last_interaction_at: datetime | None, now: datetime, half_life_days: float) -> float:
    """Exponential decay: an interest loses half its weight every `half_life_days` without interaction.

    Stored scores are "as of last_interaction_at"; decay is applied when read or updated, so no batch job
    is needed. half_life_days <= 0 disables decay. Hackathon heuristic, not an Impiricus algorithm.
    """
    if half_life_days <= 0 or last_interaction_at is None:
        return score
    age_days = max((now - last_interaction_at).total_seconds() / 86400, 0.0)
    return round(score * 0.5 ** (age_days / half_life_days), 4)


def effective_interests(
    interests: list[HCPInterestRead], now: datetime, half_life_days: float
) -> list[HCPInterestRead]:
    """Interests with decayed scores, highest first."""
    decayed = [
        i.model_copy(update={"score": decay_score(i.score, i.last_interaction_at, now, half_life_days)})
        for i in interests
    ]
    return sorted(decayed, key=lambda i: i.score, reverse=True)


def next_score(old_score: float, weight: float) -> float:
    """new_score = min(1.0, old_score + event_weight), clamped at 0."""
    return round(max(0.0, min(MAX_SCORE, old_score + weight)), 4)


def build_signals(
    *,
    hcp_id: UUID,
    event_type: EventType,
    entities: list[ExtractedEntity],
    topic: str | None,
    intent: IntentType | None,
    at: datetime,
) -> list[EngagementSignal]:
    """One signal per distinct entity touched by the interaction (products and topics)."""
    weight = EVENT_WEIGHTS.get(event_type, 0.0)
    if weight <= 0:
        return []
    seen: set[str] = set()
    signals: list[EngagementSignal] = []
    for e in entities:
        key = e.name.lower()
        if key in seen:
            continue
        seen.add(key)
        signals.append(
            EngagementSignal(
                hcp_id=hcp_id,
                entity=e.name,
                entity_type=e.type,
                topic=topic,
                intent=intent,
                event_type=event_type,
                weight=weight,
                timestamp=at,
            )
        )
    if topic and topic.lower() not in seen:
        signals.append(
            EngagementSignal(
                hcp_id=hcp_id,
                entity=topic,
                entity_type=EntityType.TOPIC,
                topic=topic,
                intent=intent,
                event_type=event_type,
                weight=weight,
                timestamp=at,
            )
        )
    return signals

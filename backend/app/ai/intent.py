"""Intent classification + entity extraction.

`IntentClassifier` is the contract; the orchestrator never knows which implementation it gets.
"""

import re
from typing import Protocol

from app.ai.gemini_client import GeminiClient
from app.ai.prompts import INTENT_PROMPT, INTENT_SYSTEM
from app.ai.vocabulary import ENTITY_ALIASES, PRODUCTS
from app.schemas.conversation import ConversationContext
from app.schemas.enums import EntityType, IntentType, TemporalReference
from app.schemas.intent import ExtractedEntity, IntentResult


class IntentClassifier(Protocol):
    async def classify(
        self, query: str, context: ConversationContext, timings: dict[str, float] | None = None
    ) -> IntentResult: ...


class GeminiIntentClassifier:
    def __init__(self, client: GeminiClient) -> None:
        self.client = client

    async def classify(
        self, query: str, context: ConversationContext, timings: dict[str, float] | None = None
    ) -> IntentResult:
        prompt = INTENT_PROMPT.format(
            active_entity=context.active_entity or "-",
            active_topic=context.active_topic or "-",
            last_intent=context.last_intent or "-",
            query=query,
        )
        # TODO(ai-rag): add few-shot examples and evaluate against tests/fixtures of demo queries.
        return await self.client.generate_structured(
            prompt=prompt,
            schema=IntentResult,
            system_instruction=INTENT_SYSTEM,
            temperature=0.0,
            operation="gemini.intent",
            timings=timings,
        )


_PATTERNS: list[tuple[IntentType, re.Pattern[str]]] = [
    (IntentType.SHOW_SOURCE, re.compile(r"\b(show|open|see)\b.*\b(source|evidence|reference|document)\b|\bsource\b")),
    (
        IntentType.WHATS_NEW,
        re.compile(r"\bwhat'?s new\b|\bwhat is new\b|\bchanged?\b|\bupdates?\b|\bsince i last\b|\blatest\b"),
    ),
    (
        IntentType.RECALL_HISTORY,
        re.compile(r"\bwhat did i\b|\blast time\b|\bpreviously\b|\bmy history\b|\bi looked at\b"),
    ),
    (IntentType.COMPARE, re.compile(r"\bcompare\b|\bversus\b|\bvs\.?\b|\bdifference between\b")),
    (
        IntentType.RESOURCE_SEARCH,
        re.compile(r"\bfind\b|\bis there a (guide|resource|document)\b|\bresources? (on|for|about)\b"),
    ),
    (IntentType.FOLLOW_UP, re.compile(r"^\s*(what|how) about\b|^\s*and\b|^\s*what else\b")),
]


def extract_entities(query: str) -> list[ExtractedEntity]:
    q = query.lower()
    found = [ExtractedEntity(name=p, type=EntityType.PRODUCT) for p in PRODUCTS if p.lower() in q]
    for canonical, (etype, aliases) in ENTITY_ALIASES.items():
        if any(re.search(rf"\b{re.escape(a)}\b", q) for a in aliases):
            found.append(ExtractedEntity(name=canonical, type=etype))
    return found


class MockIntentClassifier:
    """Deterministic keyword classifier for development and tests. No network calls."""

    async def classify(
        self, query: str, context: ConversationContext, timings: dict[str, float] | None = None
    ) -> IntentResult:
        q = query.lower().replace("\u2019", "'").strip()
        entities = extract_entities(q)
        intent = next((i for i, pat in _PATTERNS if pat.search(q)), None)
        if intent is None:
            intent = IntentType.QUESTION_ANSWERING if entities else IntentType.UNKNOWN
        has_product = any(e.type == EntityType.PRODUCT for e in entities)
        if intent == IntentType.QUESTION_ANSWERING and not has_product and context.active_entity:
            intent = IntentType.FOLLOW_UP

        temporal = TemporalReference.NONE
        if intent == IntentType.WHATS_NEW and re.search(r"since|last (time|looked|visit)", q):
            temporal = TemporalReference.LAST_INTERACTION
        elif intent == IntentType.WHATS_NEW:
            temporal = TemporalReference.RECENT

        topic = next((e.name for e in entities if e.type != EntityType.PRODUCT), None)
        return IntentResult(
            intent=intent,
            entities=entities,
            topic=topic,
            temporal_reference=temporal,
            requires_history=intent in {IntentType.WHATS_NEW, IntentType.RECALL_HISTORY},
            requires_retrieval=intent not in {IntentType.RECALL_HISTORY, IntentType.UNKNOWN},
        )

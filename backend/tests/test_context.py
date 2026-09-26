"""ContextResolver follow-up and product-switch tests."""

from app.ai.intent import MockIntentClassifier
from app.ambient.context import ContextResolver
from app.schemas.conversation import ConversationContext
from app.schemas.enums import IntentType


async def test_renal_follow_up_infers_novara_and_uses_rewrite() -> None:
    classifier = MockIntentClassifier()
    resolver = ContextResolver()
    ctx = ConversationContext(active_entity="Novara", active_topic="dosing", last_intent=IntentType.WHATS_NEW)
    intent = await classifier.classify("What about renal impairment?", ctx)
    resolved = resolver.resolve("What about renal impairment?", intent, ctx)
    assert resolved.product == "Novara"
    assert resolved.topic == "renal impairment"
    assert resolved.product_inferred_from_context
    assert "Novara" in resolved.resolved_query


async def test_product_switch_to_cardexa_mid_session() -> None:
    classifier = MockIntentClassifier()
    resolver = ContextResolver()
    ctx = ConversationContext(active_entity="Novara", last_intent=IntentType.QUESTION_ANSWERING)
    intent = await classifier.classify("and Cardexa?", ctx)
    resolved = resolver.resolve("and Cardexa?", intent, ctx)
    assert resolved.product == "Cardexa"
    assert not resolved.product_inferred_from_context
    assert intent.intent == IntentType.FOLLOW_UP

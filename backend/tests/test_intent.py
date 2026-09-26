import pytest
from pydantic import ValidationError

from app.ai.intent import MockIntentClassifier
from app.schemas.conversation import ConversationContext
from app.schemas.enums import EntityType, IntentType, TemporalReference
from app.schemas.intent import IntentResult


def test_gemini_style_json_parses_into_schema() -> None:
    raw = """{"intent": "WHATS_NEW", "entities": [{"name": "Novara", "type": "PRODUCT"}],
              "topic": "dosing", "temporal_reference": "last_interaction",
              "requires_history": true, "requires_retrieval": true}"""
    result = IntentResult.model_validate_json(raw)
    assert result.intent == IntentType.WHATS_NEW
    assert result.product == "Novara"
    assert result.temporal_reference == TemporalReference.LAST_INTERACTION


def test_invalid_intent_is_rejected() -> None:
    with pytest.raises(ValidationError):
        IntentResult.model_validate_json('{"intent": "DIAGNOSE_PATIENT"}')


@pytest.mark.parametrize(
    ("query", "intent"),
    [
        ("What's changed with Novara since I last looked at it?", IntentType.WHATS_NEW),
        ("What's new with Novara?", IntentType.WHATS_NEW),
        ("What did I look at last time?", IntentType.RECALL_HISTORY),
        ("Show me the source.", IntentType.SHOW_SOURCE),
        ("What about renal impairment?", IntentType.FOLLOW_UP),
        ("What is the Novara dosing?", IntentType.QUESTION_ANSWERING),
        ("Tell me a joke", IntentType.UNKNOWN),
    ],
)
async def test_mock_classifier_demo_queries(query: str, intent: IntentType) -> None:
    result = await MockIntentClassifier().classify(query, ConversationContext())
    assert result.intent == intent


async def test_mock_classifier_extracts_entities_and_temporal_reference() -> None:
    result = await MockIntentClassifier().classify(
        "What’s changed with Novara since I last looked at it?", ConversationContext()
    )
    assert result.intent == IntentType.WHATS_NEW
    assert result.temporal_reference == TemporalReference.LAST_INTERACTION
    assert result.entities[0].name == "Novara" and result.entities[0].type == EntityType.PRODUCT
    assert result.requires_history


async def test_bare_topic_question_becomes_follow_up_with_active_product() -> None:
    ctx = ConversationContext(active_entity="Novara")
    result = await MockIntentClassifier().classify("Is there dosing guidance?", ctx)
    assert result.intent == IntentType.FOLLOW_UP
    assert result.topic == "dosing"

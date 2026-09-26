"""Conversational context resolution: turns an IntentResult + session state into a
concrete, standalone query and retrieval strategy (e.g. "What about renal impairment?"
-> product=Novara, topic=renal impairment)."""

from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.conversation import ConversationContext
from app.schemas.enums import EntityType, IntentType
from app.schemas.intent import ExtractedEntity, IntentResult
from app.schemas.retrieval import RetrievalStrategy

_STRATEGY = {
    IntentType.WHATS_NEW: RetrievalStrategy.WHATS_NEW,
    IntentType.RECALL_HISTORY: RetrievalStrategy.HISTORY_ONLY,
    IntentType.SHOW_SOURCE: RetrievalStrategy.SOURCE_LOOKUP,
}


class ResolvedQuery(BaseModel):
    original_query: str
    resolved_query: str
    intent: IntentType
    product: str | None = None
    topic: str | None = None
    entities: list[ExtractedEntity] = Field(default_factory=list)
    strategy: RetrievalStrategy = RetrievalStrategy.SEMANTIC
    requires_retrieval: bool = True
    product_inferred_from_context: bool = False


class ContextResolver:
    """Deterministic resolution. TODO(ai-rag): fall back to Gemini query rewriting for
    ambiguous references ("that trial", "the older one")."""

    def resolve(self, query: str, intent: IntentResult, ctx: ConversationContext) -> ResolvedQuery:
        product = intent.product
        inferred = False
        if product is None and ctx.active_entity and intent.intent != IntentType.RECALL_HISTORY:
            product, inferred = ctx.active_entity, True

        topic = intent.topic
        if topic is None and intent.intent in {IntentType.SHOW_SOURCE, IntentType.FOLLOW_UP}:
            topic = ctx.active_topic

        entities = list(intent.entities)
        if inferred and product:
            entities.insert(0, ExtractedEntity(name=product, type=EntityType.PRODUCT))

        resolved = intent.rewritten_query or query
        if inferred and product and product.lower() not in resolved.lower():
            resolved = f"{product}: {resolved}"
        if intent.intent == IntentType.SHOW_SOURCE and ctx.last_resolved_query:
            resolved = ctx.last_resolved_query

        return ResolvedQuery(
            original_query=query,
            resolved_query=resolved,
            intent=intent.intent,
            product=product,
            topic=topic,
            entities=entities,
            strategy=_STRATEGY.get(intent.intent, RetrievalStrategy.SEMANTIC),
            requires_retrieval=intent.requires_retrieval or inferred,
            product_inferred_from_context=inferred,
        )

    def next_context(
        self,
        ctx: ConversationContext,
        resolved: ResolvedQuery,
        evidence_resource_ids: list[UUID],
    ) -> ConversationContext:
        keep_previous = resolved.intent in {IntentType.SHOW_SOURCE, IntentType.RECALL_HISTORY}
        return ConversationContext(
            active_entity=resolved.product or ctx.active_entity,
            active_topic=resolved.topic if resolved.topic else (ctx.active_topic if keep_previous else None),
            active_resource_id=evidence_resource_ids[0] if evidence_resource_ids else ctx.active_resource_id,
            last_intent=resolved.intent,
            last_evidence_resource_ids=evidence_resource_ids or ctx.last_evidence_resource_ids,
            last_resolved_query=ctx.last_resolved_query if keep_previous else resolved.resolved_query,
            turn_count=ctx.turn_count + 1,
        )

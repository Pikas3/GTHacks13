"""LepiusOrchestrator — the single entry point for the Lepius loop.

HCP question -> intent -> HCP context -> retrieval -> grounded answer -> evidence
-> conversation turn -> engagement event -> interest signals -> response.

Each step is delegated to an injected service so workstreams can evolve independently.
"""

import logging
from datetime import UTC, datetime
from uuid import UUID

from app.ai.generation import GenerationRequest, ResponseGenerator
from app.ai.intent import IntentClassifier
from app.ai.retrieval import ResourceRetriever
from app.ai.semantic_diff import SemanticDiffService
from app.lepius.context import ContextResolver, ResolvedQuery
from app.lepius.memory import MemoryService
from app.lepius.personalization import PersonalizationService
from app.db.repositories.interfaces import ConversationRepository, InteractionRepository, ResourceRepository
from app.errors import AppError, ErrorCode
from app.impiricus.interfaces import IONService
from app.observability import session_id_var, timed
from app.schemas.lepius import LepiusAnswer, LepiusResponse, EvidenceReference, HCPContext
from app.schemas.conversation import ConversationContext, SessionRead
from app.schemas.diff import SemanticDiff
from app.schemas.enums import ConversationRole, EntityType, EventType, Importance, InputMode, IntentType
from app.schemas.interaction import InteractionEventCreate, TimelineEntry
from app.schemas.retrieval import RetrievalPlan, RetrievalResult, RetrievalStrategy

logger = logging.getLogger(__name__)

EXCERPT_CHARS = 500


def _human_date(ts: datetime) -> str:
    return f"{ts:%B} {ts.day}, {ts.year}"


class LepiusOrchestrator:
    def __init__(
        self,
        *,
        intent_classifier: IntentClassifier,
        retriever: ResourceRetriever,
        generator: ResponseGenerator,
        diff_service: SemanticDiffService,
        context_resolver: ContextResolver,
        memory: MemoryService,
        personalization: PersonalizationService,
        ion: IONService,
        conversations: ConversationRepository,
        interactions: InteractionRepository,
        resources: ResourceRepository,
        retrieval_limit: int = 8,
    ) -> None:
        self.intent_classifier = intent_classifier
        self.retriever = retriever
        self.generator = generator
        self.diff_service = diff_service
        self.context_resolver = context_resolver
        self.memory = memory
        self.personalization = personalization
        self.ion = ion
        self.conversations = conversations
        self.interactions = interactions
        self.resources = resources
        self.retrieval_limit = retrieval_limit

    async def process_query(
        self,
        hcp_id: UUID,
        session_id: UUID | None,
        query: str,
        input_mode: InputMode = InputMode.TEXT,
    ) -> LepiusResponse:
        timings: dict[str, float] = {}
        with timed("lepius.total", timings):
            response = await self._process(hcp_id, session_id, query.strip(), input_mode, timings)
        # `timed` records on exit, i.e. after the response was built; copy the final timings in.
        return response.model_copy(update={"timings_ms": dict(timings)})

    async def _process(
        self, hcp_id: UUID, session_id: UUID | None, query: str, input_mode: InputMode, timings: dict[str, float]
    ) -> LepiusResponse:
        # 1. Load HCP (raises INVALID_HCP)
        hcp_ctx = await self.ion.get_hcp_context(hcp_id)
        # 2. Load conversation state
        session = await self._load_or_create_session(hcp_id, session_id)
        session_id_var.set(str(session.id))
        conv = session.context

        # 3-5. Intent extraction + contextual reference resolution
        intent = await self.intent_classifier.classify(query, conv, timings=timings)
        resolved = self.context_resolver.resolve(query, intent, conv)

        # 3b. Historical engagement relevant to the active entity (before we record this turn)
        if resolved.product:
            hcp_ctx.last_entity_review = await self.memory.get_last_review_of_entity(hcp_id, resolved.product)

        # 6-7. Retrieval strategy + retrieval
        results, changes, history = await self._retrieve(hcp_id, session.id, resolved, hcp_ctx, conv, timings)
        evidence = self._to_evidence(results)

        # 8. Grounded generation
        since = hcp_ctx.last_entity_review
        with timed("generation", timings):
            answer = await self.generator.generate(
                GenerationRequest(
                    query=resolved.resolved_query if resolved.intent != IntentType.SHOW_SOURCE else query,
                    intent=resolved.intent,
                    product=resolved.product,
                    topic=resolved.topic,
                    hcp_context=hcp_ctx,
                    conversation=conv,
                    evidence=evidence,
                    changes=changes,
                    history=history,
                    since_label=_human_date(since.timestamp) if since else None,
                ),
                timings=timings,
            )

        # 9. Evidence references actually cited (fall back to everything retrieved)
        if answer.cited_evidence_ids:
            cited = set(answer.cited_evidence_ids)
            evidence = [e for e in evidence if e.id in cited]

        # 10. Conversation turns
        await self.conversations.add_turn(session.id, ConversationRole.USER, query, {"input_mode": input_mode})
        await self.conversations.add_turn(
            session.id,
            ConversationRole.ASSISTANT,
            answer.text,
            {"intent": resolved.intent, "evidence": [e.id for e in evidence]},
        )

        # 11-12. Engagement signals -> interest scores, then the time-series event
        now = datetime.now(UTC)
        event_type = EventType.VOICE_QUERY if input_mode == InputMode.VOICE else EventType.TEXT_QUERY
        signals = await self.personalization.apply(
            hcp_id=hcp_id,
            event_type=event_type,
            entities=resolved.entities,
            topic=resolved.topic,
            intent=resolved.intent,
            at=now,
        )
        await self.interactions.record(
            InteractionEventCreate(
                hcp_id=hcp_id,
                session_id=session.id,
                event_type=event_type,
                timestamp=now,
                query_text=query,
                response_text=answer.text,
                intent=resolved.intent,
                entity=resolved.product,
                topic=resolved.topic,
                resource_id=evidence[0].resource_id if evidence else None,
                metadata={
                    "resolved_query": resolved.resolved_query,
                    "evidence_resource_ids": [str(e.resource_id) for e in evidence],
                    "signals": [s.model_dump(mode="json") for s in signals],
                    "insufficient_evidence": answer.insufficient_evidence,
                },
            )
        )

        new_ctx = self.context_resolver.next_context(
            conv, resolved, list(dict.fromkeys(e.resource_id for e in evidence))
        )
        await self.conversations.update_context(session.id, new_ctx)

        # 13. Response
        return LepiusResponse(
            session_id=session.id,
            query=query,
            resolved_query=resolved.resolved_query,
            intent=resolved.intent,
            entities=resolved.entities,
            response=LepiusAnswer(
                text=answer.text, speech_text=answer.speech_text, insufficient_evidence=answer.insufficient_evidence
            ),
            context=new_ctx,
            evidence=evidence,
            changes=changes,
            history=history,
            suggested_followups=answer.suggested_followups,
            signals_generated=signals,
            timings_ms=timings,
        )

    async def _load_or_create_session(self, hcp_id: UUID, session_id: UUID | None) -> SessionRead:
        if session_id is None:
            session = await self.conversations.create_session(hcp_id)
            await self.interactions.record(
                InteractionEventCreate(hcp_id=hcp_id, session_id=session.id, event_type=EventType.SESSION_STARTED)
            )
            return session
        session = await self.conversations.get_session(session_id)
        if session is None or session.hcp_id != hcp_id:
            raise AppError(ErrorCode.INVALID_SESSION, f"Session {session_id} not found for this HCP")
        return session

    async def _retrieve(
        self,
        hcp_id: UUID,
        session_id: UUID,
        resolved: ResolvedQuery,
        hcp_ctx: HCPContext,
        conv: ConversationContext,
        timings: dict[str, float],
    ) -> tuple[list[RetrievalResult], list[SemanticDiff], list[TimelineEntry]]:
        changes: list[SemanticDiff] = []
        history: list[TimelineEntry] = []

        if resolved.strategy == RetrievalStrategy.HISTORY_ONLY:
            # "Last time" = prior sessions, not the conversation in progress.
            history = await self.memory.get_timeline(hcp_id, limit=10, exclude_session_id=session_id)
            return [], changes, history
        if not resolved.requires_retrieval:
            return [], changes, history

        plan = RetrievalPlan(
            strategy=resolved.strategy,
            query=resolved.resolved_query,
            product=resolved.product or self._top_product(hcp_ctx),
            topic=resolved.topic,
            include_superseded=resolved.intent == IntentType.COMPARE,
            limit=self.retrieval_limit,
        )

        if resolved.strategy == RetrievalStrategy.WHATS_NEW and plan.product:
            whats_new = await self.memory.whats_new(hcp_id, plan.product, hcp_ctx.last_entity_review)
            if hcp_ctx.last_entity_review:
                plan.published_after = hcp_ctx.last_entity_review.timestamp
            with timed("semantic_diff", timings):
                for old, new in whats_new.superseded_pairs:
                    old_d = await self.resources.get_detail(old.id)
                    new_d = await self.resources.get_detail(new.id)
                    if old_d and new_d:
                        changes.append(await self.diff_service.compare(old_d, new_d, timings=timings))
            if not whats_new.new_resources:
                return [], changes, history
            # Steer retrieval toward what changed and what this HCP cares about.
            focus = [c.topic for d in changes for c in d.changes if c.importance == Importance.HIGH]
            focus += [i.entity for i in hcp_ctx.interests if i.entity_type != EntityType.PRODUCT][:3]
            plan.query = " ".join([plan.query, *focus])

        with timed("retrieval", timings):
            results = await self.retriever.search(plan, hcp_ctx, conv, timings=timings)
        if resolved.strategy == RetrievalStrategy.SOURCE_LOOKUP and conv.last_evidence_resource_ids:
            previous = set(conv.last_evidence_resource_ids)
            results = [r for r in results if r.resource.id in previous] or results
        return results, changes, history

    @staticmethod
    def _top_product(hcp_ctx: HCPContext) -> str | None:
        return next((i.entity for i in hcp_ctx.interests if i.entity_type == EntityType.PRODUCT), None)

    @staticmethod
    def _to_evidence(results: list[RetrievalResult]) -> list[EvidenceReference]:
        return [
            EvidenceReference(
                id=f"E{i}",
                resource_id=r.resource.id,
                chunk_id=r.chunk.id,
                title=r.resource.title,
                product=r.resource.product,
                resource_type=r.resource.resource_type,
                version=r.resource.version,
                section=r.chunk.section,
                page=r.chunk.page,
                published_at=r.resource.published_at,
                excerpt=r.chunk.text[:EXCERPT_CHARS],
                source_url=r.resource.source_url,
                is_new=r.is_new_since_last_view,
                score=r.score,
            )
            for i, r in enumerate(results, start=1)
        ]

from app.ai.retrieval import HybridResourceRetriever
from app.schemas.ambient import HCPContext
from app.schemas.conversation import ConversationContext
from app.schemas.retrieval import RetrievalPlan, RetrievalStrategy
from tests.conftest import MORGAN_ID


async def _ctx(ion) -> HCPContext:
    return await ion.get_hcp_context(MORGAN_ID, entity="Novara")


async def test_semantic_search_finds_renal_section(resources, embedder, ion) -> None:
    retriever = HybridResourceRetriever(resources, embedder)
    plan = RetrievalPlan(query="Novara renal impairment", product="Novara", topic="renal impairment", limit=4)
    results = await retriever.search(plan, await _ctx(ion), ConversationContext())
    assert results, "expected at least one result"
    assert results[0].chunk.section == "Renal Impairment"
    assert results[0].resource.version == "2.0"  # newer + unseen outranks v1
    assert all(r.resource.product == "Novara" for r in results)


async def test_published_after_filter_and_new_flags(resources, embedder, ion) -> None:
    ctx = await _ctx(ion)
    assert ctx.last_entity_review is not None
    plan = RetrievalPlan(
        strategy=RetrievalStrategy.WHATS_NEW,
        query="what changed",
        product="Novara",
        published_after=ctx.last_entity_review.timestamp,
    )
    results = await HybridResourceRetriever(resources, embedder).search(plan, ctx, ConversationContext())
    assert results and all(r.is_new_since_last_view for r in results)


async def test_results_are_diversified_per_resource(resources, embedder, ion) -> None:
    plan = RetrievalPlan(query="Novara", product="Novara", limit=8)
    results = await HybridResourceRetriever(resources, embedder).search(plan, await _ctx(ion), ConversationContext())
    per: dict = {}
    for r in results:
        per[r.resource.id] = per.get(r.resource.id, 0) + 1
    assert max(per.values()) <= 2

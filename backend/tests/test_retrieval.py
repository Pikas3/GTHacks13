"""Retrieval eval + preference boost checks on the in-memory seed corpus."""

from __future__ import annotations

from app.ai.retrieval import HybridResourceRetriever, RankingWeights
from app.schemas.lepius import HCPContext
from app.schemas.conversation import ConversationContext
from app.schemas.enums import ResourceType
from app.schemas.hcp import HCPPreferenceRead
from app.schemas.retrieval import RetrievalPlan, RetrievalStrategy
from tests.conftest import MORGAN_ID

# query → expected top resource key fragment / section (hit@1 target)
_EVAL = [
    {
        "query": "Novara renal impairment",
        "product": "Novara",
        "topic": "renal impairment",
        "expect_section": "Renal Impairment",
        "expect_title_substr": "Prescribing Information",
        "expect_version": "2.0",
    },
    {
        "query": "Novara long-term outcomes follow-up",
        "product": "Novara",
        "topic": "long-term outcomes",
        "expect_title_substr": "Long-Term",
    },
    {
        "query": "Cardexa renal dosing adjustment",
        "product": "Cardexa",
        "topic": "renal impairment",
        "expect_section": "Renal Impairment",
        "expect_title_substr": "Cardexa",
    },
    {
        "query": "Lumetrex patient access prior authorization",
        "product": "Lumetrex",
        "topic": "patient access",
        "expect_title_substr": "Access",
        "expect_type": ResourceType.ACCESS_GUIDE,
    },
    {
        "query": "Lumetrex adherence tips for patients",
        "product": "Lumetrex",
        "topic": "adherence",
        "expect_title_substr": "Patient Education",
    },
]


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


async def test_retrieval_eval_hit_at_k(resources, embedder, ion) -> None:
    """Small retrieval set: report hit@1 / hit@3 on fakes (vector+lexical hybrid)."""
    retriever = HybridResourceRetriever(resources, embedder)
    ctx = await _ctx(ion)
    hit1 = hit3 = 0
    for case in _EVAL:
        plan = RetrievalPlan(
            query=case["query"],
            product=case.get("product"),
            topic=case.get("topic"),
            limit=5,
        )
        results = await retriever.search(plan, ctx, ConversationContext())
        assert results, case["query"]

        def matches(r, expected: dict = case) -> bool:
            ok = True
            if "expect_section" in expected:
                ok = ok and r.chunk.section == expected["expect_section"]
            if "expect_title_substr" in expected:
                ok = ok and expected["expect_title_substr"].lower() in r.resource.title.lower()
            if "expect_version" in expected:
                ok = ok and r.resource.version == expected["expect_version"]
            if "expect_type" in expected:
                ok = ok and r.resource.resource_type == expected["expect_type"]
            return ok

        if matches(results[0]):
            hit1 += 1
        if any(matches(r) for r in results[:3]):
            hit3 += 1
    n = len(_EVAL)
    # Mock bag-of-words + lexical should clear most of this set.
    assert hit1 / n >= 0.6, f"hit@1={hit1}/{n}"
    assert hit3 / n >= 0.8, f"hit@3={hit3}/{n}"


async def test_preference_boosts_clinical_study(resources, embedder, ion) -> None:
    ctx = await _ctx(ion)
    ctx = ctx.model_copy(
        update={
            "preferences": [
                HCPPreferenceRead(key="clinical_evidence", value="trials", weight=1.0),
            ]
        }
    )
    plan = RetrievalPlan(query="Novara outcomes", product="Novara", topic="efficacy", limit=6)
    results = await HybridResourceRetriever(
        resources, embedder, weights=RankingWeights(preference=0.35, semantic=0.35)
    ).search(plan, ctx, ConversationContext())
    assert results
    # Preference signal should appear on clinical study hits.
    study_hits = [r for r in results if r.resource.resource_type == ResourceType.CLINICAL_STUDY]
    assert study_hits
    assert any(r.breakdown.preference > 0 for r in study_hits)

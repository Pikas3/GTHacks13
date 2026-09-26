"""Grounded response generation.

Contract: factual medical/product claims come ONLY from `evidence`. If evidence is empty or
insufficient the generator must say so (insufficient_evidence=True) rather than improvise.
"""

from typing import Protocol

from pydantic import BaseModel, Field

from app.ai.gemini_client import GeminiClient
from app.ai.prompts import GROUNDED_PROMPT, GROUNDED_SYSTEM
from app.schemas.ambient import EvidenceReference, HCPContext
from app.schemas.conversation import ConversationContext
from app.schemas.diff import SemanticDiff
from app.schemas.enums import IntentType
from app.schemas.interaction import TimelineEntry


class GenerationRequest(BaseModel):
    query: str
    intent: IntentType
    product: str | None = None
    topic: str | None = None
    hcp_context: HCPContext
    conversation: ConversationContext
    evidence: list[EvidenceReference] = Field(default_factory=list)
    changes: list[SemanticDiff] = Field(default_factory=list)
    history: list[TimelineEntry] = Field(default_factory=list)
    since_label: str | None = Field(default=None, description="Human date of last look, for WHATS_NEW.")


class GeneratedAnswer(BaseModel):
    text: str = Field(description="Visual answer with inline [E#] citations.")
    speech_text: str = Field(description="Short spoken rendering without citations.")
    insufficient_evidence: bool = False
    cited_evidence_ids: list[str] = Field(default_factory=list)
    suggested_followups: list[str] = Field(default_factory=list)


class ResponseGenerator(Protocol):
    async def generate(
        self, request: GenerationRequest, timings: dict[str, float] | None = None
    ) -> GeneratedAnswer: ...


def _format_evidence(evidence: list[EvidenceReference]) -> str:
    if not evidence:
        return "(no evidence passages retrieved)"
    return "\n\n".join(
        f"[{e.id}] {e.title} v{e.version} — {e.section or 'General'} (published {e.published_at:%Y-%m-%d})\n{e.excerpt}"
        for e in evidence
    )


class GeminiResponseGenerator:
    """TODO(ai-rag): evaluate prompts on the demo script; post-check that every [E#] in `text` exists."""

    def __init__(self, client: GeminiClient) -> None:
        self.client = client

    async def generate(self, request: GenerationRequest, timings: dict[str, float] | None = None) -> GeneratedAnswer:
        if request.intent == IntentType.RECALL_HISTORY:
            # History answers come from structured memory, not the model.
            return await MockResponseGenerator().generate(request)
        changes = "\n".join(
            f"Change in {d.resource} v{d.old_version}->v{d.new_version}: {c.topic}: {c.summary}"
            for d in request.changes
            for c in d.changes
        )
        prompt = GROUNDED_PROMPT.format(
            hcp_name=request.hcp_context.hcp.name,
            specialty=request.hcp_context.hcp.specialty,
            interests=", ".join(i.entity for i in request.hcp_context.interests[:5]) or "-",
            active_entity=request.conversation.active_entity or "-",
            active_topic=request.conversation.active_topic or "-",
            intent=request.intent.value,
            temporal_note=f"Last reviewed this product on {request.since_label}." if request.since_label else "",
            evidence=_format_evidence(request.evidence),
            changes=f"Detected document changes:\n{changes}" if changes else "",
            query=request.query,
        )
        answer = await self.client.generate_structured(
            prompt=prompt,
            schema=GeneratedAnswer,
            system_instruction=GROUNDED_SYSTEM,
            operation="gemini.generate",
            timings=timings,
        )
        # Guardrail: never return an evidence-free factual answer.
        if not request.evidence and not answer.insufficient_evidence:
            answer.insufficient_evidence = True
        valid_ids = {e.id for e in request.evidence}
        answer.cited_evidence_ids = [i for i in answer.cited_evidence_ids if i in valid_ids]
        return answer


def _first_sentence(text: str, max_len: int = 220) -> str:
    sentence = text.strip().split(". ")[0].rstrip(".")
    return (sentence[: max_len - 1] + "…") if len(sentence) > max_len else sentence + "."


class MockResponseGenerator:
    """Deterministic template answers built strictly from the provided evidence."""

    async def generate(self, request: GenerationRequest, timings: dict[str, float] | None = None) -> GeneratedAnswer:
        ev = request.evidence
        product = request.product or "this product"
        match request.intent:
            case IntentType.RECALL_HISTORY:
                return self._history(request)
            case IntentType.UNKNOWN if not ev:
                return GeneratedAnswer(
                    text="I can help with approved resources for Novara, Cardexa and Lumetrex (fictional "
                    "prototype products). Try asking what's new, or about dosing or access.",
                    speech_text="I can help with approved resources for Novara, Cardexa and Lumetrex.",
                    insufficient_evidence=True,
                    suggested_followups=["What's new with Novara?", "What did I look at last time?"],
                )
            case _ if not ev:
                since = f" since {request.since_label}" if request.since_label else ""
                msg = (
                    f"I couldn't find new approved {product} resources{since}."
                    if request.intent == IntentType.WHATS_NEW
                    else f"The available approved resources for {product} don't address that question."
                )
                return GeneratedAnswer(
                    text=msg,
                    speech_text=msg,
                    insufficient_evidence=True,
                    suggested_followups=[f"What's new with {product}?"],
                )
            case IntentType.WHATS_NEW:
                return self._whats_new(request)
            case IntentType.SHOW_SOURCE:
                titles = "; ".join(f"{e.title} v{e.version}, {e.section} [{e.id}]" for e in ev[:3])
                return GeneratedAnswer(
                    text=f"My previous answer drew on: {titles}.",
                    speech_text=f"I've pulled up {len(ev[:3])} source passages on screen.",
                    cited_evidence_ids=[e.id for e in ev[:3]],
                    suggested_followups=["What's changed since I last looked?"],
                )
            case _:
                top = ev[0]
                topic = f" on {request.topic}" if request.topic else ""
                text = f"According to {top.title} v{top.version} ({top.section}){topic}: {_first_sentence(top.excerpt)} [{top.id}]"
                if len(ev) > 1:
                    text += f" See also {ev[1].title} [{ev[1].id}]."
                return GeneratedAnswer(
                    text=text,
                    speech_text=f"According to the {top.title}, {_first_sentence(top.excerpt)}",
                    cited_evidence_ids=[e.id for e in ev[:2]],
                    suggested_followups=[f"What's new with {product}?", "Show me the source."],
                )

    def _whats_new(self, request: GenerationRequest) -> GeneratedAnswer:
        seen: dict[str, EvidenceReference] = {}
        for e in request.evidence:
            seen.setdefault(str(e.resource_id), e)
        new = list(seen.values())
        since = f"Since you last reviewed {request.product} on {request.since_label}, " if request.since_label else ""
        titles = ", ".join(f"{e.title} v{e.version} [{e.id}]" for e in new)
        text = f"{since}{len(new)} updated approved resource(s) are available: {titles}."
        change_bits = [c.summary for d in request.changes for c in d.changes if c.importance == "HIGH"]
        if change_bits:
            text += " Key change: " + change_bits[0]
        speech = f"{since}there are {len(new)} new resources, including {new[0].title}." + (
            " The most notable change: " + change_bits[0] if change_bits else ""
        )
        return GeneratedAnswer(
            text=text,
            speech_text=speech[0].upper() + speech[1:],
            cited_evidence_ids=[e.id for e in new],
            suggested_followups=[
                "What about renal impairment?",
                "Show me the source.",
                "What did I look at last time?",
            ],
        )

    def _history(self, request: GenerationRequest) -> GeneratedAnswer:
        items = request.history[:4]
        if not items:
            msg = "I don't have any previous interactions on record for you yet."
            return GeneratedAnswer(text=msg, speech_text=msg, insufficient_evidence=True)
        lines = "; ".join(f"{i.timestamp:%b %d}: {i.label}" for i in items)
        first = items[0]
        return GeneratedAnswer(
            text=f"Here's your recent activity — {lines}.",
            speech_text=f"Most recently, on {first.timestamp:%B} {first.timestamp.day}, you {first.label[0].lower() + first.label[1:].rstrip('.?!')}.",
            suggested_followups=["What's changed since I last looked?"],
        )

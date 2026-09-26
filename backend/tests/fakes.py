"""In-memory implementations of the repository Protocols, built from the real seed files.

Lets us test services and the orchestrator without a database or API keys.
"""

import json
import math
import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from app.ai.embeddings import MockEmbeddingProvider
from app.config import REPO_ROOT
from app.ingestion.chunker import chunk_sections
from app.ingestion.parser import parse_resource_file
from app.ingestion.seed import stable_id
from app.schemas.conversation import ConversationContext, ConversationTurnRead, SessionDetail, SessionRead
from app.schemas.enums import ConversationRole, EntityType, EventType
from app.schemas.hcp import HCPDetail, HCPInterestRead, HCPPreferenceRead, HCPRead
from app.schemas.intelligence import EngagementBucket, TopicAffinity
from app.schemas.interaction import InteractionEventCreate, InteractionEventRead
from app.schemas.resource import ChunkHit, ResourceChunkRead, ResourceDetail, ResourceRead

SEED_DIR = REPO_ROOT / "data" / "seed"
DIM = 256


def _cos(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class FakeHCPRepository:
    def __init__(self) -> None:
        self.hcps: dict[UUID, HCPRead] = {}
        self.prefs: dict[UUID, list[HCPPreferenceRead]] = {}
        self.interests: dict[UUID, dict[str, HCPInterestRead]] = {}
        for h in json.loads((SEED_DIR / "hcps.json").read_text()):
            hid = stable_id("hcp", h["external_id"])
            self.hcps[hid] = HCPRead(id=hid, external_id=h["external_id"], name=h["name"], specialty=h["specialty"])
            self.prefs[hid] = [HCPPreferenceRead(**p) for p in h["preferences"]]
            self.interests[hid] = {
                i["entity"].lower(): HCPInterestRead(
                    entity=i["entity"],
                    entity_type=EntityType(i["entity_type"]),
                    score=i["score"],
                    interaction_count=i["interaction_count"],
                )
                for i in h["interests"]
            }

    async def list_hcps(self) -> list[HCPRead]:
        return list(self.hcps.values())

    async def get_hcp(self, hcp_id: UUID) -> HCPRead | None:
        return self.hcps.get(hcp_id)

    async def get_detail(self, hcp_id: UUID) -> HCPDetail | None:
        h = self.hcps.get(hcp_id)
        if h is None:
            return None
        return HCPDetail(**h.model_dump(), preferences=self.prefs[hcp_id], interests=await self.get_interests(hcp_id))

    async def get_preferences(self, hcp_id: UUID) -> list[HCPPreferenceRead]:
        return self.prefs.get(hcp_id, [])

    async def get_interests(self, hcp_id: UUID) -> list[HCPInterestRead]:
        return sorted(self.interests.get(hcp_id, {}).values(), key=lambda i: i.score, reverse=True)

    async def upsert_interest(
        self, hcp_id: UUID, entity: str, entity_type: EntityType, new_score: float, at: datetime
    ) -> HCPInterestRead:
        cur = self.interests.setdefault(hcp_id, {}).get(entity.lower())
        count = (cur.interaction_count if cur else 0) + 1
        row = HCPInterestRead(
            entity=entity, entity_type=entity_type, score=new_score, interaction_count=count, last_interaction_at=at
        )
        self.interests[hcp_id][entity.lower()] = row
        return row


class FakeResourceRepository:
    def __init__(self, embedder: MockEmbeddingProvider) -> None:
        self.resources: dict[UUID, ResourceRead] = {}
        self.chunks: dict[UUID, list[tuple[ResourceChunkRead, list[float]]]] = {}
        self.by_key: dict[str, UUID] = {}
        self.embedder = embedder

    async def load_seed(self) -> "FakeResourceRepository":
        parsed = [parse_resource_file(p) for p in sorted((SEED_DIR / "resources").glob("*.md"))]
        self.by_key = {r.key: stable_id("resource", r.key) for r in parsed}
        for r in parsed:
            rid = self.by_key[r.key]
            self.resources[rid] = ResourceRead(
                id=rid,
                title=r.title,
                product=r.product,
                resource_type=r.resource_type,
                version=r.version,
                published_at=r.published_at,
                supersedes_resource_id=self.by_key.get(r.supersedes_key) if r.supersedes_key else None,
                source_url=r.source_url,
            )
            drafts = chunk_sections(r.sections)
            vectors = await self.embedder.embed_documents([f"{r.title} — {c.section}\n{c.text}" for c in drafts])
            self.chunks[rid] = [
                (
                    ResourceChunkRead(
                        id=uuid.uuid4(),
                        resource_id=rid,
                        chunk_index=c.index,
                        text=c.text,
                        section=c.section,
                        page=c.page,
                    ),
                    v,
                )
                for c, v in zip(drafts, vectors, strict=True)
            ]
        return self

    async def list_resources(self, product: str | None = None) -> list[ResourceRead]:
        return [r for r in self.resources.values() if not product or r.product.lower() == product.lower()]

    async def get_resource(self, resource_id: UUID) -> ResourceRead | None:
        return self.resources.get(resource_id)

    async def get_detail(self, resource_id: UUID) -> ResourceDetail | None:
        r = self.resources.get(resource_id)
        if r is None:
            return None
        return ResourceDetail(**r.model_dump(), chunks=[c for c, _ in self.chunks[resource_id]])

    async def get_many(self, resource_ids: list[UUID]) -> list[ResourceRead]:
        return [self.resources[i] for i in resource_ids if i in self.resources]

    async def published_after(self, product: str, after: datetime | None) -> list[ResourceRead]:
        rows = [r for r in await self.list_resources(product) if after is None or r.published_at > after]
        return sorted(rows, key=lambda r: r.published_at, reverse=True)

    async def get_superseded(self, resource_id: UUID) -> ResourceRead | None:
        r = self.resources.get(resource_id)
        return self.resources.get(r.supersedes_resource_id) if r and r.supersedes_resource_id else None

    async def vector_search(
        self,
        embedding: list[float],
        *,
        limit: int,
        product: str | None = None,
        published_after: datetime | None = None,
        approved_only: bool = True,
        exclude_superseded: bool = True,
    ) -> list[ChunkHit]:
        superseded = {r.supersedes_resource_id for r in self.resources.values() if r.supersedes_resource_id}
        hits = [
            ChunkHit(chunk=c, resource=r, similarity=_cos(embedding, v))
            for rid, r in self.resources.items()
            if (not product or r.product.lower() == product.lower())
            and (published_after is None or r.published_at > published_after)
            and not (exclude_superseded and rid in superseded)
            for c, v in self.chunks[rid]
        ]
        return sorted(hits, key=lambda h: h.similarity, reverse=True)[:limit]


class FakeInteractionRepository:
    def __init__(self, resources: FakeResourceRepository) -> None:
        self.events: list[InteractionEventRead] = []
        self.resources = resources

    def load_seed(self) -> "FakeInteractionRepository":
        for e in json.loads((SEED_DIR / "history.json").read_text()):
            rid = self.resources.by_key.get(e.get("resource_key", ""))
            self._append(
                InteractionEventCreate(
                    hcp_id=stable_id("hcp", e["hcp_external_id"]),
                    event_type=EventType(e["event_type"]),
                    timestamp=datetime.fromisoformat(e["timestamp"]),
                    query_text=e.get("query_text"),
                    entity=e.get("entity"),
                    topic=e.get("topic"),
                    resource_id=rid,
                )
            )
        return self

    def _append(self, event: InteractionEventCreate) -> InteractionEventRead:
        r = self.resources.resources.get(event.resource_id) if event.resource_id else None
        row = InteractionEventRead(
            **event.model_dump(exclude={"timestamp"}),
            id=uuid.uuid4(),
            timestamp=event.timestamp or datetime.now(UTC),
            resource_title=f"{r.title} v{r.version}" if r else None,
        )
        self.events.append(row)
        return row

    async def record(self, event: InteractionEventCreate) -> InteractionEventRead:
        return self._append(event)

    def _for(self, hcp_id: UUID) -> list[InteractionEventRead]:
        return sorted((e for e in self.events if e.hcp_id == hcp_id), key=lambda e: e.timestamp, reverse=True)

    async def recent(
        self, hcp_id: UUID, *, limit: int = 20, since: datetime | None = None
    ) -> list[InteractionEventRead]:
        return [e for e in self._for(hcp_id) if since is None or e.timestamp > since][:limit]

    async def last_with_entity(
        self, hcp_id: UUID, entity: str, *, before: datetime | None = None, event_types: set | None = None
    ) -> InteractionEventRead | None:
        for e in self._for(hcp_id):
            if event_types and e.event_type not in event_types:
                continue
            r = self.resources.resources.get(e.resource_id) if e.resource_id else None
            touches = (e.entity or "").lower() == entity.lower() or (
                r is not None and r.product.lower() == entity.lower()
            )
            if touches and (before is None or e.timestamp < before):
                return e
        return None

    async def viewed_resource_ids(self, hcp_id: UUID, entity: str | None = None) -> set[UUID]:
        out = set()
        for e in self._for(hcp_id):
            if e.event_type in {EventType.RESOURCE_VIEW, EventType.SOURCE_OPEN} and e.resource_id:
                r = self.resources.resources[e.resource_id]
                if entity is None or r.product.lower() == entity.lower():
                    out.add(e.resource_id)
        return out

    async def top_entities(
        self, hcp_id: UUID, *, since: datetime | None = None, limit: int = 10
    ) -> list[TopicAffinity]:
        counts: dict[str, int] = {}
        for e in self._for(hcp_id):
            label = e.topic or e.entity
            if label:
                counts[label] = counts.get(label, 0) + 1
        total = sum(counts.values()) or 1
        return [
            TopicAffinity(entity=k, score=v / total, interaction_count=v)
            for k, v in sorted(counts.items(), key=lambda kv: -kv[1])
        ][:limit]

    async def engagement_over_time(
        self, hcp_id: UUID, *, bucket: str = "1 day", since: datetime | None = None
    ) -> list[EngagementBucket]:
        return []


class FakeConversationRepository:
    def __init__(self) -> None:
        self.sessions: dict[UUID, SessionRead] = {}
        self.turns: dict[UUID, list[ConversationTurnRead]] = {}

    async def create_session(self, hcp_id: UUID) -> SessionRead:
        now = datetime.now(UTC)
        s = SessionRead(id=uuid.uuid4(), hcp_id=hcp_id, started_at=now, last_activity_at=now)
        self.sessions[s.id] = s
        self.turns[s.id] = []
        return s

    async def get_session(self, session_id: UUID) -> SessionRead | None:
        return self.sessions.get(session_id)

    async def get_detail(self, session_id: UUID) -> SessionDetail | None:
        s = self.sessions.get(session_id)
        return SessionDetail(**s.model_dump(), turns=self.turns[session_id]) if s else None

    async def update_context(self, session_id: UUID, context: ConversationContext) -> None:
        self.sessions[session_id] = self.sessions[session_id].model_copy(update={"context": context})

    async def add_turn(
        self, session_id: UUID, role: ConversationRole, content: str, metadata: dict[str, Any] | None = None
    ) -> ConversationTurnRead:
        t = ConversationTurnRead(
            id=uuid.uuid4(), role=role, content=content, created_at=datetime.now(UTC), metadata=metadata or {}
        )
        self.turns[session_id].append(t)
        return t

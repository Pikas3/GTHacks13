import pytest

from app.ai.embeddings import MockEmbeddingProvider
from app.ai.generation import MockResponseGenerator
from app.ai.intent import MockIntentClassifier
from app.ai.retrieval import HybridResourceRetriever
from app.ai.semantic_diff import MockSemanticDiffService
from app.ambient.context import ContextResolver
from app.ambient.memory import MemoryService
from app.ambient.orchestrator import AmbientOrchestrator
from app.ambient.personalization import PersonalizationService
from app.impiricus.mock_ion import MockIONService
from app.ingestion.seed import stable_id
from tests.fakes import (
    DIM,
    FakeConversationRepository,
    FakeHCPRepository,
    FakeInteractionRepository,
    FakeResourceRepository,
)

MORGAN_ID = stable_id("hcp", "SYN-HCP-001")


@pytest.fixture
def embedder() -> MockEmbeddingProvider:
    return MockEmbeddingProvider(DIM)


@pytest.fixture
async def resources(embedder: MockEmbeddingProvider) -> FakeResourceRepository:
    return await FakeResourceRepository(embedder).load_seed()


@pytest.fixture
def interactions(resources: FakeResourceRepository) -> FakeInteractionRepository:
    return FakeInteractionRepository(resources).load_seed()


@pytest.fixture
def hcps() -> FakeHCPRepository:
    return FakeHCPRepository()


@pytest.fixture
def conversations() -> FakeConversationRepository:
    return FakeConversationRepository()


@pytest.fixture
def ion(hcps, interactions, resources) -> MockIONService:
    return MockIONService(hcps, interactions, resources)


@pytest.fixture
def orchestrator(embedder, hcps, resources, interactions, conversations, ion) -> AmbientOrchestrator:
    return AmbientOrchestrator(
        intent_classifier=MockIntentClassifier(),
        retriever=HybridResourceRetriever(resources, embedder),
        generator=MockResponseGenerator(),
        diff_service=MockSemanticDiffService(),
        context_resolver=ContextResolver(),
        memory=MemoryService(interactions, resources),
        personalization=PersonalizationService(ion),
        ion=ion,
        conversations=conversations,
        interactions=interactions,
        resources=resources,
    )

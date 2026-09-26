"""Dependency injection wiring.

`ServiceContainer` holds process-lifetime singletons (engine, HTTP client, AI + voice providers)
chosen from Settings — mock or real. Request-scoped objects (repositories bound to a DB
session, the orchestrator) are assembled by the `get_*` functions below.
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field

import httpx
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.ai.embeddings import EmbeddingProvider, GeminiEmbeddingProvider, MockEmbeddingProvider
from app.ai.gemini_client import GeminiClient
from app.ai.generation import GeminiResponseGenerator, MockResponseGenerator, ResponseGenerator
from app.ai.intent import GeminiIntentClassifier, IntentClassifier, MockIntentClassifier
from app.ai.retrieval import HybridResourceRetriever
from app.ai.semantic_diff import GeminiSemanticDiffService, MockSemanticDiffService, SemanticDiffService
from app.ambient.context import ContextResolver
from app.ambient.memory import MemoryService
from app.ambient.orchestrator import AmbientOrchestrator
from app.ambient.personalization import EngagementService, PersonalizationService
from app.config import Settings
from app.db.repositories.conversation_repository import SqlConversationRepository
from app.db.repositories.hcp_repository import SqlHCPRepository
from app.db.repositories.interaction_repository import SqlInteractionRepository
from app.db.repositories.resource_repository import SqlResourceRepository
from app.db.session import create_engine, create_session_factory, session_scope
from app.impiricus.mock_ion import MockIONService
from app.voice.elevenlabs_stt import ElevenLabsSTTProvider
from app.voice.elevenlabs_tts import ElevenLabsTTSProvider
from app.voice.interfaces import SpeechToTextProvider, TextToSpeechProvider
from app.voice.mock_stt import MockSTTProvider
from app.voice.mock_tts import MockTTSProvider


@dataclass
class AIProviders:
    intent: IntentClassifier
    embedder: EmbeddingProvider
    generator: ResponseGenerator
    diff: SemanticDiffService
    mode: str


def build_ai_providers(settings: Settings) -> AIProviders:
    if settings.ai_is_mocked:
        return AIProviders(
            intent=MockIntentClassifier(),
            embedder=MockEmbeddingProvider(settings.gemini_embedding_dimension),
            generator=MockResponseGenerator(),
            diff=MockSemanticDiffService(),
            mode="mock",
        )
    client = GeminiClient(settings)
    return AIProviders(
        intent=GeminiIntentClassifier(client),
        embedder=GeminiEmbeddingProvider(client),
        generator=GeminiResponseGenerator(client),
        diff=GeminiSemanticDiffService(client),
        mode="gemini",
    )


def build_voice_providers(
    settings: Settings, http: httpx.AsyncClient
) -> tuple[SpeechToTextProvider, TextToSpeechProvider]:
    if settings.voice_is_mocked:
        return MockSTTProvider(settings.mock_stt_text), MockTTSProvider()
    tts: TextToSpeechProvider = (
        ElevenLabsTTSProvider(settings, http) if settings.elevenlabs_voice_id else MockTTSProvider()
    )
    return ElevenLabsSTTProvider(settings, http), tts


@dataclass
class ServiceContainer:
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    http: httpx.AsyncClient
    ai: AIProviders
    stt: SpeechToTextProvider
    tts: TextToSpeechProvider
    capabilities: dict[str, bool] = field(default_factory=dict)

    @classmethod
    def create(cls, settings: Settings) -> "ServiceContainer":
        engine = create_engine(settings)
        http = httpx.AsyncClient(timeout=settings.elevenlabs_timeout_s)
        stt, tts = build_voice_providers(settings, http)
        return cls(
            settings=settings,
            engine=engine,
            session_factory=create_session_factory(engine),
            http=http,
            ai=build_ai_providers(settings),
            stt=stt,
            tts=tts,
        )

    async def aclose(self) -> None:
        await self.http.aclose()
        await self.engine.dispose()


# --- FastAPI dependencies --------------------------------------------------------------------


def get_container(request: Request) -> ServiceContainer:
    container: ServiceContainer = request.app.state.container
    return container


def get_settings_dep(container: ServiceContainer = Depends(get_container)) -> Settings:
    return container.settings


async def get_db(container: ServiceContainer = Depends(get_container)) -> AsyncIterator[AsyncSession]:
    async for session in session_scope(container.session_factory):
        yield session


def get_stt(container: ServiceContainer = Depends(get_container)) -> SpeechToTextProvider:
    return container.stt


def get_tts(container: ServiceContainer = Depends(get_container)) -> TextToSpeechProvider:
    return container.tts


@dataclass
class Repositories:
    hcps: SqlHCPRepository
    resources: SqlResourceRepository
    interactions: SqlInteractionRepository
    conversations: SqlConversationRepository


def build_repositories(db: AsyncSession, capabilities: dict[str, bool]) -> Repositories:
    """Bind SQL repositories to one session. Shared by the API and the integration tests."""
    return Repositories(
        hcps=SqlHCPRepository(db),
        resources=SqlResourceRepository(db),
        interactions=SqlInteractionRepository(
            db,
            use_timescale=capabilities.get("timescaledb", False),
            use_topic_cagg=capabilities.get("topic_cagg", False),
        ),
        conversations=SqlConversationRepository(db),
    )


def build_orchestrator(settings: Settings, ai: AIProviders, repos: Repositories) -> AmbientOrchestrator:
    ion = MockIONService(repos.hcps, repos.interactions, repos.resources)
    return AmbientOrchestrator(
        intent_classifier=ai.intent,
        retriever=HybridResourceRetriever(
            repos.resources, ai.embedder, candidate_pool=settings.retrieval_candidate_pool
        ),
        generator=ai.generator,
        diff_service=ai.diff,
        context_resolver=ContextResolver(),
        memory=MemoryService(repos.interactions, repos.resources),
        personalization=PersonalizationService(ion),
        ion=ion,
        conversations=repos.conversations,
        interactions=repos.interactions,
        resources=repos.resources,
        retrieval_limit=settings.retrieval_default_limit,
    )


def get_repositories(
    db: AsyncSession = Depends(get_db), container: ServiceContainer = Depends(get_container)
) -> Repositories:
    return build_repositories(db, container.capabilities)


def get_ion(repos: Repositories = Depends(get_repositories)) -> MockIONService:
    return MockIONService(repos.hcps, repos.interactions, repos.resources)


def get_memory(repos: Repositories = Depends(get_repositories)) -> MemoryService:
    return MemoryService(repos.interactions, repos.resources)


def get_engagement_service(
    repos: Repositories = Depends(get_repositories), ion: MockIONService = Depends(get_ion)
) -> EngagementService:
    return EngagementService(repos.interactions, repos.resources, PersonalizationService(ion))


def get_orchestrator(
    container: ServiceContainer = Depends(get_container),
    repos: Repositories = Depends(get_repositories),
) -> AmbientOrchestrator:
    return build_orchestrator(container.settings, container.ai, repos)

"""Embedding providers. Dimension is always Settings.gemini_embedding_dimension."""

import hashlib
import math
import re
from typing import Protocol

from app.ai.gemini_client import GeminiClient

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    "a an the and or of to in on for with is are was were be what whats what's how i my me it this "
    "that about since last looked at did do does has have new changed".split()
)


class EmbeddingProvider(Protocol):
    dimension: int

    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    async def embed_query(self, text: str, timings: dict[str, float] | None = None) -> list[float]: ...


class GeminiEmbeddingProvider:
    def __init__(self, client: GeminiClient) -> None:
        self.client = client
        self.dimension = client.embedding_dimension

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        # TODO(ai-rag): batch in groups (API limits) and add retry/backoff for large ingests.
        return await self.client.embed(texts, task_type="RETRIEVAL_DOCUMENT")

    async def embed_query(self, text: str, timings: dict[str, float] | None = None) -> list[float]:
        (vector,) = await self.client.embed([text], task_type="RETRIEVAL_QUERY", timings=timings)
        return vector


class MockEmbeddingProvider:
    """Deterministic hashed bag-of-words embeddings.

    Not semantic, but lexical overlap produces real cosine similarity, so pgvector search
    behaves sensibly in mock mode without any API key.
    """

    def __init__(self, dimension: int) -> None:
        self.dimension = dimension

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dimension
        tokens = [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]
        features = tokens + [f"{a}_{b}" for a, b in zip(tokens, tokens[1:], strict=False)]
        for feat in features:
            digest = hashlib.md5(feat.encode(), usedforsecurity=False).digest()
            idx = int.from_bytes(digest[:4], "big") % self.dimension
            vec[idx] += 1.0 if digest[4] % 2 == 0 else -1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    async def embed_query(self, text: str, timings: dict[str, float] | None = None) -> list[float]:
        return self._embed(text)

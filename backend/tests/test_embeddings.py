"""Embedding provider tests (batching + L2 normalization)."""

from __future__ import annotations

import math
from unittest.mock import AsyncMock

import pytest

from app.ai.embeddings import GeminiEmbeddingProvider, MockEmbeddingProvider, l2_normalize
from app.errors import AppError, ErrorCode


def test_l2_normalize_unit_length() -> None:
    v = l2_normalize([3.0, 4.0])
    assert math.isclose(math.sqrt(sum(x * x for x in v)), 1.0)


async def test_mock_embeddings_are_unit_length() -> None:
    emb = MockEmbeddingProvider(32)
    vecs = await emb.embed_documents(["Novara renal impairment", "Cardexa dosing"])
    for v in vecs:
        assert len(v) == 32
        assert math.isclose(math.sqrt(sum(x * x for x in v)), 1.0, abs_tol=1e-6)


async def test_gemini_provider_batches_and_normalizes() -> None:
    client = AsyncMock()
    client.embedding_dimension = 4

    # Return unnormalized vectors in two batches of 16 max — we send 20 texts.
    async def fake_embed(texts, **_):
        return [[float(i), 0.0, 0.0, 0.0] for i, _ in enumerate(texts, start=1)]

    client.embed = AsyncMock(side_effect=fake_embed)
    provider = GeminiEmbeddingProvider(client)
    texts = [f"doc-{i}" for i in range(20)]
    vectors = await provider.embed_documents(texts)
    assert len(vectors) == 20
    assert client.embed.await_count == 2  # 16 + 4
    for v in vectors:
        assert len(v) == 4
        assert math.isclose(math.sqrt(sum(x * x for x in v)), 1.0, abs_tol=1e-6)


async def test_gemini_provider_rejects_wrong_dimension() -> None:
    client = AsyncMock()
    client.embedding_dimension = 4
    client.embed = AsyncMock(return_value=[[1.0, 2.0]])  # wrong dim
    provider = GeminiEmbeddingProvider(client)
    with pytest.raises(AppError) as exc:
        await provider.embed_documents(["x"])
    assert exc.value.code == ErrorCode.GEMINI_UNAVAILABLE

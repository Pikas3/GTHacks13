from app.ai.embeddings import EmbeddingProvider
from app.ingestion.chunker import ChunkDraft


async def embed_chunks(
    chunks: list[ChunkDraft], provider: EmbeddingProvider, *, title: str, batch_size: int = 32
) -> list[list[float]]:
    """Embed chunks with their resource title + section prepended for better retrieval context."""
    texts = [f"{title} — {c.section}\n{c.text}" for c in chunks]
    vectors: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        vectors.extend(await provider.embed_documents(texts[i : i + batch_size]))
    for v in vectors:
        if len(v) != provider.dimension:
            raise ValueError(f"embedding dimension {len(v)} != configured {provider.dimension}")
    return vectors

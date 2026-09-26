"""Section-aware chunking: never mixes sections, splits long sections on paragraph breaks.

TODO(ai-rag): tune chunk size/overlap once real Gemini embeddings are evaluated.
"""

from dataclasses import dataclass

from app.ingestion.parser import ParsedSection


@dataclass
class ChunkDraft:
    index: int
    section: str
    text: str
    page: int | None = None


def chunk_sections(sections: list[ParsedSection], max_chars: int = 900) -> list[ChunkDraft]:
    chunks: list[ChunkDraft] = []
    for section in sections:
        paragraphs = [p.strip() for p in section.text.split("\n\n") if p.strip()]
        current = ""
        for para in paragraphs:
            if current and len(current) + len(para) + 2 > max_chars:
                chunks.append(ChunkDraft(len(chunks), section.heading, current, section.page))
                current = para
            else:
                current = f"{current}\n\n{para}" if current else para
        if current:
            chunks.append(ChunkDraft(len(chunks), section.heading, current, section.page))
    return chunks

"""Section-aware chunking: never mixes sections, splits long sections on paragraph breaks.

Defaults tuned for Gemini embedding-2 at 768 dims: ~600–800 char chunks with light
overlap keep renal/dosing passages self-contained without diluting bag-of-words/semantic signal.
"""

from dataclasses import dataclass

from app.ingestion.parser import ParsedSection

# Tuned against seed corpus + live Gemini embed retrieval (Novara renal hit@1).
DEFAULT_MAX_CHARS = 750
DEFAULT_OVERLAP_CHARS = 120


@dataclass
class ChunkDraft:
    index: int
    section: str
    text: str
    page: int | None = None


def _overlap_tail(text: str, overlap: int) -> str:
    if overlap <= 0 or len(text) <= overlap:
        return text
    tail = text[-overlap:]
    # Prefer breaking at a paragraph or sentence boundary inside the overlap window.
    for sep in ("\n\n", ". ", "; "):
        idx = tail.find(sep)
        if idx != -1 and idx < len(tail) - 1:
            return tail[idx + len(sep) :].lstrip()
    return tail.lstrip()


def chunk_sections(
    sections: list[ParsedSection],
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> list[ChunkDraft]:
    """Chunk sections without crossing headings. Overlap only applies when a section is split."""
    chunks: list[ChunkDraft] = []
    for section in sections:
        paragraphs = [p.strip() for p in section.text.split("\n\n") if p.strip()]
        current = ""
        for para in paragraphs:
            if current and len(current) + len(para) + 2 > max_chars:
                chunks.append(ChunkDraft(len(chunks), section.heading, current, section.page))
                carry = _overlap_tail(current, overlap_chars)
                current = f"{carry}\n\n{para}" if carry else para
                # If carry+para still overflows, start fresh with the paragraph alone.
                if len(current) > max_chars:
                    current = para
            else:
                current = f"{current}\n\n{para}" if current else para
        if current:
            chunks.append(ChunkDraft(len(chunks), section.heading, current, section.page))
    return chunks

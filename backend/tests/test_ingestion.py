from pathlib import Path

from app.config import REPO_ROOT
from app.ingestion.chunker import DEFAULT_MAX_CHARS, DEFAULT_OVERLAP_CHARS, chunk_sections
from app.ingestion.parser import ParsedSection, parse_pdf_resource, parse_resource_file
from app.schemas.enums import ResourceType

RES = REPO_ROOT / "data" / "seed" / "resources"


def test_parse_pi_v2_front_matter_and_sections() -> None:
    r = parse_resource_file(RES / "novara-pi-v2.md")
    assert r.resource_type == ResourceType.PRESCRIBING_INFORMATION
    assert r.version == "2.0" and r.supersedes_key == "novara-pi-v1"
    assert "Renal Impairment" in [s.heading for s in r.sections]


def test_chunker_keeps_sections_separate() -> None:
    r = parse_resource_file(RES / "novara-pi-v1.md")
    chunks = chunk_sections(r.sections, max_chars=200, overlap_chars=40)
    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert {c.section for c in chunks} == {s.heading for s in r.sections}


def test_chunker_overlap_carries_context_across_splits() -> None:
    long = "First paragraph about dosing.\n\n" + ("More renal detail. " * 40) + "\n\nClosing note."
    sections = [ParsedSection("Renal Impairment", long)]
    chunks = chunk_sections(sections, max_chars=180, overlap_chars=50)
    assert len(chunks) >= 2
    # Overlap should make a later chunk share some earlier wording when split mid-section.
    assert any("renal" in c.text.lower() for c in chunks[1:])
    assert DEFAULT_MAX_CHARS == 750 and DEFAULT_OVERLAP_CHARS == 120


def test_every_seed_resource_is_labelled_synthetic() -> None:
    for path in RES.glob("*.md"):
        assert "FICTIONAL" in path.read_text(), f"{path.name} must state it is fictional"


def _write_tiny_pdf(path: Path, pages: list[str]) -> None:
    """Write a minimal multi-page PDF with Helvetica text (no external deps beyond path)."""
    objects: list[bytes] = []
    # 1: Catalog, 2: Pages, then per page: Page + Content, shared Font at end.

    def obj(n: int, body: bytes) -> bytes:
        return f"{n} 0 obj\n".encode() + body + b"\nendobj\n"

    page_objs: list[int] = []
    next_id = 3
    content_ids: list[tuple[int, int]] = []  # (page_id, content_id)
    for text in pages:
        page_id = next_id
        content_id = next_id + 1
        next_id += 2
        page_objs.append(page_id)
        content_ids.append((page_id, content_id))
        safe = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        # Two lines so heading-like ALL CAPS first token can be detected after extract
        stream = f"BT /F1 12 Tf 72 720 Td ({safe[:80]}) Tj 0 -18 Td ({safe[80:160]}) Tj ET"
        stream_b = stream.encode("latin-1", errors="replace")
        objects.append(
            obj(
                content_id,
                f"<< /Length {len(stream_b)} >>\nstream\n".encode() + stream_b + b"\nendstream",
            )
        )

    font_id = next_id
    next_id += 1
    for page_id, content_id in content_ids:
        objects.append(
            obj(
                page_id,
                (
                    f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                    f"/Contents {content_id} 0 R "
                    f"/Resources << /Font << /F1 {font_id} 0 R >> >> >>"
                ).encode(),
            )
        )
    objects.append(obj(font_id, b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"))
    kids = " ".join(f"{pid} 0 R" for pid in page_objs)
    objects.insert(0, obj(1, b"<< /Type /Catalog /Pages 2 0 R >>"))
    objects.insert(
        1,
        obj(2, f"<< /Type /Pages /Kids [{kids}] /Count {len(page_objs)} >>".encode()),
    )

    # Assemble with xref
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for o in sorted(objects, key=lambda b: int(b.split(b" ")[0])):
        offsets.append(len(out))
        out.extend(o if o.endswith(b"\n") else o + b"\n")
    # Rebuild properly by id order
    by_id: dict[int, bytes] = {}
    for o in objects:
        oid = int(o.split(b" ")[0])
        by_id[oid] = o if o.endswith(b"\n") else o + b"\n"
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i in range(1, max(by_id) + 1):
        offsets.append(len(out))
        out.extend(by_id[i])
    xref_pos = len(out)
    out.extend(f"xref\n0 {max(by_id) + 1}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for i in range(1, max(by_id) + 1):
        out.extend(f"{offsets[i]:010d} 00000 n \n".encode())
    out.extend(f"trailer<< /Size {max(by_id) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(out))


def test_parse_pdf_page_aware_with_sidecar(tmp_path: Path) -> None:
    pdf = tmp_path / "demo-pi.pdf"
    yml = tmp_path / "demo-pi.yml"
    _write_tiny_pdf(
        pdf,
        [
            "RENAL IMPAIRMENT Version 2 adds Regimen A-R for moderate renal impairment.",
            "SAFETY Category Beta monitoring during the first two placeholder cycles.",
        ],
    )
    yml.write_text(
        "\n".join(
            [
                "key: demo-pi",
                "title: Demo PI",
                "product: Novara",
                "resource_type: PRESCRIBING_INFORMATION",
                "version: 1.0",
                "published_at: 2026-08-01",
            ]
        ),
        encoding="utf-8",
    )
    parsed = parse_pdf_resource(pdf)
    assert parsed.key == "demo-pi"
    assert parsed.product == "Novara"
    assert {s.page for s in parsed.sections} == {1, 2}
    assert any(s.page == 1 for s in parsed.sections)
    assert "renal" in " ".join(s.text.lower() for s in parsed.sections)

from app.config import REPO_ROOT
from app.ingestion.chunker import chunk_sections
from app.ingestion.parser import parse_resource_file
from app.schemas.enums import ResourceType

RES = REPO_ROOT / "data" / "seed" / "resources"


def test_parse_pi_v2_front_matter_and_sections() -> None:
    r = parse_resource_file(RES / "novara-pi-v2.md")
    assert r.resource_type == ResourceType.PRESCRIBING_INFORMATION
    assert r.version == "2.0" and r.supersedes_key == "novara-pi-v1"
    assert "Renal Impairment" in [s.heading for s in r.sections]


def test_chunker_keeps_sections_separate() -> None:
    r = parse_resource_file(RES / "novara-pi-v1.md")
    chunks = chunk_sections(r.sections, max_chars=200)
    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert {c.section for c in chunks} == {s.heading for s in r.sections}


def test_every_seed_resource_is_labelled_synthetic() -> None:
    for path in RES.glob("*.md"):
        assert "FICTIONAL" in path.read_text(), f"{path.name} must state it is fictional"

"""Parse synthetic resource documents (Markdown with a simple `key: value` front matter).

TODO(ai-rag): add PDF parsing (page-aware) for real approved documents.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from app.schemas.enums import ResourceType


@dataclass
class ParsedSection:
    heading: str
    text: str
    page: int | None = None


@dataclass
class ParsedResource:
    key: str
    title: str
    product: str
    resource_type: ResourceType
    version: str
    published_at: datetime
    supersedes_key: str | None = None
    source_url: str | None = None
    is_approved: bool = True
    sections: list[ParsedSection] = field(default_factory=list)
    metadata: dict[str, str] = field(default_factory=dict)


def _parse_front_matter(raw: str) -> tuple[dict[str, str], str]:
    if not raw.startswith("---"):
        raise ValueError("resource file must start with front matter")
    _, fm, body = raw.split("---", 2)
    meta: dict[str, str] = {}
    for line in fm.strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta, body


def parse_resource_text(raw: str) -> ParsedResource:
    meta, body = _parse_front_matter(raw)
    sections: list[ParsedSection] = []
    heading, buf, page = "General", [], None
    for line in body.splitlines():
        if line.startswith("## "):
            if "".join(buf).strip():
                sections.append(ParsedSection(heading, "\n".join(buf).strip(), page))
            heading, buf = line[3:].strip(), []
        elif line.startswith("<!-- page:"):
            page = int(line.split(":", 1)[1].strip(" ->"))
        elif not line.startswith("# "):
            buf.append(line)
    if "".join(buf).strip():
        sections.append(ParsedSection(heading, "\n".join(buf).strip(), page))

    known = {
        "key",
        "title",
        "product",
        "resource_type",
        "version",
        "published_at",
        "supersedes",
        "source_url",
        "is_approved",
    }
    return ParsedResource(
        key=meta["key"],
        title=meta["title"],
        product=meta["product"],
        resource_type=ResourceType(meta["resource_type"]),
        version=meta["version"],
        published_at=datetime.fromisoformat(meta["published_at"]).replace(tzinfo=UTC),
        supersedes_key=meta.get("supersedes") or None,
        source_url=meta.get("source_url") or None,
        is_approved=meta.get("is_approved", "true").lower() == "true",
        sections=sections,
        metadata={k: v for k, v in meta.items() if k not in known},
    )


def parse_resource_file(path: Path) -> ParsedResource:
    return parse_resource_text(path.read_text(encoding="utf-8"))

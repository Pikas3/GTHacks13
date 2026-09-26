"""Parse synthetic resource documents (Markdown + optional page-aware PDFs).

Markdown uses a simple `key: value` front matter. PDFs use the same `ParsedResource`
shape: metadata from a sibling `{stem}.yml` (or PDF document info fallback), body text
extracted page-by-page with `page` set on each section.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from app.schemas.enums import ResourceType

_PAGE_MARKER = re.compile(r"^<!--\s*page:\s*(\d+)\s*-->\s*$", re.I)


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


def _meta_to_resource(meta: dict[str, str], sections: list[ParsedSection]) -> ParsedResource:
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


def _sections_from_markdown_body(body: str) -> list[ParsedSection]:
    sections: list[ParsedSection] = []
    heading, buf, page = "General", [], None
    for line in body.splitlines():
        page_match = _PAGE_MARKER.match(line.strip())
        if page_match:
            page = int(page_match.group(1))
            continue
        if line.startswith("## "):
            if "".join(buf).strip():
                sections.append(ParsedSection(heading, "\n".join(buf).strip(), page))
            heading, buf = line[3:].strip(), []
        elif not line.startswith("# "):
            buf.append(line)
    if "".join(buf).strip():
        sections.append(ParsedSection(heading, "\n".join(buf).strip(), page))
    return sections


def parse_resource_text(raw: str) -> ParsedResource:
    meta, body = _parse_front_matter(raw)
    return _meta_to_resource(meta, _sections_from_markdown_body(body))


def _load_sidecar_meta(path: Path) -> dict[str, str]:
    """Sibling `{stem}.yml` / `{stem}.yaml` with the same key: value lines as MD front matter."""
    for candidate in (path.with_suffix(".yml"), path.with_suffix(".yaml")):
        if not candidate.exists():
            continue
        raw = candidate.read_text(encoding="utf-8")
        if raw.lstrip().startswith("---"):
            text = raw if raw.startswith("---") else f"---\n{raw.strip()}\n---\n"
            meta, _ = _parse_front_matter(text)
            return meta
        meta: dict[str, str] = {}
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip()
        return meta
    return {}


def _meta_from_pdf_info(path: Path) -> dict[str, str]:
    """Best-effort metadata from PDF info dict when no sidecar is present."""
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    info = reader.metadata or {}
    title = str(info.get("/Title") or path.stem)
    subject = str(info.get("/Subject") or "")
    meta: dict[str, str] = {
        "key": path.stem,
        "title": title,
        "product": subject or "Unknown",
        "resource_type": "EDUCATIONAL_RESOURCE",
        "version": "1.0",
        "published_at": datetime.now(UTC).date().isoformat(),
    }
    # Custom keys sometimes live in /Keywords as "key=value;product=Novara"
    keywords = str(info.get("/Keywords") or "")
    for part in re.split(r"[;,\n]", keywords):
        if "=" in part:
            k, v = part.split("=", 1)
            meta[k.strip()] = v.strip()
        elif ":" in part:
            k, v = part.split(":", 1)
            meta[k.strip()] = v.strip()
    return meta


def _sections_from_page_text(page_num: int, text: str) -> list[ParsedSection]:
    """Split a page into heading/body sections; default heading is Page N."""
    lines = [ln.rstrip() for ln in (text or "").splitlines()]
    sections: list[ParsedSection] = []
    heading = f"Page {page_num}"
    buf: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            buf.append("")
            continue
        # Markdown-style or ALL-CAPS short lines as headings
        is_md = stripped.startswith("## ")
        is_caps = bool(re.fullmatch(r"[A-Z0-9][A-Z0-9 /&-]{2,80}", stripped)) and len(stripped.split()) <= 8
        if is_md or is_caps:
            if "".join(buf).strip():
                sections.append(ParsedSection(heading, "\n".join(buf).strip(), page_num))
            heading = stripped[3:].strip() if is_md else stripped.title() if is_caps else stripped
            buf = []
        else:
            buf.append(line)
    if "".join(buf).strip():
        sections.append(ParsedSection(heading, "\n".join(buf).strip(), page_num))
    if not sections and (text or "").strip():
        sections.append(ParsedSection(f"Page {page_num}", text.strip(), page_num))
    return sections


def parse_pdf_resource(path: Path) -> ParsedResource:
    """Page-aware PDF → ParsedResource (requires `pypdf`)."""
    from pypdf import PdfReader

    meta = _load_sidecar_meta(path) or _meta_from_pdf_info(path)
    required = ("key", "title", "product", "resource_type", "version", "published_at")
    missing = [k for k in required if k not in meta or not meta[k]]
    if missing:
        raise ValueError(f"PDF {path.name} missing metadata keys {missing}; add a sibling .yml sidecar")

    reader = PdfReader(str(path))
    sections: list[ParsedSection] = []
    for i, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""
        sections.extend(_sections_from_page_text(i, text))
    if not sections:
        raise ValueError(f"PDF {path.name} produced no extractable text")
    return _meta_to_resource(meta, sections)


def parse_resource_file(path: Path) -> ParsedResource:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return parse_pdf_resource(path)
    if suffix in {".md", ".markdown", ".txt"}:
        return parse_resource_text(path.read_text(encoding="utf-8"))
    raise ValueError(f"unsupported resource format: {path.suffix}")

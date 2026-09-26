"""Turn display / answer text into speakable TTS input.

Display answers may include citation markers, markdown, and abbreviations that sound
awkward when spoken. The ambient generator stays display-oriented; this normalizer
runs only on the synthesize path.
"""

from __future__ import annotations

import re

# Brand tokens kept explicit so TTS doesn't invent syllables.
_PRONUNCIATION: dict[str, str] = {
    "Novara": "Novara",
    "Cardexa": "Cardexa",
    "Lumetrex": "Lumetrex",
}

_VERSION_RE = re.compile(r"\bv(\d+)(?:\.(\d+))?\b", re.I)
_CITATION_RE = re.compile(r"\[E\d+\]")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MD_BOLD_RE = re.compile(r"[*_`]{1,3}")
_BULLET_RE = re.compile(r"^\s*[-•*]\s+", re.M)
_MULTISPACE_RE = re.compile(r"[ \t]{2,}")
_MULTINEWLINE_RE = re.compile(r"\n{2,}")

_ABBREVIATIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bPI\b"), "prescribing information"),
    (re.compile(r"\bPIs\b"), "prescribing information documents"),
    (re.compile(r"\bHCP\b"), "healthcare professional"),
    (re.compile(r"\bHCPs\b"), "healthcare professionals"),
    (re.compile(r"\beGFR\b", re.I), "estimated G F R"),
    (re.compile(r"\bPU\b"), "placeholder units"),
    (re.compile(r"\biDFS\b", re.I), "invasive disease-free survival"),
    (re.compile(r"\bLTFU\b", re.I), "long-term follow-up"),
]


def _version_replacer(match: re.Match[str]) -> str:
    major = match.group(1)
    minor = match.group(2)
    if minor and minor != "0":
        return f"version {major} point {minor}"
    return f"version {major}"


def normalize_speech_text(text: str) -> str:
    """Return speakable text derived from a display answer."""
    out = text.strip()
    if not out:
        return out

    out = _CITATION_RE.sub("", out)
    out = _MD_LINK_RE.sub(r"\1", out)
    out = _MD_BOLD_RE.sub("", out)
    out = _BULLET_RE.sub("", out)
    out = _VERSION_RE.sub(_version_replacer, out)

    for pattern, replacement in _ABBREVIATIONS:
        out = pattern.sub(replacement, out)

    for token, spoken in _PRONUNCIATION.items():
        out = re.sub(rf"\b{re.escape(token)}\b", spoken, out)

    out = out.replace("→", " to ").replace("•", ",")
    out = _MULTINEWLINE_RE.sub(". ", out)
    out = out.replace("\n", " ")
    out = _MULTISPACE_RE.sub(" ", out)
    return out.strip(" ,;")


def first_sentence(text: str) -> tuple[str, str]:
    """Split into (first_sentence, remainder) for chunked TTS."""
    cleaned = text.strip()
    if not cleaned:
        return "", ""
    match = re.search(r"[.!?]\s+", cleaned)
    if not match:
        return cleaned, ""
    end = match.end()
    return cleaned[:end].strip(), cleaned[end:].strip()

"""Markdown-extraction helpers shared by source adapters."""

import re

import yaml

from ..fingerprints import DOC_KEYWORDS

H1_RE = re.compile(r"^# (.+)$", re.MULTILINE)
MERMAID_RE = re.compile(r"```mermaid\n(.*?)```", re.DOTALL)


def parse_frontmatter(text: str) -> tuple[dict, str]:
    if text.startswith("---\n"):
        end = text.find("\n---\n", 4)
        if end != -1:
            meta = yaml.safe_load(text[4:end]) or {}
            return meta, text[end + 5 :]
    return {}, text


def h1_title(body: str, fallback: str) -> str:
    m = H1_RE.search(body)
    return m.group(1).strip() if m else fallback


def first_mermaid(body: str) -> str | None:
    m = MERMAID_RE.search(body)
    return m.group(1).strip() if m else None


def first_paragraph(body: str) -> str:
    """First prose paragraph of a Markdown body — the fallback description
    for docs without one in their frontmatter."""
    for block in body.split("\n\n"):
        block = block.strip()
        if not block or block.startswith(("#", "```", "<", "|", "-", ">", "![", "[")):
            continue
        return re.sub(r"\s+", " ", block)
    return ""


def fingerprint_text(text: str) -> list[str]:
    """Detect components from prose (title/description keywords) — the only
    detection available for chapters without lab code."""
    lowered = text.lower()
    detected: set[str] = set()
    for keyword, comps in DOC_KEYWORDS.items():
        if keyword in lowered:
            detected.update(comps)
    return sorted(detected)

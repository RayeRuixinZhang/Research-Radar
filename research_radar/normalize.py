from __future__ import annotations

import html
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.I)
ISSN_RE = re.compile(r"^\d{4}-?\d{3}[\dXx]$")
TAG_RE = re.compile(r"<[^>]+>")
SENTENCE_RE = re.compile(r"(?<=[.!?。！？])\s+")


def normalize_doi(value: str) -> str:
    match = DOI_RE.search(value or "")
    return match.group(0).rstrip(".,;:)").lower() if match else ""


def normalize_issn(value: str) -> str:
    value = (value or "").strip().upper().replace("-", "")
    if not ISSN_RE.match(value):
        return ""
    return f"{value[:4]}-{value[4:]}"


def canonical_url(value: str) -> str:
    if not value:
        return ""
    parts = urlsplit(value.strip())
    if parts.scheme not in {"http", "https"}:
        return value.strip()
    tracking = {"utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "gclid", "fbclid"}
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if k.casefold() not in tracking])
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, query, ""))


def clean_text(value: str) -> str:
    return " ".join(html.unescape(TAG_RE.sub(" ", value or "")).split())


def truncate_summary(value: str, limit: int = 250) -> str:
    text = clean_text(value)
    if len(text) <= limit:
        return text
    sentences = SENTENCE_RE.split(text)
    result = ""
    for sentence in sentences:
        candidate = f"{result} {sentence}".strip()
        if len(candidate) > limit:
            break
        result = candidate
    if result:
        return result
    return text[: max(1, limit - 1)].rstrip() + "…"


def classify(text: str, topic_config: dict) -> list[str]:
    folded = (text or "").casefold()
    labels: list[str] = []
    for key, definition in topic_config.get("categories", {}).items():
        if any(term.casefold() in folded for term in definition.get("terms", [])):
            labels.append(key)
    return labels


def matches_hotspot_scope(item, scope_config: dict) -> bool:
    """Apply the transparent second-stage scope filter to a PubMed item."""
    allowed_categories = set(scope_config.get("include_categories", []))
    if allowed_categories.intersection(item.categories):
        return True
    text = " ".join(
        [
            item.title or "",
            item.summary or "",
            " ".join(item.mesh_terms),
            item.primary_topic or "",
        ]
    ).casefold()
    return any(term.casefold() in text for term in scope_config.get("include_terms", []))

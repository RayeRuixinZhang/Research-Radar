from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(slots=True)
class ResearchItem:
    kind: str
    source_id: str
    source_name: str
    title: str
    summary: str
    url: str
    published_at: str
    retrieved_at: str = field(default_factory=utc_now)
    doi: str = ""
    pmid: str = ""
    journal: str = ""
    issns: list[str] = field(default_factory=list)
    language: str = ""
    country: str = ""
    categories: list[str] = field(default_factory=list)
    mesh_terms: list[str] = field(default_factory=list)
    primary_topic: str = ""
    citation_percentile: float = 0.0
    is_retracted: bool = False
    content_hash: str = ""
    provenance: dict[str, Any] = field(default_factory=dict)

    def finalize(self) -> "ResearchItem":
        from .normalize import canonical_url, normalize_doi, normalize_issn, truncate_summary

        self.title = " ".join((self.title or "").split())
        self.summary = truncate_summary(self.summary or "", 250)
        self.doi = normalize_doi(self.doi)
        self.issns = sorted({x for value in self.issns if (x := normalize_issn(value))})
        self.url = canonical_url(self.url)
        identity = self.doi or self.pmid or self.url or self.title.casefold()
        self.content_hash = sha256(
            json.dumps(
                {
                    "identity": identity,
                    "title": self.title,
                    "published_at": self.published_at,
                    "source": self.source_id,
                },
                ensure_ascii=False,
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        return self

    @property
    def item_id(self) -> str:
        identity = self.doi or self.pmid or self.url or self.content_hash
        return sha256(f"{self.kind}:{identity}".encode("utf-8")).hexdigest()[:24]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["item_id"] = self.item_id
        return data


@dataclass(slots=True)
class SourceStatus:
    source_id: str
    section: str
    status: str
    item_count: int = 0
    error: str = ""
    checked_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Hotspot:
    topic: str
    score: float
    paper_count: int
    journal_count: int
    mesh_terms: list[str]
    papers: list[ResearchItem]

    def to_dict(self) -> dict[str, Any]:
        return {
            "topic": self.topic,
            "score": self.score,
            "paper_count": self.paper_count,
            "journal_count": self.journal_count,
            "mesh_terms": self.mesh_terms,
            "papers": [paper.to_dict() for paper in self.papers],
        }


from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from typing import Iterable

from .models import ResearchItem, SourceStatus, utc_now

SCHEMA = """
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS items (
  item_id TEXT PRIMARY KEY,
  kind TEXT NOT NULL,
  source_id TEXT NOT NULL,
  title TEXT NOT NULL,
  summary TEXT NOT NULL,
  url TEXT NOT NULL,
  doi TEXT,
  pmid TEXT,
  journal TEXT,
  issns_json TEXT NOT NULL,
  published_at TEXT NOT NULL,
  retrieved_at TEXT NOT NULL,
  language TEXT,
  country TEXT,
  categories_json TEXT NOT NULL,
  mesh_json TEXT NOT NULL,
  primary_topic TEXT,
  citation_percentile REAL DEFAULT 0,
  is_retracted INTEGER DEFAULT 0,
  content_hash TEXT NOT NULL,
  provenance_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_kind_date ON items(kind, published_at DESC);
CREATE INDEX IF NOT EXISTS idx_items_doi ON items(doi);
CREATE TABLE IF NOT EXISTS source_runs (
  run_id TEXT NOT NULL,
  source_id TEXT NOT NULL,
  section TEXT NOT NULL,
  status TEXT NOT NULL,
  item_count INTEGER NOT NULL,
  error TEXT,
  checked_at TEXT NOT NULL,
  PRIMARY KEY (run_id, source_id, section)
);
CREATE TABLE IF NOT EXISTS reports (
  report_key TEXT PRIMARY KEY,
  path TEXT NOT NULL,
  manifest_path TEXT NOT NULL,
  generated_at TEXT NOT NULL,
  item_count INTEGER NOT NULL,
  commit_sha TEXT
);
CREATE TABLE IF NOT EXISTS raw_artifacts (
  run_id TEXT NOT NULL,
  source_id TEXT NOT NULL,
  r2_key TEXT NOT NULL,
  sha256 TEXT NOT NULL,
  bytes INTEGER NOT NULL,
  uploaded INTEGER NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (run_id, source_id, sha256)
);
"""


class Storage:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with self.connect() as con:
            con.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.path)
        con.row_factory = sqlite3.Row
        try:
            yield con
            con.commit()
        finally:
            con.close()

    def upsert_items(self, items: Iterable[ResearchItem]) -> int:
        rows = [item.finalize() for item in items]
        with self.connect() as con:
            for item in rows:
                con.execute(
                    """
                    INSERT INTO items VALUES (
                      :item_id,:kind,:source_id,:title,:summary,:url,:doi,:pmid,:journal,
                      :issns_json,:published_at,:retrieved_at,:language,:country,:categories_json,
                      :mesh_json,:primary_topic,:citation_percentile,:is_retracted,:content_hash,
                      :provenance_json,:updated_at
                    )
                    ON CONFLICT(item_id) DO UPDATE SET
                      title=excluded.title, summary=excluded.summary, url=excluded.url,
                      doi=excluded.doi, journal=excluded.journal, issns_json=excluded.issns_json,
                      categories_json=excluded.categories_json, mesh_json=excluded.mesh_json,
                      primary_topic=excluded.primary_topic,
                      citation_percentile=excluded.citation_percentile,
                      is_retracted=excluded.is_retracted, content_hash=excluded.content_hash,
                      provenance_json=excluded.provenance_json, updated_at=excluded.updated_at
                    """,
                    {
                        **item.to_dict(),
                        "issns_json": json.dumps(item.issns, ensure_ascii=False),
                        "categories_json": json.dumps(item.categories, ensure_ascii=False),
                        "mesh_json": json.dumps(item.mesh_terms, ensure_ascii=False),
                        "provenance_json": json.dumps(item.provenance, ensure_ascii=False, sort_keys=True),
                        "is_retracted": int(item.is_retracted),
                        "updated_at": utc_now(),
                    },
                )
        return len(rows)

    def save_statuses(self, run_id: str, statuses: Iterable[SourceStatus]) -> None:
        with self.connect() as con:
            for status in statuses:
                con.execute(
                    "INSERT OR REPLACE INTO source_runs VALUES (?,?,?,?,?,?,?)",
                    (
                        run_id,
                        status.source_id,
                        status.section,
                        status.status,
                        status.item_count,
                        status.error,
                        status.checked_at,
                    ),
                )

    def load_items(self, kind: str | None = None, since: str | None = None) -> list[ResearchItem]:
        where, args = [], []
        if kind:
            where.append("kind = ?")
            args.append(kind)
        if since:
            where.append("published_at >= ?")
            args.append(since)
        sql = "SELECT * FROM items" + (f" WHERE {' AND '.join(where)}" if where else "") + " ORDER BY published_at DESC"
        with self.connect() as con:
            rows = con.execute(sql, args).fetchall()
        result = []
        for row in rows:
            result.append(
                ResearchItem(
                    kind=row["kind"], source_id=row["source_id"], source_name=row["source_id"],
                    title=row["title"], summary=row["summary"], url=row["url"], doi=row["doi"] or "",
                    pmid=row["pmid"] or "", journal=row["journal"] or "",
                    issns=json.loads(row["issns_json"]), published_at=row["published_at"],
                    retrieved_at=row["retrieved_at"], language=row["language"] or "",
                    country=row["country"] or "", categories=json.loads(row["categories_json"]),
                    mesh_terms=json.loads(row["mesh_json"]), primary_topic=row["primary_topic"] or "",
                    citation_percentile=float(row["citation_percentile"] or 0),
                    is_retracted=bool(row["is_retracted"]), content_hash=row["content_hash"],
                    provenance=json.loads(row["provenance_json"]),
                )
            )
        return result

    def latest_statuses(self) -> list[SourceStatus]:
        with self.connect() as con:
            row = con.execute("SELECT run_id FROM source_runs ORDER BY checked_at DESC LIMIT 1").fetchone()
            if not row:
                return []
            rows = con.execute(
                "SELECT * FROM source_runs WHERE run_id = ? ORDER BY section, source_id", (row["run_id"],)
            ).fetchall()
        return [
            SourceStatus(
                source_id=value["source_id"],
                section=value["section"],
                status=value["status"],
                item_count=value["item_count"],
                error=value["error"] or "",
                checked_at=value["checked_at"],
            )
            for value in rows
        ]

    def save_raw_artifact(self, run_id: str, artifact: dict) -> None:
        with self.connect() as con:
            con.execute(
                "INSERT OR REPLACE INTO raw_artifacts VALUES (?,?,?,?,?,?,?)",
                (
                    run_id,
                    artifact["source_id"],
                    artifact["r2_key"],
                    artifact["sha256"],
                    artifact["bytes"],
                    int(artifact["uploaded"]),
                    utc_now(),
                ),
            )

    def latest_raw_artifacts(self) -> list[dict]:
        with self.connect() as con:
            row = con.execute("SELECT run_id FROM raw_artifacts ORDER BY created_at DESC LIMIT 1").fetchone()
            if not row:
                return []
            rows = con.execute(
                "SELECT * FROM raw_artifacts WHERE run_id = ? ORDER BY source_id", (row["run_id"],)
            ).fetchall()
        return [
            {
                "source_id": value["source_id"],
                "r2_key": value["r2_key"],
                "sha256": value["sha256"],
                "bytes": value["bytes"],
                "uploaded": bool(value["uploaded"]),
            }
            for value in rows
        ]

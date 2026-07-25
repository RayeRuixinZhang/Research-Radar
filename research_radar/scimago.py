from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import re

from .normalize import normalize_issn


HEADER_ALIASES = {
    "title": {"title", "journaltitle", "sourcetitle"},
    "issn": {"issn", "issns"},
    "quartile": {"quartile", "bestquartile", "sjrbestquartile"},
    "year": {"year", "datayear"},
    "area": {"area", "areas", "subjectarea", "subjectareas"},
}
ISSN_FINDER = re.compile(r"\d{4}-?\d{3}[\dXx]")
YEAR_FINDER = re.compile(r"\b(20\d{2})\b")


def _header_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").casefold())


def _decode_csv(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-16", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("SCImago CSV encoding is not supported")


def _reader(text: str) -> csv.DictReader:
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return csv.DictReader(io.StringIO(text), dialect=dialect)


def _column_map(fieldnames: list[str]) -> dict[str, str]:
    normalized = {_header_key(name): name for name in fieldnames if name}
    result: dict[str, str] = {}
    for canonical, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                result[canonical] = normalized[alias]
                break
    missing = {"title", "issn", "quartile"} - result.keys()
    if missing:
        raise ValueError(
            "SCImago CSV is missing required column(s): "
            + ", ".join(sorted(missing))
            + f". Found: {', '.join(fieldnames)}"
        )
    return result


def import_scimago(source: Path, root: Path, year: int | None = None) -> dict:
    """Import an official SCImago export into the canonical Q1 reference files."""
    source = source.resolve()
    raw = source.read_bytes()
    reader = _reader(_decode_csv(raw))
    columns = _column_map(list(reader.fieldnames or []))
    rows: list[dict[str, str]] = []
    observed_years: set[int] = set()
    seen: set[tuple[str, str]] = set()

    for row in reader:
        if (row.get(columns["quartile"]) or "").strip().upper() != "Q1":
            continue
        area_column = columns.get("area")
        area = (row.get(area_column) or "").strip() if area_column else ""
        if area and "medicine" not in area.casefold():
            continue
        issns = {
            normalized
            for match in ISSN_FINDER.findall(row.get(columns["issn"]) or "")
            if (normalized := normalize_issn(match))
        }
        title = (row.get(columns["title"]) or "").strip()
        if not title or not issns:
            continue
        year_column = columns.get("year")
        year_text = (row.get(year_column) or "").strip() if year_column else ""
        if match := YEAR_FINDER.search(year_text):
            observed_years.add(int(match.group(1)))
        joined_issns = ";".join(sorted(issns))
        identity = (title.casefold(), joined_issns)
        if identity in seen:
            continue
        seen.add(identity)
        rows.append(
            {
                "title": title,
                "issn": joined_issns,
                "quartile": "Q1",
                "year": str(year or (int(year_text) if year_text.isdigit() else "")),
            }
        )

    if not rows:
        raise ValueError("No Medicine Q1 journals with valid ISSNs were found in the CSV")

    inferred_year = year or (max(observed_years) if observed_years else None)
    if inferred_year is None:
        if match := YEAR_FINDER.search(source.name):
            inferred_year = int(match.group(1))
    for row in rows:
        if not row["year"] and inferred_year:
            row["year"] = str(inferred_year)

    reference = root / "reference"
    reference.mkdir(parents=True, exist_ok=True)
    target = reference / "scimago_q1_medicine.csv"
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["title", "issn", "quartile", "year"])
        writer.writeheader()
        writer.writerows(sorted(rows, key=lambda item: item["title"].casefold()))

    all_issns = {
        value
        for row in rows
        for value in row["issn"].split(";")
        if value
    }
    metadata = {
        "status": "ready",
        "metric": "SCImago Journal Rank",
        "area": "Medicine",
        "quartile": "Q1",
        "is_jcr": False,
        "source_url": "https://www.scimagojr.com/journalrank.php?area=2700",
        "data_year": inferred_year,
        "downloaded_at": datetime.now(timezone.utc).isoformat(),
        "source_filename": source.name,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "journal_count": len(rows),
        "issn_count": len(all_issns),
        "transform_version": "scimago-import-v1",
    }
    (reference / "scimago_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return metadata

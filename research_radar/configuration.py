from __future__ import annotations

from pathlib import Path
import csv
import json
import os
from typing import Any

import yaml


class Config:
    def __init__(self, root: Path | None = None):
        self.root = (root or Path.cwd()).resolve()
        self.settings = self._yaml("config/settings.yaml")
        self.sources = self._yaml("config/sources.yaml")
        self.topics = self._yaml("config/topics.yaml")
        self.journals = self._yaml("config/journals.yaml")

    def _yaml(self, relative: str) -> dict[str, Any]:
        with (self.root / relative).open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}

    def journal_aliases(self) -> list[str]:
        values: list[str] = []
        for group in ("main", "selected"):
            for journal in self.journals.get(group, []):
                values.extend(journal.get("aliases", []))
                values.append(journal["name"])
        return sorted(set(values))

    def scimago_issns(self) -> set[str]:
        from .normalize import normalize_issn

        path = self.root / "reference/scimago_q1_medicine.csv"
        values: set[str] = set()
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                if (row.get("quartile") or "").upper() != "Q1":
                    continue
                for raw in (row.get("issn") or "").replace(",", ";").split(";"):
                    if normalized := normalize_issn(raw):
                        values.add(normalized)
        return values

    def scimago_metadata(self) -> dict[str, Any]:
        return json.loads((self.root / "reference/scimago_metadata.json").read_text(encoding="utf-8"))

    def env(self, key: str, default: str = "") -> str:
        return os.environ.get(key, default)


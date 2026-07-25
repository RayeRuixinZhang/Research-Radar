from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from .configuration import Config
from .pipeline import Pipeline, _run_id
from .remote import RawArchive
from .scimago import import_scimago
from .storage import Storage


def _runtime(root: Path) -> tuple[Config, Storage, RawArchive, Pipeline]:
    config = Config(root)
    db_path = root / config.settings["storage"]["sqlite_path"]
    archive = RawArchive(root, config.settings["storage"]["r2_prefix"], _run_id())
    if not db_path.exists():
        archive.restore_database(db_path)
    storage = Storage(db_path)
    return config, storage, archive, Pipeline(config, storage, archive)


def doctor(config: Config) -> int:
    checks = {
        "python": sys.version.split()[0],
        "root": str(config.root),
        "sources": len(config.sources.get("news", [])) + len(config.sources.get("agencies", [])),
        "journals": len(config.journals.get("main", [])) + len(config.journals.get("selected", [])),
        "scimago_q1_issns": len(config.scimago_issns()),
        "openalex_key": bool(os.getenv("OPENALEX_API_KEY")),
        "r2_configured": all(os.getenv(key) for key in ("S3_BUCKET_NAME", "S3_ACCESS_KEY_ID", "S3_SECRET_ACCESS_KEY")),
        "email_configured": all(os.getenv(key) for key in ("EMAIL_FROM", "EMAIL_PASSWORD", "EMAIL_TO")),
        "ai_enabled": bool(config.settings.get("ai", {}).get("enabled")),
        "ai_provider": config.settings.get("ai", {}).get("provider", ""),
        "ai_model": config.settings.get("ai", {}).get("model", ""),
        "deepseek_key": bool(os.getenv("DEEPSEEK_API_KEY")),
    }
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    if checks["scimago_q1_issns"] == 0:
        print("WARNING: SCImago Q1 reference is empty; hotspot board will be marked unavailable.")
    if not checks["openalex_key"]:
        print("WARNING: OPENALEX_API_KEY is missing; citation/topic enrichment will be skipped.")
    if checks["ai_enabled"] and not checks["deepseek_key"]:
        print("WARNING: DEEPSEEK_API_KEY is missing; board 5 will use the safe fallback.")
    return 0


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(prog="research-radar")
    value.add_argument("--root", type=Path, default=Path.cwd())
    sub = value.add_subparsers(dest="command", required=True)
    backfill = sub.add_parser("backfill", help="Collect the 365-day hotspot corpus")
    backfill.add_argument("--days", type=int, default=365)
    backfill.add_argument("--retmax", type=int, default=2000)
    collect = sub.add_parser("collect", help="Collect weekly papers, news and agency updates")
    collect.add_argument("--days", type=int, default=7)
    report = sub.add_parser("build-report", help="Build Markdown, manifest and static site")
    report.add_argument("--send-email", action="store_true")
    scimago = sub.add_parser("import-scimago", help="Import an official SCImago Medicine CSV export")
    scimago.add_argument("csv_path", type=Path)
    scimago.add_argument("--year", type=int, help="Data year when it cannot be inferred from the CSV")
    sub.add_parser("doctor", help="Validate configuration and optional integrations")
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = args.root.resolve()
    if args.command == "import-scimago":
        metadata = import_scimago(args.csv_path, root, args.year)
        print(json.dumps(metadata, ensure_ascii=False, indent=2))
        return 0
    config, _storage, _archive, pipeline = _runtime(root)
    if args.command == "doctor":
        return doctor(config)
    if args.command == "backfill":
        count = pipeline.backfill(args.days, args.retmax)
        print(f"Backfill stored {count} eligible SCImago Q1 papers")
        return 0
    if args.command == "collect":
        result = pipeline.collect(args.days)
        print(json.dumps({k: v for k, v in result.items() if k != "statuses"}, ensure_ascii=False))
        return 0
    if args.command == "build-report":
        paths = pipeline.build_report(args.send_email)
        print("\n".join(str(path) for path in paths))
        return 0
    return 2

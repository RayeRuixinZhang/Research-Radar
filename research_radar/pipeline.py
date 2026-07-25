from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Iterable

from .ai import analyze_cross_board
from .configuration import Config
from .mailer import send_report
from .models import ResearchItem, SourceStatus
from .remote import RawArchive
from .reporting import build_markdown, write_report
from .scoring import score_hotspots
from .sources import EuropePMCEnricher, OpenAlexEnricher, PubMedSource, collect_registered_sources
from .storage import Storage


def _run_id() -> str:
    external = __import__("os").getenv("GITHUB_RUN_ID")
    return external or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _since(days: int) -> str:
    return (date.today() - timedelta(days=days)).isoformat()


def _dedupe(items: Iterable[ResearchItem]) -> list[ResearchItem]:
    result: dict[str, ResearchItem] = {}
    for item in items:
        item.finalize()
        key = item.doi or item.url or item.item_id
        existing = result.get(key)
        if not existing or (len(item.summary), item.published_at) > (len(existing.summary), existing.published_at):
            result[key] = item
    return list(result.values())


class Pipeline:
    def __init__(self, config: Config, storage: Storage, archive: RawArchive):
        self.config = config
        self.storage = storage
        self.archive = archive
        self.run_id = archive.run_id
        self.raw_artifacts: list[dict] = []

    def _archive(self, source_id: str, payload) -> None:
        artifact = self.archive.save(source_id, payload)
        self.raw_artifacts.append(artifact)
        self.storage.save_raw_artifact(self.run_id, artifact)

    def backfill(self, days: int = 365, retmax: int = 2000) -> int:
        q1 = self.config.scimago_issns()
        if not q1:
            status = SourceStatus(
                "pubmed-scimago-q1",
                "hotspots",
                "degraded",
                0,
                "SCImago Q1 ISSN reference is empty",
            )
            self.storage.save_statuses(self.run_id, [status])
            self.archive.upload_database(self.storage.path)
            return 0
        pubmed = PubMedSource(self.config.topics)
        items, raw = pubmed.collect(days=days, journal_aliases=None, retmax=retmax)
        self._archive("pubmed-hotspot", raw)
        items = [
            item for item in items
            if item.doi and not item.is_retracted and q1.intersection(item.issns)
        ]
        EuropePMCEnricher().enrich(items, max_items=100)
        openalex_raw = OpenAlexEnricher().enrich(items, max_items=retmax)
        if openalex_raw:
            self._archive("openalex-hotspot", openalex_raw)
        eligible = []
        for item in items:
            item.kind = "hotspot_paper"
            if item.doi and not item.is_retracted and q1.intersection(item.issns):
                eligible.append(item.finalize())
        status = SourceStatus(
            "pubmed-scimago-q1",
            "hotspots",
            "success" if q1 else "degraded",
            len(eligible),
            "" if q1 else "SCImago Q1 ISSN reference is empty",
        )
        self.storage.upsert_items(eligible)
        self.storage.save_statuses(self.run_id, [status])
        self.archive.upload_database(self.storage.path)
        return len(eligible)

    def collect(self, days: int = 7) -> dict:
        statuses: list[SourceStatus] = []
        print("[collect] PubMed journal search")
        pubmed = PubMedSource(self.config.topics)
        papers, academic_raw = pubmed.collect(days, self.config.journal_aliases(), retmax=200)
        self._archive("pubmed-journals", academic_raw)
        papers = [
            item for item in papers
            if item.doi and not item.is_retracted and item.categories
        ]
        EuropePMCEnricher().enrich(papers, max_items=50)
        openalex_raw = OpenAlexEnricher().enrich(papers, max_items=500)
        if openalex_raw:
            self._archive("openalex-journals", openalex_raw)
        for item in papers:
            item.kind = "journal_paper"
            item.finalize()
        statuses.append(SourceStatus("pubmed", "journals", "success", len(papers)))

        print("[collect] News and health agency sources")
        with ThreadPoolExecutor(max_workers=2) as executor:
            news_future = executor.submit(
                collect_registered_sources,
                self.config.sources.get("news", []), "news", days, self.config.topics,
            )
            agency_future = executor.submit(
                collect_registered_sources,
                self.config.sources.get("agencies", []), "agencies", days, self.config.topics,
            )
            news, news_statuses, news_raw = news_future.result()
            agencies, agency_statuses, agency_raw = agency_future.result()
        statuses.extend(news_statuses)
        statuses.extend(agency_statuses)
        for source_id, payload in news_raw.items():
            self._archive(f"news-{source_id}", payload)
        for source_id, payload in agency_raw.items():
            self._archive(f"agency-{source_id}", payload)

        cutoff = _since(days)
        news = [item for item in _dedupe(news) if item.published_at >= cutoff and item.url]
        agencies = [item for item in _dedupe(agencies) if item.published_at >= cutoff and item.url]
        self.storage.upsert_items([*papers, *news, *agencies])
        self.storage.save_statuses(self.run_id, statuses)
        self.archive.upload_database(self.storage.path)
        print(f"[collect] stored papers={len(papers)} news={len(news)} agencies={len(agencies)}")

        news_success = any(status.status == "success" for status in news_statuses)
        agency_success = any(status.status == "success" for status in agency_statuses)
        if not news_success or not agency_success:
            failed = []
            if not news_success:
                failed.append("news")
            if not agency_success:
                failed.append("agencies")
            raise RuntimeError(f"All configured sources failed for required section(s): {', '.join(failed)}")
        return {"papers": len(papers), "news": len(news), "agencies": len(agencies), "statuses": statuses}

    def build_report(self, send_email: bool = False) -> tuple[Path, Path, Path]:
        settings = self.config.settings
        hotspot_items = self.storage.load_items("hotspot_paper", _since(settings["windows"]["hotspot_days"]))
        hotspots = score_hotspots(hotspot_items, settings, self.config.scimago_issns())
        cutoff = _since(settings["windows"]["weekly_days"])
        news = self.storage.load_items("news", cutoff)[: settings["limits"]["news"]]
        agencies = self.storage.load_items("agency", cutoff)[: settings["limits"]["agencies"]]
        journals = [
            item for item in self.storage.load_items("journal_paper", cutoff) if item.doi
        ][: settings["limits"]["journals"]]
        source_names = {"pubmed": "PubMed"}
        for section in ("news", "agencies"):
            source_names.update(
                {source["id"]: source["name"] for source in self.config.sources.get(section, [])}
            )
        for item in [*hotspot_items, *news, *agencies, *journals]:
            item.source_name = source_names.get(item.source_id, item.source_id)
        statuses = self.storage.latest_statuses()
        previous_artifacts = self.storage.latest_raw_artifacts()
        analysis = analyze_cross_board(
            self.config.root, settings, hotspots, news, agencies, journals
        )
        ai_success = analysis.metadata.get("status") == "success"
        ai_status = SourceStatus(
            "deepseek",
            "ai_analysis",
            "success" if ai_success else "degraded",
            1 if ai_success else 0,
            analysis.metadata.get("error", analysis.metadata.get("status", "")),
        )
        self.storage.save_statuses(self.run_id, [ai_status])
        statuses = [
            status for status in statuses
            if not (status.source_id == "deepseek" and status.section == "ai_analysis")
        ] + [ai_status]
        if analysis.raw:
            self._archive("ai-cross-board", analysis.raw)
        markdown = build_markdown(
            hotspots,
            news,
            agencies,
            journals,
            statuses,
            self.config.scimago_metadata(),
            analysis.markdown,
        )
        all_items = [*hotspot_items, *news, *agencies, *journals]
        raw_artifacts = {
            (artifact["source_id"], artifact["sha256"]): artifact
            for artifact in [*previous_artifacts, *self.raw_artifacts]
        }.values()
        paths = write_report(
            self.config.root,
            markdown,
            all_items,
            statuses,
            list(raw_artifacts),
            analysis.metadata,
        )
        if send_email:
            send_report(paths[0], paths[2])
        return paths

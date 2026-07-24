from __future__ import annotations

from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlsplit

import feedparser

from ..models import ResearchItem, SourceStatus
from ..normalize import classify, clean_text
from .base import get_json, session

GDELT = "https://api.gdeltproject.org/api/v2/doc/doc"


def _feed_date(entry: dict) -> str:
    for key in ("published_parsed", "updated_parsed"):
        value = entry.get(key)
        if value:
            return datetime(*value[:6], tzinfo=timezone.utc).date().isoformat()
    for key in ("published", "updated"):
        value = entry.get(key)
        if value:
            try:
                return parsedate_to_datetime(value).date().isoformat()
            except (TypeError, ValueError):
                pass
    return datetime.now(timezone.utc).date().isoformat()


def collect_rss(source: dict, section: str, topic_config: dict) -> tuple[list[ResearchItem], dict]:
    response = session().get(source["url"], timeout=15)
    response.raise_for_status()
    parsed = feedparser.parse(response.content)
    if parsed.bozo and not parsed.entries:
        raise RuntimeError(str(parsed.bozo_exception))
    kind = "news" if section == "news" else "agency"
    items = []
    for entry in parsed.entries:
        title = clean_text(entry.get("title", ""))
        summary = clean_text(entry.get("summary", "") or entry.get("description", ""))
        categories = classify(f"{title} {summary}", topic_config)
        if not categories:
            continue
        link = entry.get("link", "")
        items.append(
            ResearchItem(
                kind=kind,
                source_id=source["id"],
                source_name=source["name"],
                title=title,
                summary=summary,
                url=link,
                published_at=_feed_date(entry),
                language=parsed.feed.get("language", ""),
                country=source.get("country", ""),
                categories=categories,
                provenance={"adapter": "rss", "feed_url": source["url"]},
            ).finalize()
        )
    raw = {"feed": dict(parsed.feed), "entries": [dict(entry) for entry in parsed.entries]}
    return items, raw


def collect_gdelt(source: dict, section: str, days: int, topic_config: dict) -> tuple[list[ResearchItem], dict]:
    topic_terms = '(health OR medical OR disease OR outbreak OR hospital OR vaccine OR "artificial intelligence")'
    query = f"domainis:{source['domain']} {source.get('query', topic_terms)}"
    payload = get_json(
        GDELT,
        {
            "query": query,
            "mode": "artlist",
            "format": "json",
            "maxrecords": 100,
            "timespan": f"{max(1, days)}d",
            "sort": "datedesc",
        },
        timeout=12,
    )
    kind = "news" if section == "news" else "agency"
    items = []
    for article in payload.get("articles", []):
        title = clean_text(article.get("title", ""))
        summary = clean_text(article.get("snippet", "") or article.get("description", ""))
        categories = classify(f"{title} {summary}", topic_config)
        if not categories:
            continue
        seen = str(article.get("seendate", ""))
        published = f"{seen[:4]}-{seen[4:6]}-{seen[6:8]}" if len(seen) >= 8 else ""
        items.append(
            ResearchItem(
                kind=kind,
                source_id=source["id"],
                source_name=source["name"],
                title=title,
                summary=summary,
                url=article.get("url", ""),
                published_at=published,
                language=article.get("language", ""),
                country=source.get("country", ""),
                categories=categories,
                provenance={
                    "adapter": "gdelt-discovery",
                    "original_domain": urlsplit(article.get("url", "")).netloc,
                    "gdelt_sourcecountry": article.get("sourcecountry", ""),
                },
            ).finalize()
        )
    return items, payload


def collect_registered_sources(
    sources: list[dict], section: str, days: int, topic_config: dict
) -> tuple[list[ResearchItem], list[SourceStatus], dict]:
    items: list[ResearchItem] = []
    statuses: list[SourceStatus] = []
    raw: dict[str, dict] = {}
    def run(source: dict):
        try:
            if source.get("mode") == "rss":
                collected, payload = collect_rss(source, section, topic_config)
            else:
                collected, payload = collect_gdelt(source, section, days, topic_config)
            return source, collected, payload, None
        except Exception as exc:
            return source, [], None, exc

    with ThreadPoolExecutor(max_workers=min(8, max(1, len(sources)))) as executor:
        futures = [executor.submit(run, source) for source in sources]
        for future in as_completed(futures):
            source, collected, payload, error = future.result()
            if error is None:
                items.extend(collected)
                raw[source["id"]] = payload
                statuses.append(SourceStatus(source["id"], section, "success", len(collected)))
            else:
                statuses.append(
                    SourceStatus(source["id"], section, "failed", 0, f"{type(error).__name__}: {error}")
                )
    return items, statuses, raw

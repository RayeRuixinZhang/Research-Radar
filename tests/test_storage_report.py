import json
from pathlib import Path

from research_radar.models import ResearchItem, SourceStatus
from research_radar.reporting import build_markdown, write_report
from research_radar.storage import Storage


def sample(kind: str, item_id: int, doi: str = "") -> ResearchItem:
    return ResearchItem(
        kind=kind, source_id="source", source_name="Source", title=f"Title {item_id}",
        summary="Short summary.", url=f"https://example.org/{item_id}", doi=doi,
        journal="Journal", published_at="2026-07-20", categories=["medicine"],
    ).finalize()


def test_storage_is_idempotent(tmp_path: Path):
    store = Storage(tmp_path / "radar.db")
    item = sample("news", 1)
    assert store.upsert_items([item]) == 1
    assert store.upsert_items([item]) == 1
    assert len(store.load_items("news")) == 1
    assert store.delete_items("news") == 1
    assert store.load_items("news") == []


def test_golden_report_and_manifest(tmp_path: Path):
    news = sample("news", 1)
    agency = sample("agency", 2)
    paper = sample("journal_paper", 3, "10.1000/test")
    status = SourceStatus("source", "news", "success", 1)
    markdown = build_markdown([], [news], [agency], [paper], [status], {"status": "test"})
    assert all(f"## {index}." in markdown for index in range(1, 6))
    assert "AI 分析尚未配置" in markdown
    assert markdown.index("## 1. 重点期刊近期论文") < markdown.index("## 4. 近一年专题科研热点")
    assert "DOI: 10.1000/test" in markdown
    assert "医疗" in markdown
    assert "![" not in markdown
    report, manifest, site = write_report(
        tmp_path,
        markdown,
        [news, agency, paper],
        [status],
        [],
        {"status": "disabled"},
        {"version": "test-scope"},
    )
    assert report.exists() and site.exists()
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert len(payload["items"]) == 3
    assert all(value["content_hash"] for value in payload["items"])
    assert payload["ai_analysis"]["status"] == "disabled"
    assert payload["hotspot_scope"]["version"] == "test-scope"

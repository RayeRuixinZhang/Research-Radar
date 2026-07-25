from __future__ import annotations

from datetime import date, datetime, timezone
from html import escape
import json
from pathlib import Path
import re
import subprocess

from .models import Hotspot, ResearchItem, SourceStatus

CATEGORY_LABELS = {
    "public_health": "公共卫生",
    "medicine": "医疗",
    "health_services": "卫生服务",
    "infectious_disease": "传染病",
    "medical_ai": "医疗与AI",
    "pediatrics": "儿科学",
    "respiratory": "呼吸道疾病",
    "infection_control": "医院感染",
}


def _tags(item: ResearchItem) -> str:
    return "、".join(CATEGORY_LABELS.get(value, value) for value in item.categories) or "未分类"


def report_key(today: date | None = None) -> tuple[str, int, int]:
    current = today or date.today()
    year, week, _ = current.isocalendar()
    return f"{year}-W{week:02d}", year, week


def _paper_line(item: ResearchItem) -> str:
    doi = f"[DOI: {item.doi}](https://doi.org/{item.doi})"
    tags = _tags(item)
    return f"- **{item.title}**  \n  {item.summary or '无可用摘要'}  \n  {item.journal} · {item.published_at} · {tags} · {doi}"


def _linked_line(item: ResearchItem) -> str:
    tags = _tags(item)
    source = item.source_name or item.source_id
    country = f" · {item.country}" if item.country else ""
    return f"- **[{item.title}]({item.url})**  \n  {item.summary or '无可用摘要'}  \n  {source}{country} · {item.published_at} · {tags}"


def build_markdown(
    hotspots: list[Hotspot],
    news: list[ResearchItem],
    agencies: list[ResearchItem],
    journals: list[ResearchItem],
    statuses: list[SourceStatus],
    scimago_metadata: dict,
    ai_markdown: str = "_AI 分析尚未配置。_",
) -> str:
    key, _, _ = report_key()
    lines = [
        f"# Research Radar 科研周报 · {key}",
        "",
        f"> 生成时间：{datetime.now(timezone.utc).replace(microsecond=0).isoformat()}",
        "> 数据口径：SCImago Medicine Q1（非 JCR Q1）。标题与摘要保留原始语言。",
        "> 本报告不含图片，不转载新闻或论文全文。",
        "",
        "## 1. 近一年科研热点",
        "",
    ]
    if not hotspots:
        status = scimago_metadata.get("status", "unknown")
        lines.append(f"_暂无可计算热点。SCImago 参考数据状态：`{status}`。_")
    for index, hotspot in enumerate(hotspots, 1):
        lines.extend(
            [
                f"### {index}. {hotspot.topic}",
                "",
                f"热点分数 **{hotspot.score:.3f}** · {hotspot.paper_count} 篇 · {hotspot.journal_count} 种期刊",
                "",
            ]
        )
        lines.extend(_paper_line(paper) for paper in hotspot.papers)
        lines.append("")
    lines.extend(["## 2. 医学与公共卫生新闻", ""])
    lines.extend(_linked_line(item) for item in news) if news else lines.append("_本周未检索到符合条件的新闻。_")
    lines.extend(["", "## 3. 世界及主要国家卫生机构动态", ""])
    lines.extend(_linked_line(item) for item in agencies) if agencies else lines.append("_本周未检索到符合条件的机构动态。_")
    lines.extend(["", "## 4. 重点期刊近期论文", ""])
    lines.extend(_paper_line(item) for item in journals) if journals else lines.append("_本周未检索到符合条件且带 DOI 的重点期刊论文。_")
    lines.extend(
        [
            "",
            "## 5. 跨板块科研启发",
            "",
            ai_markdown,
            "",
            "## 数据源运行状态",
            "",
            "| 来源 | 板块 | 状态 | 条目 | 说明 |",
            "|---|---|---:|---:|---|",
        ]
    )
    for status in statuses:
        lines.append(
            f"| {status.source_id} | {status.section} | {status.status} | {status.item_count} | {status.error.replace('|', '/')[:160]} |"
        )
    lines.extend(["", "---", "", "Research Radar · GPL-3.0-or-later · 所有条目均可追溯至原始来源。", ""])
    return "\n".join(lines)


def markdown_to_html(markdown: str, history: list[str]) -> str:
    body: list[str] = []
    in_list = False
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if line.startswith("- "):
            if not in_list:
                body.append("<ul>")
                in_list = True
            text = line[2:]
            text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escape(text))
            text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2" rel="noopener">\1</a>', text)
            body.append(f"<li>{text}</li>")
            continue
        if in_list:
            body.append("</ul>")
            in_list = False
        if not line:
            continue
        if line.startswith("#"):
            level = min(3, len(line) - len(line.lstrip("#")))
            body.append(f"<h{level}>{escape(line[level:].strip())}</h{level}>")
        elif line.startswith(">"):
            body.append(f"<p class=\"note\">{escape(line.lstrip('> ').rstrip())}</p>")
        elif line.startswith("|") or line == "---":
            continue
        else:
            text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escape(line))
            text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2" rel="noopener">\1</a>', text)
            body.append(f"<p>{text}</p>")
    if in_list:
        body.append("</ul>")
    history_html = "".join(f"<li><a href=\"reports/{escape(name)}.html\">{escape(name)}</a></li>" for name in history)
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Research Radar</title><style>
:root{{--ink:#172033;--muted:#64748b;--line:#dce3ec;--accent:#0f766e;--paper:#fff;--bg:#f5f7fa}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.72 system-ui,-apple-system,"Segoe UI",sans-serif}}
main{{max-width:980px;margin:auto;padding:40px 24px 80px}}article,aside{{background:var(--paper);border:1px solid var(--line);border-radius:14px;padding:28px;margin-bottom:20px}}
h1{{font-size:2rem}}h2{{border-top:1px solid var(--line);padding-top:26px;margin-top:36px}}h3{{color:var(--accent)}}
a{{color:var(--accent)}}li{{margin:.65rem 0}}.note{{color:var(--muted);margin:.2rem 0}}code{{background:#eef2f7;padding:.1rem .3rem;border-radius:4px}}
</style></head><body><main><article>{''.join(body)}</article>
<aside><h2>历史周报</h2><ul>{history_html}</ul></aside></main></body></html>"""


def git_sha(root: Path) -> str:
    try:
        return subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return ""


def write_report(
    root: Path,
    markdown: str,
    items: list[ResearchItem],
    statuses: list[SourceStatus],
    raw_artifacts: list[dict],
    ai_metadata: dict | None = None,
) -> tuple[Path, Path, Path]:
    key, year, _ = report_key()
    report_path = root / "reports" / str(year) / f"{key}.md"
    manifest_path = root / "manifests" / str(year) / f"{key}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(markdown, encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "report_key": key,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "git_commit": git_sha(root),
        "github_run_id": __import__("os").getenv("GITHUB_RUN_ID", ""),
        "items": [
            {
                "item_id": item.item_id,
                "source_id": item.source_id,
                "url": item.url,
                "doi": item.doi,
                "retrieved_at": item.retrieved_at,
                "content_hash": item.content_hash,
            }
            for item in items
        ],
        "source_statuses": [status.to_dict() for status in statuses],
        "raw_artifacts": raw_artifacts,
        "ai_analysis": ai_metadata or {"status": "not_configured"},
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    site = root / "_site"
    (site / "reports").mkdir(parents=True, exist_ok=True)
    history = sorted(path.stem for path in (root / "reports").glob("*/*.md") if path.stem)
    html = markdown_to_html(markdown, history)
    index_path = site / "index.html"
    index_path.write_text(html, encoding="utf-8")
    (site / "reports" / f"{key}.html").write_text(html, encoding="utf-8")
    (site / ".nojekyll").write_text("", encoding="utf-8")
    return report_path, manifest_path, index_path

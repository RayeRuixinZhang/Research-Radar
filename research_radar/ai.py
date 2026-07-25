from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any

import requests

from .models import Hotspot, ResearchItem


PROMPT_VERSION = "cross-board-zh-v2"
EXPECTED_SECTIONS = (
    "cross_board_themes",
    "epidemiology_implications",
    "research_questions",
    "candidate_methods",
    "evidence_limitations",
)


@dataclass(slots=True)
class AIAnalysis:
    markdown: str
    metadata: dict[str, Any]
    raw: dict[str, Any] | None = None


def _item_payload(ref: str, item: ResearchItem, board: int) -> dict[str, Any]:
    return {
        "ref": ref,
        "board": board,
        "title": item.title,
        "summary": item.summary,
        "source": item.source_name or item.source_id,
        "published_at": item.published_at,
        "categories": item.categories,
        "doi": item.doi,
        "url": item.url,
    }


def _analysis_input(
    hotspots: list[Hotspot],
    news: list[ResearchItem],
    agencies: list[ResearchItem],
    journals: list[ResearchItem],
) -> tuple[dict[str, Any], dict[str, dict[str, str]]]:
    references: dict[str, dict[str, str]] = {}
    hotspot_payload: list[dict[str, Any]] = []
    for index, hotspot in enumerate(hotspots, 1):
        ref = f"H{index}"
        first = hotspot.papers[0] if hotspot.papers else None
        references[ref] = {
            "title": hotspot.topic,
            "url": f"https://doi.org/{first.doi}" if first and first.doi else "",
        }
        papers = []
        for paper_index, paper in enumerate(hotspot.papers, 1):
            paper_ref = f"{ref}-P{paper_index}"
            papers.append(_item_payload(paper_ref, paper, 4))
            references[paper_ref] = {
                "title": paper.title,
                "url": f"https://doi.org/{paper.doi}" if paper.doi else paper.url,
            }
        hotspot_payload.append(
            {
                "ref": ref,
                "board": 4,
                "topic": hotspot.topic,
                "score": hotspot.score,
                "paper_count": hotspot.paper_count,
                "journal_count": hotspot.journal_count,
                "mesh_terms": hotspot.mesh_terms,
                "representative_papers": papers,
            }
        )

    def items_payload(
        prefix: str, board: int, items: list[ResearchItem]
    ) -> list[dict[str, Any]]:
        payload = []
        for index, item in enumerate(items, 1):
            ref = f"{prefix}{index}"
            payload.append(_item_payload(ref, item, board))
            url = f"https://doi.org/{item.doi}" if item.doi else item.url
            references[ref] = {"title": item.title, "url": url}
        return payload

    return (
        {
            "priority_journals": items_payload("J", 1, journals),
            "news": items_payload("N", 2, news),
            "health_agencies": items_payload("A", 3, agencies),
            "hotspots": hotspot_payload,
        },
        references,
    )


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _evidence(values: Any, references: dict[str, dict[str, str]]) -> str:
    valid = []
    for ref in values if isinstance(values, list) else []:
        if ref not in references or ref in valid:
            continue
        valid.append(ref)
    links = []
    for ref in valid[:6]:
        record = references[ref]
        title = _clean(record["title"]).replace("[", "(").replace("]", ")")
        label = f"{ref} · {title[:70]}"
        links.append(f"[{label}]({record['url']})" if record["url"] else label)
    return "；".join(links) or "模型未提供可核验的输入编号"


def _render(payload: dict[str, Any], references: dict[str, dict[str, str]]) -> str:
    lines: list[str] = []
    sections = [
        ("### 5.1 四板块综合研判", "cross_board_themes"),
        ("### 5.2 对传染病流行病学的启示", "epidemiology_implications"),
        ("### 5.3 可检验的数据驱动研究问题", "research_questions"),
        ("### 5.4 候选研究方法与数据需求", "candidate_methods"),
        ("### 5.5 证据局限", "evidence_limitations"),
    ]
    for heading, key in sections:
        lines.extend([heading, ""])
        entries = payload.get(key, [])
        if not isinstance(entries, list) or not entries:
            lines.extend(["_本项未生成有效内容。_", ""])
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if key == "cross_board_themes":
                text = f"**{_clean(entry.get('title'))}**：{_clean(entry.get('analysis'))}"
            elif key == "research_questions":
                text = f"**问题：{_clean(entry.get('question'))}**　{_clean(entry.get('rationale'))}"
            elif key == "candidate_methods":
                text = (
                    f"**{_clean(entry.get('method'))}**：{_clean(entry.get('application'))}"
                    f"；数据需求：{_clean(entry.get('data_requirements'))}"
                )
            else:
                text = _clean(entry.get("text"))
            if not text.strip("*：　；"):
                continue
            lines.append(f"- {text}  ")
            lines.append(f"  依据：{_evidence(entry.get('evidence'), references)}")
        lines.append("")
    return "\n".join(lines).strip()


def _parse_json(content: str) -> dict[str, Any]:
    text = (content or "").strip()
    if text.startswith("```"):
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    payload = json.loads(text)
    if not isinstance(payload, dict) or not any(key in payload for key in EXPECTED_SECTIONS):
        raise ValueError("DeepSeek response does not contain the expected analysis sections")
    return payload


def analyze_cross_board(
    root: Path,
    settings: dict[str, Any],
    hotspots: list[Hotspot],
    news: list[ResearchItem],
    agencies: list[ResearchItem],
    journals: list[ResearchItem],
) -> AIAnalysis:
    ai = settings.get("ai", {})
    model = ai.get("model", "deepseek-v4-flash")
    base_metadata = {
        "enabled": bool(ai.get("enabled")),
        "provider": ai.get("provider", ""),
        "model": model,
        "prompt_version": PROMPT_VERSION,
    }
    if not ai.get("enabled"):
        return AIAnalysis(
            "_AI 分析尚未配置。_",
            {**base_metadata, "status": "disabled"},
        )
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        return AIAnalysis(
            "_AI 分析尚未配置：缺少 GitHub Secret `DEEPSEEK_API_KEY`。_",
            {**base_metadata, "status": "missing_key"},
        )

    prompt = (root / ai.get("prompt_path", "prompts/cross_board_analysis_zh.md")).read_text(
        encoding="utf-8"
    )
    analysis_input, references = _analysis_input(hotspots, news, agencies, journals)
    input_json = json.dumps(analysis_input, ensure_ascii=False, separators=(",", ":"))
    request_body = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"以下是本期结构化输入，请输出 json：\n{input_json}"},
        ],
        "thinking": {"type": "disabled"},
        "response_format": {"type": "json_object"},
        "max_tokens": int(ai.get("max_tokens", 2400)),
        "stream": False,
    }
    try:
        response = requests.post(
            ai.get("endpoint", "https://api.deepseek.com/chat/completions"),
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=request_body,
            timeout=int(ai.get("timeout_seconds", 120)),
        )
        response.raise_for_status()
        response_payload = response.json()
        content = response_payload["choices"][0]["message"]["content"]
        parsed = _parse_json(content)
        markdown = _render(parsed, references)
        if not markdown:
            raise ValueError("DeepSeek returned no renderable analysis")
        metadata = {
            **base_metadata,
            "status": "success",
            "response_id": response_payload.get("id", ""),
            "input_sha256": sha256(input_json.encode("utf-8")).hexdigest(),
            "input_counts": {
                "hotspots": len(hotspots),
                "news": len(news),
                "agencies": len(agencies),
                "journals": len(journals),
            },
            "usage": response_payload.get("usage", {}),
        }
        return AIAnalysis(
            markdown,
            metadata,
            {
                "request": {
                    "model": model,
                    "prompt_version": PROMPT_VERSION,
                    "input": analysis_input,
                    "thinking": "disabled",
                    "max_tokens": request_body["max_tokens"],
                },
                "response": response_payload,
                "metadata": metadata,
            },
        )
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:300]
        return AIAnalysis(
            f"_本期 DeepSeek 分析生成失败：{error}。板块1–4不受影响。_",
            {**base_metadata, "status": "failed", "error": error},
        )

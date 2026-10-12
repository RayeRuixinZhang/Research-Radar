from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any

import requests

from .models import Hotspot, ResearchItem


PROMPT_VERSION = "cross-board-zh-v3"
EXPECTED_SECTIONS = (
    "cross_board_themes",
    "epidemiology_implications",
    "research_questions",
    "candidate_methods",
    "evidence_limitations",
)
FORBIDDEN_DRAFT_MARKERS = (
    "删除此条",
    "修正：",
    "改为：",
    "自检发现",
    "此处应为",
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
        "summary": item.summary[:1200],
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
                "trend": hotspot.trend,
                "why_it_matters": hotspot.why_it_matters,
                "research_designs": hotspot.research_designs,
                "methods": hotspot.methods,
                "research_gap": hotspot.research_gap,
                "potential_phd_question": hotspot.potential_phd_question,
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


def _contains_draft_markers(payload: dict[str, Any]) -> bool:
    text = json.dumps(payload, ensure_ascii=False)
    return any(marker in text for marker in FORBIDDEN_DRAFT_MARKERS)


def _hotspot_input(hotspots: list[Hotspot]) -> list[dict[str, Any]]:
    payload = []
    for index, hotspot in enumerate(hotspots, 1):
        papers = []
        for paper_index, paper in enumerate(hotspot.papers, 1):
            papers.append(
                {
                    "ref": f"H{index}-P{paper_index}",
                    "paper_id": paper.item_id,
                    "title": paper.title,
                    "abstract": paper.summary,
                    "journal": paper.journal,
                    "published_at": paper.published_at,
                    "publication_types": paper.provenance.get("publication_types", []),
                }
            )
        payload.append(
            {
                "ref": f"H{index}",
                "topic": hotspot.topic,
                "trend": hotspot.trend,
                "paper_count": hotspot.paper_count,
                "representative_papers": papers,
            }
        )
    return payload


def analyze_hotspots(
    root: Path, settings: dict[str, Any], hotspots: list[Hotspot]
) -> tuple[list[Hotspot], dict[str, Any], dict[str, Any] | None]:
    """Enrich board 4 in bounded batches; deterministic scoring remains the fallback."""
    config = settings.get("hotspot_ai", {})
    shared = settings.get("ai", {})
    model = shared.get("model", "deepseek-flash")
    metadata: dict[str, Any] = {
        "enabled": bool(config.get("enabled")), "provider": shared.get("provider", ""),
        "model": model, "status": "disabled", "batches": 0,
    }
    if not hotspots or not config.get("enabled"):
        return hotspots, metadata, None
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    if not api_key:
        metadata["status"] = "missing_key"
        return hotspots, metadata, None
    prompt_path = root / config.get("prompt_path", "prompts/hotspot_analysis_zh.md")
    prompt = prompt_path.read_text(encoding="utf-8")
    full_input = _hotspot_input(hotspots)
    input_json = json.dumps(full_input, ensure_ascii=False, separators=(",", ":"))
    cache_key = sha256(f"{model}\n{prompt}\n{input_json}".encode("utf-8")).hexdigest()
    cache_path = root / config.get("cache_dir", "output/ai-cache/hotspots") / f"{cache_key}.json"
    parsed_batches: list[dict[str, Any]] = []
    responses: list[dict[str, Any]] = []
    try:
        if cache_path.exists():
            parsed_batches = json.loads(cache_path.read_text(encoding="utf-8"))["batches"]
            metadata.update({"status": "cache_hit", "cache_key": cache_key})
        else:
            batch_size = max(1, int(config.get("batch_size", 5)))
            for offset in range(0, len(full_input), batch_size):
                batch = full_input[offset : offset + batch_size]
                response = requests.post(
                    shared.get("endpoint", "https://api.deepseek.com/chat/completions"),
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": "请分析以下结构化热点并只输出JSON：\n" + json.dumps(batch, ensure_ascii=False)},
                        ],
                        "thinking": {"type": "disabled"},
                        "response_format": {"type": "json_object"},
                        "max_tokens": int(config.get("max_tokens", 3200)),
                        "stream": False,
                    },
                    timeout=int(config.get("timeout_seconds", 120)),
                )
                response.raise_for_status()
                response_payload = response.json()
                parsed = json.loads(response_payload["choices"][0]["message"]["content"])
                if not isinstance(parsed.get("hotspots"), list):
                    raise ValueError("hotspot AI response is missing hotspots[]")
                parsed_batches.append(parsed)
                responses.append(response_payload)
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(
                json.dumps({"cache_key": cache_key, "batches": parsed_batches}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            metadata.update({"status": "success", "cache_key": cache_key})
        allowed_refs = {
            paper["ref"] for record in full_input for paper in record["representative_papers"]
        }
        by_topic = {hotspot.topic: hotspot for hotspot in hotspots}
        enriched = 0
        for batch in parsed_batches:
            for record in batch.get("hotspots", []):
                if not isinstance(record, dict) or record.get("topic") not in by_topic:
                    continue
                evidence = [ref for ref in record.get("evidence", []) if ref in allowed_refs]
                if not evidence:
                    continue
                hotspot = by_topic[record["topic"]]
                hotspot.why_it_matters = _clean(record.get("why_it_matters")) or hotspot.why_it_matters
                hotspot.research_designs = [_clean(x) for x in record.get("research_designs", []) if _clean(x)][:6] or hotspot.research_designs
                hotspot.methods = [_clean(x) for x in record.get("methods", []) if _clean(x)][:6] or hotspot.methods
                hotspot.research_gap = _clean(record.get("research_gap")) or hotspot.research_gap
                hotspot.potential_phd_question = _clean(record.get("potential_phd_question")) or hotspot.potential_phd_question
                hotspot.analysis_basis = evidence
                hotspot.ai_status = "success"
                enriched += 1
        metadata.update({"batches": len(parsed_batches), "enriched_hotspots": enriched, "input_sha256": sha256(input_json.encode("utf-8")).hexdigest()})
        return hotspots, metadata, {"request_input": full_input, "responses": responses, "metadata": metadata}
    except Exception as exc:
        metadata.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"[:300], "cache_key": cache_key})
        return hotspots, metadata, {"request_input": full_input, "responses": responses, "metadata": metadata}


def analyze_cross_board(
    root: Path,
    settings: dict[str, Any],
    hotspots: list[Hotspot],
    news: list[ResearchItem],
    agencies: list[ResearchItem],
    journals: list[ResearchItem],
) -> AIAnalysis:
    ai = settings.get("ai", {})
    model = ai.get("model", "deepseek-flash")
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
    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": f"以下是本期结构化输入，请输出 json：\n{input_json}"},
    ]
    request_body = {
        "model": model,
        "messages": messages,
        "thinking": {"type": "disabled"},
        "response_format": {"type": "json_object"},
        "max_tokens": int(ai.get("max_tokens", 2400)),
        "stream": False,
    }
    try:
        response_payload: dict[str, Any] = {}
        parsed: dict[str, Any] = {}
        for attempt in range(2):
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
            if not _contains_draft_markers(parsed):
                break
            if attempt == 1:
                raise ValueError("DeepSeek response contains draft self-correction markers")
            messages.extend(
                [
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": (
                            "上一版包含“修正/删除此条/改为”等草稿自检痕迹。"
                            "请在内部完成自检，只返回清理后的最终 JSON；"
                            "无法由输入支持的整条内容直接省略。"
                        ),
                    },
                ]
            )
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

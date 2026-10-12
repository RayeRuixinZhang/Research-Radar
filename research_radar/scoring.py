from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from difflib import SequenceMatcher
import re
from statistics import mean

from .models import Hotspot, ResearchItem


METHOD_TERMS = {
    "clustering": "聚类分析", "latent class": "潜类别分析", "latent profile": "潜在剖面分析",
    "machine learning": "机器学习", "xgboost": "XGBoost", "survival": "生存分析",
    "longitudinal": "纵向建模", "time-varying": "时变模型",
    "external validation": "外部验证", "calibration": "模型校准", "shap": "SHAP",
}
DESIGN_TERMS = {
    "multicenter": "多中心研究", "multi-center": "多中心研究",
    "prospective cohort": "前瞻性队列", "retrospective cohort": "回顾性队列",
    "cohort": "队列研究", "randomized": "随机对照试验",
    "electronic health record": "电子健康记录队列", "ehr": "电子健康记录队列",
    "case-control": "病例对照研究",
}


def _percentiles(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    ordered = sorted(values.items(), key=lambda pair: pair[1])
    denominator = max(1, len(ordered) - 1)
    return {key: index / denominator for index, (key, _) in enumerate(ordered)}


def _text(item: ResearchItem) -> str:
    return " ".join([item.title, item.summary, " ".join(item.mesh_terms)]).casefold()


def _publication_type(item: ResearchItem) -> str:
    values = item.provenance.get("publication_types", [])
    if not isinstance(values, list):
        return "未标明"
    preferred = [value for value in values if value not in {"journal article", "research support, non-u.s. gov't"}]
    return (preferred or values or ["未标明"])[0]


def _journal_category(item: ResearchItem) -> str:
    text = _text(item)
    if any(term in text for term in ("causal inference", "target trial", "machine learning", "artificial intelligence", "statistical method", "prediction model")):
        return "innovative_methods"
    if any(term in text for term in ("immunology", "host-pathogen", "genomic", "microbiome", "mechanism", "translational", "precision medicine")):
        return "biomedical_breakthrough"
    if set(item.categories).intersection({"medicine", "pediatrics", "infectious_disease", "public_health", "health_services"}):
        return "clinical_epidemiology"
    return "interdisciplinary"


def select_journal_papers(items: list[ResearchItem], settings: dict) -> list[ResearchItem]:
    """Select a broad, quality-first weekly journal board with soft category targets."""
    config = settings.get("journal_board", {})
    excluded = {value.casefold() for value in config.get("excluded_publication_types", [])}
    targets = config.get("category_targets", {})
    weights = config.get("score_weights", {})
    limit = int(settings["limits"]["journals"])
    candidates: list[ResearchItem] = []
    for item in items:
        publication_types = {str(value).casefold() for value in item.provenance.get("publication_types", [])}
        if item.is_retracted or publication_types.intersection(excluded):
            continue
        category = _journal_category(item)
        text = _text(item)
        importance = 1.0 if publication_types.intersection({"clinical trial", "randomized controlled trial", "multicenter study"}) else 0.7
        innovation = min(1.0, 0.45 + 0.2 * sum(term in text for term in ("novel", "causal", "genomic", "mechanism", "target trial", "precision")))
        evidence = 1.0 if item.summary and publication_types.intersection({"clinical trial", "randomized controlled trial", "observational study", "multicenter study"}) else (0.7 if item.summary else 0.3)
        future_value = min(1.0, 0.5 + 0.15 * sum(term in text for term in ("longitudinal", "translation", "method", "prediction", "mechanism")))
        relevance = min(1.0, len(item.categories) / 3)
        components = {
            "research_importance": importance, "scientific_innovation": innovation,
            "evidence_quality": evidence, "future_research_value": future_value,
            "background_relevance": relevance,
        }
        score = sum(float(weights.get(name, 0)) * value for name, value in components.items())
        item.provenance.update({
            "journal_main_category": category,
            "article_type": _publication_type(item),
            "journal_selection_score": round(score, 2),
        })
        candidates.append(item)
    candidates.sort(key=lambda value: (value.provenance["journal_selection_score"], value.published_at), reverse=True)
    selected: list[ResearchItem] = []
    used: set[str] = set()
    for category, target in targets.items():
        for item in candidates:
            if len([x for x in selected if x.provenance.get("journal_main_category") == category]) >= int(target):
                break
            if item.item_id not in used and item.provenance.get("journal_main_category") == category:
                selected.append(item)
                used.add(item.item_id)
    for item in candidates:
        if len(selected) >= limit:
            break
        if item.item_id not in used:
            selected.append(item)
            used.add(item.item_id)
    return selected[:limit]


def _news_category(item: ResearchItem) -> str:
    categories = set(item.categories)
    text = _text(item)
    if "pediatrics" in categories:
        return "child_health"
    if "infectious_disease" in categories or any(term in text for term in ("outbreak", "epidemic", "influenza", "rsv", "antimicrobial resistance")):
        return "infectious_disease"
    return "hospital_services"


def _event_key(title: str) -> str:
    words = re.findall(r"[a-z0-9\u4e00-\u9fff]+", title.casefold())
    stop = {"the", "a", "an", "and", "of", "to", "in", "on", "for", "with", "new"}
    return " ".join(word for word in words if word not in stop)[:160]


def select_news(items: list[ResearchItem], settings: dict, sources: list[dict]) -> list[ResearchItem]:
    config = settings.get("news_board", {})
    targets = config.get("category_targets", {})
    weights = config.get("score_weights", {})
    source_limit = int(config.get("source_candidate_limit", 3))
    limit = int(settings["limits"]["news"])
    priorities = {source["id"]: int(source.get("priority", 1)) for source in sources}
    per_source: Counter[str] = Counter()
    staged: list[ResearchItem] = []
    for item in sorted(items, key=lambda x: (priorities.get(x.source_id, 1), len(x.categories), bool(x.summary), x.published_at), reverse=True):
        if per_source[item.source_id] >= source_limit:
            continue
        item.provenance["news_main_category"] = _news_category(item)
        text = _text(item)
        components = {
            "topic_relevance": min(1.0, 0.6 + len(item.categories) * 0.1),
            "clinical_public_health_impact": 1.0 if any(term in text for term in ("outbreak", "policy", "hospital", "vaccine", "emergency", "mortality")) else 0.6,
            "news_importance": 0.9 if item.summary else 0.5,
            "source_credibility": min(1.0, priorities.get(item.source_id, 1) / 6),
            "research_inspiration": min(1.0, 0.5 + len(item.categories) * 0.1),
        }
        item.provenance["news_selection_score"] = round(sum(float(weights.get(name, 0)) * value for name, value in components.items()), 2)
        key = _event_key(item.title)
        if any(SequenceMatcher(None, key, _event_key(existing.title)).ratio() >= 0.88 for existing in staged):
            continue
        staged.append(item)
        per_source[item.source_id] += 1
    staged.sort(key=lambda value: (value.provenance["news_selection_score"], value.published_at), reverse=True)
    selected: list[ResearchItem] = []
    used: set[str] = set()
    for category, target in targets.items():
        for item in staged:
            if len([x for x in selected if x.provenance.get("news_main_category") == category]) >= int(target):
                break
            if item.item_id not in used and item.provenance.get("news_main_category") == category:
                selected.append(item)
                used.add(item.item_id)
    for item in staged:
        if len(selected) >= limit:
            break
        if item.item_id not in used:
            selected.append(item)
            used.add(item.item_id)
    return selected[:limit]


def _terms_found(papers: list[ResearchItem], mapping: dict[str, str]) -> list[str]:
    text = " ".join(_text(paper) for paper in papers)
    return list(dict.fromkeys(label for term, label in mapping.items() if term in text))


def _track_fallback(track_id: str, label: str) -> tuple[str, str]:
    gaps = {
        "dynamic_deterioration_prediction": "本次检索样本中，多中心外部验证及连续动态数据的报告仍有限；这一判断仅适用于当前代表性文献。",
        "model_transportability": "本次检索样本提示模型跨医院、跨人群的校准与可迁移性仍需被直接检验。",
    }
    questions = {
        "dynamic_deterioration_prediction": "能否利用入院后24小时生命体征与实验室指标的变化，预测儿童感染患者未来48小时发生PICU转入？",
        "pediatric_ari_phenotypes": "儿童急性呼吸道感染能否基于早期临床轨迹识别具有不同严重结局的可重复表型？",
        "virus_host_severity": "病毒特征与宿主反应的联合表型能否解释儿童呼吸道病毒感染严重程度差异？",
    }
    gap = gaps.get(track_id, "当前代表性文献支持该方向值得继续评估，但研究设计、外部验证与人群可迁移性需要在完整文献核查后再作判断。")
    question = questions.get(track_id, f"如何用可验证的临床流行病学设计进一步检验“{label}”并评估其跨人群可重复性？")
    return gap, question


def _safe_date(value: str) -> date | None:
    try:
        return date.fromisoformat((value or "")[:10])
    except ValueError:
        return None


def score_hotspots(items: list[ResearchItem], settings: dict, q1_issns: set[str]) -> list[Hotspot]:
    config = settings["hotspot_score"]
    if not q1_issns:
        return []
    tracks = {track["id"]: track for track in settings["hotspot_scope"].get("tracks", [])}
    recent_cutoff = date.today() - timedelta(days=settings["windows"]["recent_days"])
    groups: dict[str, list[ResearchItem]] = defaultdict(list)
    for item in items:
        if not item.doi or item.is_retracted or not q1_issns.intersection(item.issns):
            continue
        track_id = str(item.provenance.get("research_track", ""))
        if track_id in tracks:
            groups[track_id].append(item)
    groups = {track_id: papers for track_id, papers in groups.items() if len(papers) >= int(config["minimum_papers"]) and len({paper.journal for paper in papers if paper.journal}) >= int(config["minimum_journals"])}
    acceleration: dict[str, float] = {}
    method_value: dict[str, float] = {}
    clinical_value: dict[str, float] = {}
    citation: dict[str, float] = {}
    multicenter: dict[str, float] = {}
    for track_id, papers in groups.items():
        recent = sum(1 for paper in papers if (published := _safe_date(paper.published_at)) and published >= recent_cutoff)
        older = max(0, len(papers) - recent)
        acceleration[track_id] = (recent / max(1, settings["windows"]["recent_days"])) / (older / max(1, settings["windows"]["hotspot_days"] - settings["windows"]["recent_days"]) + 1e-6)
        method_value[track_id] = mean(min(1.0, sum(term in _text(paper) for term in METHOD_TERMS) / 2) for paper in papers)
        clinical_value[track_id] = mean(min(1.0, sum(term in _text(paper) for term in ("picu", "mortality", "ventilation", "deterioration", "severity", "outcome")) / 2) for paper in papers)
        citation[track_id] = mean([paper.citation_percentile for paper in papers] or [0.0])
        multicenter[track_id] = mean(1.0 if any(term in _text(paper) for term in ("multicenter", "multi-center", "external validation")) else 0.0 for paper in papers)
    percentile_metrics = {
        "methodological_novelty": _percentiles(method_value), "clinical_value": _percentiles(clinical_value),
        "acceleration": _percentiles(acceleration), "citation": _percentiles(citation),
        "multicenter_evidence": _percentiles(multicenter),
    }
    hotspots: list[Hotspot] = []
    for track_id, papers in groups.items():
        track = tracks[track_id]
        fit = {"high": 1.0, "core": 0.9, "secondary": 0.7}.get(track.get("priority"), 0.6)
        score = float(config["research_fit"]) * fit
        for metric_name, values in percentile_metrics.items():
            score += float(config[metric_name]) * values.get(track_id, 0.0)
        representative = sorted(papers, key=lambda paper: (sum(term in _text(paper) for term in METHOD_TERMS), paper.citation_percentile, paper.published_at), reverse=True)[: settings["limits"]["representative_papers"]]
        recent_count = sum(1 for paper in papers if (published := _safe_date(paper.published_at)) and published >= recent_cutoff)
        older_count = len(papers) - recent_count
        trend = "emerging" if recent_count and not older_count else ("increasing" if acceleration[track_id] > 1.2 else "stable")
        gap, question = _track_fallback(track_id, track["label"])
        hotspots.append(Hotspot(
            topic=track["label"], score=round(score, 4), paper_count=len(papers),
            journal_count=len({paper.journal for paper in papers if paper.journal}),
            mesh_terms=sorted({term for paper in papers for term in paper.mesh_terms})[:8], papers=representative,
            trend=trend,
            why_it_matters=f"该方向与儿童感染、临床结局或可操作的方法学问题直接相关；评分基于本次检索到的{len(papers)}篇Q1论文。",
            research_designs=_terms_found(papers, DESIGN_TERMS)[:6], methods=_terms_found(papers, METHOD_TERMS)[:6],
            research_gap=gap, potential_phd_question=question,
            analysis_basis=[paper.item_id for paper in representative],
        ))
    return sorted(hotspots, key=lambda value: value.score, reverse=True)[: settings["limits"]["hotspots"]]

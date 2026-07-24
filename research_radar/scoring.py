from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from statistics import mean

from .models import Hotspot, ResearchItem


def _percentiles(values: dict[str, float]) -> dict[str, float]:
    if not values:
        return {}
    ordered = sorted(values.items(), key=lambda pair: pair[1])
    denominator = max(1, len(ordered) - 1)
    return {key: index / denominator for index, (key, _) in enumerate(ordered)}


def score_hotspots(items: list[ResearchItem], settings: dict, q1_issns: set[str]) -> list[Hotspot]:
    config = settings["hotspot_score"]
    if not q1_issns:
        return []
    today = date.today()
    recent_cutoff = today - timedelta(days=settings["windows"]["recent_days"])
    groups: dict[str, list[ResearchItem]] = defaultdict(list)
    for item in items:
        if not item.doi or item.is_retracted or not q1_issns.intersection(item.issns):
            continue
        topic = item.primary_topic or (item.mesh_terms[0] if item.mesh_terms else "")
        if topic:
            groups[topic].append(item)
    groups = {
        topic: papers
        for topic, papers in groups.items()
        if len(papers) >= config["minimum_papers"]
        and len({paper.journal for paper in papers if paper.journal}) >= config["minimum_journals"]
    }
    volume = {topic: float(len(papers)) for topic, papers in groups.items()}
    diversity = {topic: float(len({paper.journal for paper in papers if paper.journal})) for topic, papers in groups.items()}
    citation = {topic: mean([paper.citation_percentile for paper in papers] or [0.0]) for topic, papers in groups.items()}
    acceleration: dict[str, float] = {}
    for topic, papers in groups.items():
        recent = 0
        older = 0
        for paper in papers:
            try:
                published = date.fromisoformat(paper.published_at[:10])
            except (ValueError, TypeError):
                continue
            if published >= recent_cutoff:
                recent += 1
            else:
                older += 1
        acceleration[topic] = (recent / max(1, settings["windows"]["recent_days"])) / (
            older / max(1, settings["windows"]["hotspot_days"] - settings["windows"]["recent_days"]) + 1e-6
        )
    metrics = [_percentiles(values) for values in (volume, acceleration, citation, diversity)]
    weights = [config["volume"], config["acceleration"], config["citation"], config["diversity"]]
    hotspots = []
    for topic, papers in groups.items():
        score = sum(weight * metric.get(topic, 0.0) for weight, metric in zip(weights, metrics))
        representative = sorted(
            papers,
            key=lambda paper: (paper.citation_percentile, paper.published_at),
            reverse=True,
        )[: settings["limits"]["representative_papers"]]
        mesh = sorted({term for paper in papers for term in paper.mesh_terms})[:8]
        hotspots.append(
            Hotspot(topic, round(score, 4), len(papers), int(diversity[topic]), mesh, representative)
        )
    return sorted(hotspots, key=lambda value: value.score, reverse=True)[: settings["limits"]["hotspots"]]


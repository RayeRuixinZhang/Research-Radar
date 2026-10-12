from datetime import date, timedelta

from research_radar.models import ResearchItem
from research_radar.scoring import score_hotspots, select_journal_papers, select_news


def paper(index: int, journal: str) -> ResearchItem:
    return ResearchItem(
        kind="hotspot_paper",
        source_id="pubmed",
        source_name="PubMed",
        title=f"Paper {index}",
        summary="An abstract.",
        url=f"https://pubmed.ncbi.nlm.nih.gov/{index}/",
        doi=f"10.1000/{index}",
        journal=journal,
        issns=["1234-567X"],
        published_at=(date.today() - timedelta(days=index)).isoformat(),
        primary_topic="儿童感染严重程度与临床结局预测",
        mesh_terms=["Epidemiology"],
        citation_percentile=index / 10,
        provenance={"research_track": "infection_outcome_prediction"},
    ).finalize()


def test_hotspot_weighting_and_thresholds():
    settings = {
        "windows": {"recent_days": 90, "hotspot_days": 365},
        "limits": {"hotspots": 10, "representative_papers": 3},
        "hotspot_score": {
            "research_fit": 0.3, "methodological_novelty": 0.2,
            "clinical_value": 0.2, "acceleration": 0.15, "citation": 0.1,
            "multicenter_evidence": 0.05, "minimum_papers": 5, "minimum_journals": 3,
        },
        "hotspot_scope": {"tracks": [{
            "id": "infection_outcome_prediction",
            "label": "儿童感染严重程度与临床结局预测", "priority": "core",
        }]},
    }
    items = [paper(i, f"Journal {i % 3}") for i in range(1, 7)]
    result = score_hotspots(items, settings, {"1234-567X"})
    assert len(result) == 1
    assert result[0].paper_count == 6
    assert len(result[0].papers) == 3


def test_missing_scimago_data_is_not_mislabelled():
    assert score_hotspots([paper(1, "Journal")], {
        "windows": {"recent_days": 90, "hotspot_days": 365},
        "limits": {"hotspots": 10, "representative_papers": 3},
        "hotspot_score": {
            "research_fit": .3, "methodological_novelty": .2, "clinical_value": .2,
            "acceleration": .15, "citation": .1, "multicenter_evidence": .05,
            "minimum_papers": 1, "minimum_journals": 1,
        },
        "hotspot_scope": {"tracks": []},
    }, set()) == []


def test_journal_selection_keeps_high_quality_cross_disciplinary_paper():
    item = paper(1, "Nature")
    item.categories = []
    item.provenance["publication_types"] = ["journal article"]
    settings = {
        "limits": {"journals": 15},
        "journal_board": {"category_targets": {"interdisciplinary": 2}, "excluded_publication_types": ["editorial"]},
    }
    assert select_journal_papers([item], settings) == [item]
    assert item.provenance["journal_main_category"] == "interdisciplinary"


def test_news_selection_caps_each_source_and_assigns_theme():
    items = []
    for index in range(5):
        value = paper(index + 1, "News")
        value.kind = "news"
        value.source_id = "reuters"
        value.title = [
            "Child vaccination access expands",
            "Pediatric emergency staffing changes",
            "Neonatal care quality programme",
            "Adolescent mental health services",
            "Infant hospital capacity review",
        ][index]
        value.categories = ["pediatrics"]
        value.finalize()
        items.append(value)
    settings = {"limits": {"news": 10}, "news_board": {"source_candidate_limit": 3, "category_targets": {"child_health": 4}}}
    selected = select_news(items, settings, [{"id": "reuters", "priority": 6}])
    assert len(selected) == 3
    assert all(item.provenance["news_main_category"] == "child_health" for item in selected)


from datetime import date, timedelta

from research_radar.models import ResearchItem
from research_radar.scoring import score_hotspots


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
        primary_topic="Outbreak surveillance",
        mesh_terms=["Epidemiology"],
        citation_percentile=index / 10,
    ).finalize()


def test_hotspot_weighting_and_thresholds():
    settings = {
        "windows": {"recent_days": 90, "hotspot_days": 365},
        "limits": {"hotspots": 10, "representative_papers": 3},
        "hotspot_score": {
            "volume": 0.4, "acceleration": 0.3, "citation": 0.2, "diversity": 0.1,
            "minimum_papers": 5, "minimum_journals": 3,
        },
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
            "volume": .4, "acceleration": .3, "citation": .2, "diversity": .1,
            "minimum_papers": 1, "minimum_journals": 1,
        },
    }, set()) == []


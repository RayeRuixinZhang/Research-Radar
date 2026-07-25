from research_radar.models import ResearchItem
from research_radar.normalize import (
    canonical_url,
    classify,
    matches_hotspot_scope,
    normalize_doi,
    normalize_issn,
    truncate_summary,
)


def test_identifiers_and_url():
    assert normalize_doi("https://doi.org/10.1000/ABC.12") == "10.1000/abc.12"
    assert normalize_issn("1234567X") == "1234-567X"
    assert canonical_url("https://EXAMPLE.com/a?utm_source=x&id=2#top") == "https://example.com/a?id=2"


def test_summary_never_exceeds_limit():
    value = "First complete sentence. " + ("x" * 400)
    result = truncate_summary(value, 250)
    assert len(result) <= 250
    assert result == "First complete sentence."


def test_classification():
    config = {"categories": {"infection": {"terms": ["outbreak", "传染病"]}}}
    assert classify("New outbreak warning", config) == ["infection"]


def test_hotspot_scope_uses_categories_and_terms():
    scope = {
        "include_categories": ["infectious_disease"],
        "include_terms": ["epidemiolog", "vaccine"],
    }
    unrelated = ResearchItem(
        kind="paper", source_id="x", source_name="x", title="Cancer metabolism",
        summary="Tumour pathway study.", url="", published_at="2026-01-01",
    )
    vaccine = ResearchItem(
        kind="paper", source_id="x", source_name="x", title="Vaccine uptake",
        summary="Population study.", url="", published_at="2026-01-01",
    )
    labelled = ResearchItem(
        kind="paper", source_id="x", source_name="x", title="Study",
        summary="", url="", published_at="2026-01-01",
        categories=["infectious_disease"],
    )
    assert not matches_hotspot_scope(unrelated, scope)
    assert matches_hotspot_scope(vaccine, scope)
    assert matches_hotspot_scope(labelled, scope)

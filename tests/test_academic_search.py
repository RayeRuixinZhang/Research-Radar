from research_radar.sources.academic import PubMedSource


def test_pubmed_search_appends_focused_term(monkeypatch):
    captured = {}

    def fake_get_json(url, params):
        captured.update(params)
        return {"esearchresult": {"idlist": ["1"]}}

    monkeypatch.setattr("research_radar.sources.academic.get_json", fake_get_json)
    source = PubMedSource({})
    ids, _ = source.search(
        365,
        retmax=2000,
        extra_term='("Epidemiology"[MeSH Terms] OR vaccine*[Title/Abstract])',
    )
    assert ids == ["1"]
    assert "medline[sb]" in captured["term"]
    assert '"Epidemiology"[MeSH Terms]' in captured["term"]
    assert "vaccine*[Title/Abstract]" in captured["term"]
    assert captured["retmax"] == 2000

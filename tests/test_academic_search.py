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


def test_pubmed_fetch_retries_rate_limit(monkeypatch):
    class Response:
        def __init__(self, status_code, text="<PubmedArticleSet />", headers=None):
            self.status_code = status_code
            self.text = text
            self.content = text.encode()
            self.headers = headers or {}

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError(f"HTTP {self.status_code}")

    responses = [Response(429, headers={"Retry-After": "1"}), Response(200)]

    class HTTP:
        def get(self, *_args, **_kwargs):
            return responses.pop(0)

    sleeps = []
    monkeypatch.setattr("research_radar.sources.academic.time.sleep", sleeps.append)
    source = PubMedSource({})
    source.http = HTTP()
    items, batches = source.fetch(["1"])
    assert items == []
    assert batches == ["<PubmedArticleSet />"]
    assert 1.0 in sleeps

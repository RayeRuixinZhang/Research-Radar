from pathlib import Path

from research_radar.ai import _contains_draft_markers, analyze_cross_board, analyze_hotspots
from research_radar.models import Hotspot, ResearchItem


def item(kind: str, title: str, doi: str = "", url: str = "") -> ResearchItem:
    return ResearchItem(
        kind=kind,
        source_id="source",
        source_name="Source",
        title=title,
        summary="Evidence summary.",
        url=url or "https://example.org/item",
        doi=doi,
        journal="Journal",
        published_at="2026-07-20",
    ).finalize()


def settings() -> dict:
    return {
        "ai": {
            "enabled": True,
            "provider": "deepseek",
            "model": "deepseek-v4-flash",
            "prompt_path": "prompts/cross_board_analysis_zh.md",
            "max_tokens": 2400,
            "timeout_seconds": 120,
        }
    }


def test_ai_missing_key_degrades(monkeypatch, tmp_path: Path):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    result = analyze_cross_board(tmp_path, settings(), [], [], [], [])
    assert result.metadata["status"] == "missing_key"
    assert "DEEPSEEK_API_KEY" in result.markdown


def test_deepseek_json_is_rendered_with_traceable_evidence(monkeypatch, tmp_path: Path):
    prompt = tmp_path / "prompts" / "cross_board_analysis_zh.md"
    prompt.parent.mkdir()
    prompt.write_text("输出 json。", encoding="utf-8")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    paper = item("hotspot_paper", "Paper", "10.1000/test")
    hotspot = Hotspot("Outbreak surveillance", 0.9, 8, 3, ["Humans"], [paper])
    news = item("news", "News")

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "id": "response-1",
                "usage": {"prompt_tokens": 100, "completion_tokens": 50},
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"cross_board_themes":[{"title":"监测","analysis":"存在跨板块信号",'
                                '"evidence":["H1","N1","BAD"]}],"epidemiology_implications":[],'
                                '"research_questions":[],"candidate_methods":[],"evidence_limitations":[]}'
                            )
                        }
                    }
                ],
            }

    def fake_post(url, headers, json, timeout):
        assert headers["Authorization"] == "Bearer test-key"
        assert json["model"] == "deepseek-v4-flash"
        assert json["thinking"] == {"type": "disabled"}
        assert json["response_format"] == {"type": "json_object"}
        assert '"board":2' in json["messages"][1]["content"]
        assert '"board":4' in json["messages"][1]["content"]
        return Response()

    monkeypatch.setattr("research_radar.ai.requests.post", fake_post)
    result = analyze_cross_board(tmp_path, settings(), [hotspot], [news], [], [])
    assert result.metadata["status"] == "success"
    assert result.metadata["usage"]["completion_tokens"] == 50
    assert "存在跨板块信号" in result.markdown
    assert "H1 · Outbreak surveillance" in result.markdown
    assert "N1 · News" in result.markdown
    assert "BAD" not in result.markdown
    assert "test-key" not in str(result.raw)


def test_draft_markers_are_rejected():
    assert _contains_draft_markers(
        {"epidemiology_implications": [{"text": "修正：删除此条"}]}
    )
    assert not _contains_draft_markers(
        {"epidemiology_implications": [{"text": "需进一步验证该监测信号。"}]}
    )


def test_hotspot_ai_is_independent_and_evidence_checked(monkeypatch, tmp_path: Path):
    prompt = tmp_path / "hotspot.md"
    prompt.write_text("只输出JSON", encoding="utf-8")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-key")
    paper = item("hotspot_paper", "Paper", "10.1000/hotspot")
    hotspot = Hotspot("儿童感染严重程度预测", 0.8, 5, 2, [], [paper])

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "id": "hotspot-response",
                "choices": [{"message": {"content": (
                    '{"hotspots":[{"topic":"儿童感染严重程度预测",'
                    '"why_it_matters":"可检验临床恶化风险。","research_designs":["队列研究"],'
                    '"methods":["外部验证"],"research_gap":"当前代表性文献的外部验证有限。",'
                    '"potential_phd_question":"能否预测48小时恶化？","evidence":["H1-P1"]}]}'
                )}}],
                "usage": {"total_tokens": 100},
            }

    def fake_post(_url, **kwargs):
        assert kwargs["json"]["model"] == "deepseek-flash"
        return Response()

    monkeypatch.setattr("research_radar.ai.requests.post", fake_post)
    settings = {
        "ai": {"provider": "deepseek", "model": "deepseek-flash", "endpoint": "https://api.deepseek.com/chat/completions"},
        "hotspot_ai": {"enabled": True, "prompt_path": "hotspot.md", "cache_dir": "cache", "batch_size": 5},
    }
    enriched, metadata, raw = analyze_hotspots(tmp_path, settings, [hotspot])
    assert metadata["status"] == "success"
    assert enriched[0].ai_status == "success"
    assert enriched[0].analysis_basis == ["H1-P1"]
    assert "外部验证" in enriched[0].methods
    assert raw and "test-key" not in str(raw)

"""
Tests for reckon/ingestion/news_sentiment.py
pytest tests/test_news_sentiment.py -v
"""
import os, pytest
from unittest.mock import MagicMock, patch
from reckon.ingestion.news_sentiment import (
    NewsSentimentIngester, NewsSentimentIndicator,
    SOURCE_REGISTRY, _SYSTEM_PROMPT,
)


class TestSourceRegistry:

    def test_registry_has_global_diversity(self):
        regions = {s["region"] for s in SOURCE_REGISTRY}
        # Must cover more than just Western regions
        assert len(regions) >= 5
        non_western = regions - {"europe", "global"}
        assert len(non_western) >= 3, f"Insufficient non-Western regions: {non_western}"

    def test_all_sources_have_required_fields(self):
        for s in SOURCE_REGISTRY:
            assert "url" in s and s["url"].startswith("http")
            assert "label" in s and s["label"]
            assert "region" in s
            assert "credibility" in s and 0.0 <= s["credibility"] <= 1.0
            assert "max_items" in s and s["max_items"] > 0

    def test_wire_services_have_max_credibility(self):
        wire_labels = {"Reuters World", "Reuters Business", "AP Top News"}
        for s in SOURCE_REGISTRY:
            if s["label"] in wire_labels:
                assert s["credibility"] == 1.0, (
                    f"{s['label']} should have credibility 1.0"
                )

    def test_sentiment_bias_note_in_system_prompt(self):
        assert "structural" in _SYSTEM_PROMPT.lower() or "bias" in _SYSTEM_PROMPT.lower()


class TestNewsSentimentIngester:

    def test_stub_when_no_api_key(self):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        ingester = NewsSentimentIngester()
        results = ingester.fetch()
        assert all(r.source.endswith("stub") for r in results)

    def test_stub_has_all_tiers(self):
        ingester = NewsSentimentIngester()
        stubs = ingester._stub_data()
        names = {s.name for s in stubs}
        for tier in ("economic", "political", "military", "existential"):
            assert f"news_sentiment_{tier}" in names
        assert "news_sentiment_composite" in names

    def test_build_indicators_returns_five(self):
        ingester = NewsSentimentIngester()
        scores = {"economic": 40, "political": 55, "military": 62, "existential": 28}
        indicators = ingester._build_indicators(scores, 80)
        assert len(indicators) == 5

    def test_composite_is_average(self):
        ingester = NewsSentimentIngester()
        scores = {"economic": 40, "political": 60, "military": 80, "existential": 20}
        indicators = ingester._build_indicators(scores, 10)
        composite = next(i for i in indicators if i.name == "news_sentiment_composite")
        assert composite.raw_value == pytest.approx(50.0, abs=0.1)

    def test_source_ids_stable_same_scores(self):
        """Same scores → same source_id (enables upsert)."""
        ingester = NewsSentimentIngester()
        scores = {"economic": 30, "political": 40, "military": 50, "existential": 20}
        ids_a = {i.source_id for i in ingester._build_indicators(scores, 50)}
        ids_b = {i.source_id for i in ingester._build_indicators(scores, 99)}
        assert ids_a == ids_b

    def test_metadata_has_bias_note(self):
        ingester = NewsSentimentIngester()
        scores = {"economic": 45, "political": 50, "military": 55, "existential": 30}
        indicators = ingester._build_indicators(scores, 40)
        for ind in indicators:
            assert "bias_note" in ind.metadata

    def test_metadata_has_region_coverage(self):
        ingester = NewsSentimentIngester()
        scores = {"economic": 45, "political": 50, "military": 55, "existential": 30}
        indicators = ingester._build_indicators(scores, 40)
        for ind in indicators:
            assert "regions_covered" in ind.metadata
            assert len(ind.metadata["regions_covered"]) >= 3

    def test_score_with_claude_parses_json(self):
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text=(
            '{"economic":42,"political":55,"military":60,"existential":25,'
            '"top_signals":["test"],"reasoning":"test signal"}'
        ))]
        ingester = NewsSentimentIngester()
        ingester._client = MagicMock()
        ingester._client.messages.create.return_value = mock_resp

        from reckon.ingestion.news_sentiment import WeightedHeadline
        headlines = [WeightedHeadline("Headline", "Test", "global", 0.9)]
        result = ingester._score_with_claude(headlines)
        assert result is not None
        assert result["economic"] == 42
        assert result["reasoning"] == "test signal"

    def test_score_with_claude_returns_none_on_bad_json(self):
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text="not json")]
        ingester = NewsSentimentIngester()
        ingester._client = MagicMock()
        ingester._client.messages.create.return_value = mock_resp
        from reckon.ingestion.news_sentiment import WeightedHeadline
        result = ingester._score_with_claude([WeightedHeadline("H", "S", "global", 0.9)])
        assert result is None

    def test_collect_headlines_handles_bad_url(self):
        ingester = NewsSentimentIngester()
        with patch(
            "reckon.ingestion.news_sentiment.SOURCE_REGISTRY",
            [{"url": "https://this-does-not-exist.invalid/rss",
              "label": "Bad", "region": "global", "credibility": 0.9, "max_items": 5}],
        ):
            headlines = ingester._collect_headlines()
        assert isinstance(headlines, list)

    def test_headlines_grouped_by_credibility(self):
        """Headlines are grouped into high/mid/low credibility tiers for Claude."""
        mock_resp = MagicMock()
        mock_resp.content = [MagicMock(text=(
            '{"economic":30,"political":30,"military":30,"existential":10,'
            '"top_signals":[],"reasoning":""}'
        ))]
        ingester = NewsSentimentIngester()
        ingester._client = MagicMock()
        ingester._client.messages.create.return_value = mock_resp

        from reckon.ingestion.news_sentiment import WeightedHeadline
        headlines = [
            WeightedHeadline("Wire headline", "Reuters", "global", 1.0),
            WeightedHeadline("Mid headline", "BBC", "europe", 0.80),
            WeightedHeadline("Lower headline", "AllAfrica", "africa", 0.70),
        ]
        ingester._score_with_claude(headlines)
        call_args = ingester._client.messages.create.call_args
        user_content = call_args[1]["messages"][0]["content"]
        assert "HIGH CREDIBILITY" in user_content
        assert "MID CREDIBILITY" in user_content

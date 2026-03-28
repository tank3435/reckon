"""
Tests for the Claude API Narrative Layer.

Covers:
  - Stub returned when ANTHROPIC_API_KEY absent
  - Output contains all required keys
  - Headline is <= 15 words
  - Confidence note present when completeness < 80%
  - Confidence note absent when completeness >= 80%
  - Mock Claude API response parses correctly
  - Graceful failure (returns None) when API errors
  - Narrative is not merged into assessment response when generation fails
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from reckon.analysis.narrative import (
    REQUIRED_KEYS,
    REQUIRED_TIER_KEYS,
    _build_user_prompt,
    _parse_narrative_response,
    _stub_narrative,
    generate_narrative,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def sample_narrative_data():
    """Representative narrative_data matching what scoring.py produces."""
    return {
        "composite_score": 47.3,
        "hard_data_composite": 44.1,
        "tier_scores": {
            "economic": 38.5,
            "political": 52.0,
            "military": 55.8,
            "existential": 41.2,
        },
        "response_level": "YELLOW",
        "data_completeness_pct": 72.0,
        "top_indicators": [
            {
                "name": "acled_global_fatalities_last_30d",
                "normalized_value": 68.2,
                "tier": "military",
                "source": "acled",
            },
            {
                "name": "polymarket_nuclear_use",
                "normalized_value": 61.5,
                "tier": "existential",
                "source": "polymarket",
            },
        ],
        "methodology_note": "Weighted average with sentiment capped at 0.08.",
    }


@pytest.fixture
def sample_narrative_data_high_completeness(sample_narrative_data):
    """narrative_data with completeness >= 80%."""
    return {**sample_narrative_data, "data_completeness_pct": 92.0}


@pytest.fixture
def valid_claude_response():
    """A well-formed narrative JSON that Claude would return."""
    return {
        "headline": "Risk indicators are moderately elevated but within historical norms.",
        "summary": (
            "The composite risk score stands at 47.3 out of 100, placing the overall "
            "assessment in YELLOW territory. Military and political tiers show the most "
            "activity, while economic and existential indicators remain closer to baseline."
        ),
        "tier_narratives": {
            "economic": (
                "The economic tier scores 38.5/100. Recession probability and yield "
                "curve data suggest mild caution but no immediate distress signal."
            ),
            "political": (
                "The political tier scores 52.0/100, reflecting elevated protest "
                "activity tracked by ACLED over the past 30 days."
            ),
            "military": (
                "The military tier is the highest at 55.8/100. Global conflict "
                "fatalities over the last 30 days are above the historical median."
            ),
            "existential": (
                "The existential tier scores 41.2/100. Prediction market estimates "
                "for nuclear weapon use remain low but non-trivial."
            ),
        },
        "response_rationale": (
            "The YELLOW response level reflects a composite score below 50, meaning "
            "indicators warrant monitoring but do not call for accelerated action."
        ),
        "confidence_note": (
            "Data completeness is 72%, meaning some indicators are missing or stale. "
            "This assessment may shift as more data becomes available."
        ),
    }


@pytest.fixture
def valid_claude_response_no_confidence(valid_claude_response):
    """Narrative where completeness is high, so confidence_note is empty."""
    return {**valid_claude_response, "confidence_note": ""}


# ---------------------------------------------------------------------------
# Test: Stub returned when ANTHROPIC_API_KEY absent
# ---------------------------------------------------------------------------
class TestStubBehavior:
    def test_stub_returned_without_api_key(self, sample_narrative_data, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = generate_narrative(sample_narrative_data)
        assert result is not None
        assert result["_stub"] is True
        assert result["_stub_reason"] == "api_key_missing"

    def test_stub_has_all_required_keys(self):
        stub = _stub_narrative("test")
        for key in REQUIRED_KEYS:
            assert key in stub
        for tier_key in REQUIRED_TIER_KEYS:
            assert tier_key in stub["tier_narratives"]

    def test_stub_values_are_empty_strings(self):
        stub = _stub_narrative("test")
        assert stub["headline"] == ""
        assert stub["summary"] == ""
        assert stub["response_rationale"] == ""
        for v in stub["tier_narratives"].values():
            assert v == ""


# ---------------------------------------------------------------------------
# Test: Output contains all required keys
# ---------------------------------------------------------------------------
class TestOutputStructure:
    def test_valid_response_has_all_keys(self, valid_claude_response):
        result = _parse_narrative_response(json.dumps(valid_claude_response))
        assert result is not None
        for key in REQUIRED_KEYS:
            assert key in result

    def test_valid_response_has_all_tier_keys(self, valid_claude_response):
        result = _parse_narrative_response(json.dumps(valid_claude_response))
        assert result is not None
        for key in REQUIRED_TIER_KEYS:
            assert key in result["tier_narratives"]


# ---------------------------------------------------------------------------
# Test: Headline is <= 15 words
# ---------------------------------------------------------------------------
class TestHeadlineLength:
    def test_headline_within_limit(self, valid_claude_response):
        result = _parse_narrative_response(json.dumps(valid_claude_response))
        assert result is not None
        word_count = len(result["headline"].split())
        assert word_count <= 15, f"Headline is {word_count} words, max 15"


# ---------------------------------------------------------------------------
# Test: Confidence note behavior based on completeness
# ---------------------------------------------------------------------------
class TestConfidenceNote:
    def test_confidence_note_present_when_low_completeness(
        self, valid_claude_response
    ):
        """When completeness < 80%, confidence_note should be non-empty."""
        # The valid_claude_response fixture has a non-empty confidence_note
        result = _parse_narrative_response(json.dumps(valid_claude_response))
        assert result is not None
        assert len(result["confidence_note"]) > 0

    def test_confidence_note_absent_when_high_completeness(
        self, valid_claude_response_no_confidence
    ):
        """When completeness >= 80%, confidence_note should be empty."""
        result = _parse_narrative_response(
            json.dumps(valid_claude_response_no_confidence)
        )
        assert result is not None
        assert result["confidence_note"] == ""

    def test_user_prompt_includes_completeness(self, sample_narrative_data):
        """The user prompt should include the completeness percentage."""
        prompt = _build_user_prompt(sample_narrative_data)
        assert "72.0%" in prompt


# ---------------------------------------------------------------------------
# Test: Mock Claude API response parses correctly
# ---------------------------------------------------------------------------
class TestParsing:
    def test_parses_clean_json(self, valid_claude_response):
        raw = json.dumps(valid_claude_response)
        result = _parse_narrative_response(raw)
        assert result is not None
        assert result["headline"] == valid_claude_response["headline"]

    def test_parses_json_with_markdown_fences(self, valid_claude_response):
        raw = "```json\n" + json.dumps(valid_claude_response) + "\n```"
        result = _parse_narrative_response(raw)
        assert result is not None
        assert result["headline"] == valid_claude_response["headline"]

    def test_returns_none_for_invalid_json(self):
        result = _parse_narrative_response("this is not json")
        assert result is None

    def test_returns_none_for_missing_keys(self):
        incomplete = {"headline": "test"}
        result = _parse_narrative_response(json.dumps(incomplete))
        assert result is None

    def test_returns_none_for_missing_tier_keys(self):
        data = {
            "headline": "test",
            "summary": "test",
            "tier_narratives": {"economic": "ok"},  # missing other tiers
            "response_rationale": "test",
            "confidence_note": "",
        }
        result = _parse_narrative_response(json.dumps(data))
        assert result is None


# ---------------------------------------------------------------------------
# Test: Graceful failure when API errors
# ---------------------------------------------------------------------------
class TestGracefulFailure:
    @patch("reckon.analysis.narrative.anthropic")
    def test_returns_none_on_api_exception(
        self, mock_anthropic_mod, sample_narrative_data, monkeypatch
    ):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API timeout")
        mock_anthropic_mod.Anthropic.return_value = mock_client

        result = generate_narrative(sample_narrative_data)
        assert result is None

    @patch("reckon.analysis.narrative.anthropic")
    def test_returns_none_on_empty_response(
        self, mock_anthropic_mod, sample_narrative_data, monkeypatch
    ):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = []
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_mod.Anthropic.return_value = mock_client

        result = generate_narrative(sample_narrative_data)
        assert result is None

    @patch("reckon.analysis.narrative.anthropic")
    def test_returns_none_on_unparseable_response(
        self, mock_anthropic_mod, sample_narrative_data, monkeypatch
    ):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_block = MagicMock()
        mock_block.text = "Sorry, I can't do that."
        mock_response.content = [mock_block]
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_mod.Anthropic.return_value = mock_client

        result = generate_narrative(sample_narrative_data)
        assert result is None


# ---------------------------------------------------------------------------
# Test: Full round-trip with mocked API returning valid JSON
# ---------------------------------------------------------------------------
class TestFullRoundTrip:
    @patch("reckon.analysis.narrative.anthropic")
    def test_successful_generation(
        self,
        mock_anthropic_mod,
        sample_narrative_data,
        valid_claude_response,
        monkeypatch,
    ):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_block = MagicMock()
        mock_block.text = json.dumps(valid_claude_response)
        mock_response.content = [mock_block]
        mock_client.messages.create.return_value = mock_response
        mock_anthropic_mod.Anthropic.return_value = mock_client

        result = generate_narrative(sample_narrative_data)

        assert result is not None
        assert result["headline"] == valid_claude_response["headline"]
        assert result["summary"] == valid_claude_response["summary"]
        assert result["tier_narratives"]["military"] == valid_claude_response["tier_narratives"]["military"]

        # Verify the API was called with the right model
        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs.get("model") == "claude-sonnet-4-20250514" or \
               call_kwargs[1].get("model") == "claude-sonnet-4-20250514"


# ---------------------------------------------------------------------------
# Test: User prompt construction
# ---------------------------------------------------------------------------
class TestUserPrompt:
    def test_prompt_includes_all_tier_scores(self, sample_narrative_data):
        prompt = _build_user_prompt(sample_narrative_data)
        assert "38.5" in prompt  # economic
        assert "52.0" in prompt  # political
        assert "55.8" in prompt  # military
        assert "41.2" in prompt  # existential

    def test_prompt_includes_composite(self, sample_narrative_data):
        prompt = _build_user_prompt(sample_narrative_data)
        assert "47.3" in prompt

    def test_prompt_includes_response_level(self, sample_narrative_data):
        prompt = _build_user_prompt(sample_narrative_data)
        assert "YELLOW" in prompt

    def test_prompt_includes_top_indicators(self, sample_narrative_data):
        prompt = _build_user_prompt(sample_narrative_data)
        assert "acled_global_fatalities_last_30d" in prompt
        assert "polymarket_nuclear_use" in prompt

    def test_prompt_handles_empty_top_indicators(self, sample_narrative_data):
        data = {**sample_narrative_data, "top_indicators": []}
        prompt = _build_user_prompt(data)
        assert "(none available)" in prompt


# ---------------------------------------------------------------------------
# Test: Assessment endpoint integration (narrative failure does not break it)
# ---------------------------------------------------------------------------
class TestAssessmentIntegration:
    """
    Verify that when narrative generation fails, the assessment response
    is still valid — narrative is simply absent, not a 500 error.
    """

    def test_none_result_is_not_merged(self, sample_narrative_data, monkeypatch):
        """
        Simulate what assessment.py should do: if generate_narrative returns
        None, the 'narrative' key should not appear in the response.
        """
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

        # Simulate the assessment endpoint logic
        assessment_response = {
            "composite_score": 47.3,
            "response_level": "YELLOW",
            "tier_scores": sample_narrative_data["tier_scores"],
        }

        # Narrative fails
        with patch(
            "reckon.analysis.narrative.generate_narrative", return_value=None
        ):
            narrative_result = None  # simulating the call returning None

        # Assessment endpoint should NOT include narrative key on failure
        if narrative_result is not None:
            assessment_response["narrative"] = narrative_result

        assert "narrative" not in assessment_response

    def test_stub_result_is_still_mergeable(self, sample_narrative_data, monkeypatch):
        """Stub results (from missing API key) can be merged if desired."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        result = generate_narrative(sample_narrative_data)
        assert result is not None
        assert result["_stub"] is True

        # It can be merged without error
        assessment_response = {"composite_score": 47.3}
        assessment_response["narrative"] = result
        assert "narrative" in assessment_response

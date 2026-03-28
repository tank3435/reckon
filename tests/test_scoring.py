"""
Tests for reckon/analysis/scoring.py
pytest tests/test_scoring.py -v
"""
import pytest
from reckon.analysis.scoring import (
    ScoringEngine, compute_assessment, _composite_to_response,
    _norm_t10y2y, _norm_unemployment, _norm_cpi_yoy, _norm_gdp_growth,
    _norm_recession_probability, _norm_nuclear_probability,
    _norm_existential_probability, _norm_conflict_events,
    _hard_data_score, RESPONSE_MAP, TIER_WEIGHTS, INDICATOR_REGISTRY, _TIER_EXPECTED,
)


def ind(name, raw, tier="economic", source="test"):
    return {"name": name, "raw_value": raw, "tier": tier,
            "source": source, "timestamp": "2026-03-23T12:00:00+00:00"}


class TestNormalizers:

    def test_t10y2y_healthy(self):
        assert _norm_t10y2y(2.5) == 0.0

    def test_t10y2y_inverted(self):
        assert _norm_t10y2y(-1.5) == 100.0

    def test_t10y2y_flat(self):
        score = _norm_t10y2y(0.0)
        assert 40 < score < 70

    def test_unemployment_baseline(self):
        assert _norm_unemployment(4.0) == 0.0

    def test_unemployment_crisis(self):
        assert _norm_unemployment(12.0) == 100.0

    def test_cpi_target(self):
        assert _norm_cpi_yoy(2.0) == 0.0

    def test_cpi_crisis(self):
        assert _norm_cpi_yoy(9.0) == 100.0

    def test_gdp_healthy(self):
        assert _norm_gdp_growth(3.0) == 0.0

    def test_gdp_contraction(self):
        assert _norm_gdp_growth(-5.0) == 100.0

    def test_recession_prob_range(self):
        assert _norm_recession_probability(0.0) == 0.0
        assert _norm_recession_probability(1.0) == 100.0

    def test_nuclear_prob_amplified(self):
        # 10% nuclear use = max on our scale
        assert _norm_nuclear_probability(0.10) == 100.0

    def test_nuclear_prob_small_but_nonzero(self):
        score = _norm_nuclear_probability(0.01)
        assert 0 < score <= 15

    def test_existential_prob_amplified(self):
        # 5% = max; 2% = 40
        assert _norm_existential_probability(0.05) == 100.0
        assert _norm_existential_probability(0.02) == pytest.approx(40.0, abs=1)

    def test_conflict_events_range(self):
        assert _norm_conflict_events(8000) == 0.0
        assert _norm_conflict_events(20000) == 100.0

    def test_all_normalizers_stay_in_bounds(self):
        fns = [_norm_t10y2y, _norm_unemployment, _norm_cpi_yoy,
               _norm_gdp_growth, _norm_recession_probability,
               _norm_nuclear_probability, _norm_existential_probability,
               _norm_conflict_events]
        for fn in fns:
            for val in [-1e6, -1, 0, 0.5, 1, 10, 100, 1e6]:
                r = fn(val)
                assert 0.0 <= r <= 100.0, f"{fn.__name__}({val}) = {r}"


class TestScoringEngine:

    def test_empty_indicators_returns_assessment(self):
        result = compute_assessment([])
        assert result.composite_score == 50.0
        assert result.response.level in RESPONSE_MAP

    def test_calm_conditions_green(self):
        indicators = [
            ind("T10Y2Y", 3.0),
            ind("UNRATE", 3.5),
            ind("CPIAUCSL", 2.0),
            ind("GDPC1", 3.0),
            ind("recession_probability", 0.02),
            ind("nuclear_use_probability", 0.001, "military"),
            ind("nuclear_war_probability", 0.001, "existential"),
            ind("civilizational_collapse_prob", 0.001, "existential"),
            ind("existential_risk_prob", 0.001, "existential"),
            ind("ww3_probability", 0.01, "military"),
            ind("acled_global_events_30d", 7000.0, "military"),
            ind("acled_global_fatalities_30d", 4000.0, "military"),
        ]
        result = compute_assessment(indicators)
        assert result.composite_score < 30
        assert result.response.level == "GREEN"

    def test_stressed_conditions_orange_or_red(self):
        indicators = [
            ind("T10Y2Y", -1.0),
            ind("UNRATE", 9.0),
            ind("CPIAUCSL", 7.0),
            ind("GDPC1", -3.0),
            ind("recession_probability", 0.75),
            ind("nuclear_use_probability", 0.06, "military"),
            ind("ww3_probability", 0.15, "military"),
            ind("acled_global_events_30d", 18000.0, "military"),
            ind("acled_global_fatalities_30d", 22000.0, "military"),
            ind("nuclear_war_probability", 0.04, "existential"),
            ind("civilizational_collapse_prob", 0.03, "existential"),
            ind("existential_risk_prob", 0.04, "existential"),
        ]
        result = compute_assessment(indicators)
        assert result.composite_score >= 50
        assert result.response.level in ("ORANGE", "RED")

    def test_existential_boost_applied(self):
        """High existential score should amplify composite above naive weighted avg."""
        indicators = [
            ind("T10Y2Y", 2.5),
            ind("UNRATE", 4.0),
            ind("nuclear_war_probability", 0.045, "existential"),
            ind("civilizational_collapse_prob", 0.04, "existential"),
            ind("existential_risk_prob", 0.04, "existential"),
            ind("nuclear_use_probability", 0.01, "military"),
            ind("ww3_probability", 0.01, "military"),
        ]
        result = compute_assessment(indicators)
        naive_exist_contribution = result.tier_scores["existential"].score * TIER_WEIGHTS["existential"]
        assert result.composite_score > naive_exist_contribution

    def test_sentiment_dampening_applied(self):
        """
        If news sentiment is elevated but hard data is calm, composite
        should be dampened — sentiment cannot singlehandedly spike the score.
        """
        # High sentiment, calm hard data
        elevated_sentiment = [
            ind("news_sentiment_economic", 80.0),
            ind("news_sentiment_political", 80.0, "political"),
            ind("news_sentiment_military", 80.0, "military"),
            ind("news_sentiment_existential", 80.0, "existential"),
            # Calm hard data
            ind("T10Y2Y", 2.0),
            ind("UNRATE", 4.0),
            ind("CPIAUCSL", 2.5),
            ind("acled_global_events_30d", 8000.0, "military"),
            ind("nuclear_use_probability", 0.005, "military"),
            ind("nuclear_war_probability", 0.005, "existential"),
        ]
        result = compute_assessment(elevated_sentiment)
        hard_composite = result.narrative_data["hard_data_composite"]
        # Composite should not be more than ~20 points above hard data
        assert result.composite_score < hard_composite + 22, (
            f"Composite {result.composite_score} too far above "
            f"hard data {hard_composite} — sentiment dampening may not be working"
        )

    def test_duplicate_indicators_uses_latest(self):
        indicators = [
            {**ind("T10Y2Y", 1.0), "timestamp": "2026-03-20T00:00:00+00:00"},
            {**ind("T10Y2Y", -1.0), "timestamp": "2026-03-23T00:00:00+00:00"},
        ]
        result = compute_assessment(indicators)
        econ_contribs = result.tier_scores["economic"].contributing_indicators
        t10 = next((c for c in econ_contribs if c["name"] == "T10Y2Y"), None)
        assert t10 is not None
        assert t10["raw_value"] == -1.0

    def test_tier_scores_structure(self):
        result = compute_assessment([ind("T10Y2Y", 0.5)])
        assert set(result.tier_scores.keys()) == set(TIER_WEIGHTS.keys())
        for tier, ts in result.tier_scores.items():
            assert 0 <= ts.score <= 100
            assert 0 <= ts.confidence <= 1

    def test_narrative_data_has_methodology_note(self):
        result = compute_assessment([])
        assert "methodology_note" in result.narrative_data
        assert "news sentiment" in result.narrative_data["methodology_note"].lower()

    def test_hard_data_composite_in_narrative(self):
        result = compute_assessment([ind("T10Y2Y", 1.0)])
        assert "hard_data_composite" in result.narrative_data

    def test_response_thresholds(self):
        assert _composite_to_response(10).level == "GREEN"
        assert _composite_to_response(35).level == "YELLOW"
        assert _composite_to_response(60).level == "ORANGE"
        assert _composite_to_response(80).level == "RED"


class TestRegistry:

    def test_tier_weights_sum_to_one(self):
        assert abs(sum(TIER_WEIGHTS.values()) - 1.0) < 0.001

    def test_all_tiers_represented(self):
        tiers = {tier for _, tier, _, _ in INDICATOR_REGISTRY}
        assert tiers == set(TIER_WEIGHTS.keys())

    def test_no_duplicate_names(self):
        names = [name for name, *_ in INDICATOR_REGISTRY]
        assert len(names) == len(set(names))

    def test_sentiment_indicators_low_weight(self):
        """News sentiment indicators must have weight <= 0.12 per bias policy."""
        for name, tier, weight, _ in INDICATOR_REGISTRY:
            if name.startswith("news_sentiment_"):
                assert weight <= 0.12, (
                    f"{name} has weight {weight} — must be <=0.12 per upward bias policy"
                )

    def test_response_map_complete(self):
        assert set(RESPONSE_MAP.keys()) == {"GREEN", "YELLOW", "ORANGE", "RED"}
        for level, rec in RESPONSE_MAP.items():
            assert rec.level == level
            assert rec.actions

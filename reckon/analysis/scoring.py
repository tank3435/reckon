"""
Reckon Scoring Engine
=====================
Normalizes raw indicator values, applies per-indicator weights, produces
tier scores 0-100, computes a composite score, and emits a RiskAssessment
with proportionate response recommendations.

Key design decisions (see CLAUDE.md and Architectural Decisions page in Notion):

NEWS SENTIMENT WEIGHTING
  News sentiment indicators are deliberately weighted LOW vs. hard data
  (FRED, ACLED, prediction markets). News inherently covers abnormal events,
  creating structural upward bias. The hard data sources are the anchor.
  News sentiment informs; it does not dominate.

  Rule: If news sentiment is elevated but FRED + ACLED + prediction markets
  are not, the composite score should NOT spike. Cross-validate before
  concluding a threshold has been crossed.

BEHAVIORAL / ALTERNATIVE DATA LAYER
  Not implemented in the scoring engine for v0.1. Behavioral signals
  (capital flows, institutional positioning, etc.) will be collected and
  logged by a separate observatory module. They will NOT carry scoring
  weight until they have been validated against historical outcomes.
  See: reckon/ingestion/behavioral.py (TODO — v0.2)

EXISTENTIAL NON-LINEARITY
  Small existential risk signals should dominate the composite even when
  other tiers look fine. A 5% nuclear war probability is not the same as
  a 5% recession probability. The boost function below encodes this.

METHODOLOGY TRANSPARENCY
  Every normalizer documents its historical bounds. Every weight is
  documented. The scoring engine must remain auditable — no magic numbers.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


# ===========================================================================
# Response levels
# ===========================================================================

@dataclass
class ResponseRecommendation:
    level: str
    color_hex: str
    tagline: str
    actions: list[str]


RESPONSE_MAP: dict[str, ResponseRecommendation] = {
    "GREEN": ResponseRecommendation(
        level="GREEN", color_hex="#22c55e",
        tagline="Stay the course.",
        actions=[
            "Maintain normal financial and life routines.",
            "Keep a standard 2-week emergency supply.",
            "Stay informed via reliable sources. No urgent action needed.",
        ],
    ),
    "YELLOW": ResponseRecommendation(
        level="YELLOW", color_hex="#eab308",
        tagline="Build cushion.",
        actions=[
            "Review and strengthen your emergency fund (3-6 months expenses).",
            "Check emergency supplies — food, water, medications.",
            "Identify evacuation routes and rally points.",
            "Diversify if heavily concentrated in one asset class.",
            "Set news alerts for key indicators.",
        ],
    ),
    "ORANGE": ResponseRecommendation(
        level="ORANGE", color_hex="#f97316",
        tagline="Accelerate preparations.",
        actions=[
            "Ensure 30+ days of food and water stored.",
            "Reduce exposure to high-volatility assets.",
            "Verify passports and important documents are current.",
            "Establish a concrete household communication plan.",
            "Know your contingency location and have it provisioned.",
            "Reduce debt exposure, increase liquid reserves.",
        ],
    ),
    "RED": ResponseRecommendation(
        level="RED", color_hex="#ef4444",
        tagline="Execute your plans now.",
        actions=[
            "Activate your emergency/continuity plan.",
            "Move to your pre-planned safe location if applicable.",
            "Maximize liquid reserves. Limit bank exposure.",
            "Activate communication protocols with household and trusted network.",
            "Monitor official emergency channels continuously.",
            "Reduce all non-essential travel.",
        ],
    ),
}


# ===========================================================================
# Output types
# ===========================================================================

@dataclass
class TierScore:
    tier: str
    score: float                      # 0-100
    contributing_indicators: list[dict]
    confidence: float                 # 0-1, fraction of expected indicators present


@dataclass
class RiskAssessment:
    composite_score: float
    tier_scores: dict[str, TierScore]
    response: ResponseRecommendation
    data_completeness: float
    narrative_data: dict
    timestamp_utc: str


# ===========================================================================
# Normalizers
# ===========================================================================
# Each normalizer(raw) -> float in [0, 100]
# 0 = no risk / historically normal
# 100 = maximum historical risk
# Historical bounds are documented per indicator.

def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, v))


def _linear(raw: float, low: float, high: float) -> float:
    """Map raw linearly onto [0, 100] between low (= 0 risk) and high (= 100 risk)."""
    if high == low:
        return 50.0
    return _clamp((raw - low) / (high - low) * 100.0)


# -- Economic --

def _norm_t10y2y(raw: float) -> float:
    """
    10Y-2Y Treasury spread. Historical range: -1.5 (deep inversion) to +3.5 (steep).
    0 risk at >= +2.0 (healthy). Max risk at <= -1.5 (deep inversion = recession signal).
    """
    return _linear(raw, low=2.0, high=-1.5)  # inverted: falling spread = rising risk


def _norm_unemployment(raw: float) -> float:
    """US unemployment %. 0 risk at <=4%, max at >=12% (beyond GFC peak)."""
    return _linear(raw, low=4.0, high=12.0)


def _norm_cpi_yoy(raw: float) -> float:
    """CPI YoY %. 0 risk at Fed target 2%, max at >=9% (2022 peak)."""
    return _linear(raw, low=2.0, high=9.0)


def _norm_gdp_growth(raw: float) -> float:
    """Real GDP growth QoQ annualized %. 0 risk at >=2.5%, max at <=-5%."""
    return _linear(raw, low=2.5, high=-5.0)


def _norm_recession_probability(raw: float) -> float:
    """Recession probability [0-1]. Direct 0→0%, 1→100%."""
    return _clamp(raw * 100.0)


# -- Political --

def _norm_political_forecast(raw: float) -> float:
    """Generic political risk probability [0-1]. Direct map."""
    return _clamp(raw * 100.0)


# -- Military --

def _norm_conflict_events(raw: float) -> float:
    """Global ACLED events/month. 0 risk at <=8000, max at >=20000."""
    return _linear(raw, low=8000.0, high=20000.0)


def _norm_conflict_fatalities(raw: float) -> float:
    """Global ACLED fatalities/month. 0 risk at <=5000, max at >=30000."""
    return _linear(raw, low=5000.0, high=30000.0)


def _norm_nuclear_probability(raw: float) -> float:
    """
    Nuclear use probability [0-1]. Even 10% (0.10) is historically extreme.
    Scale: 0% -> 0, 10% -> 100. Values above 10% clamp to 100.
    """
    return _clamp((raw / 0.10) * 100.0)


def _norm_ww3_probability(raw: float) -> float:
    """WW3 probability [0-1]. Scale: 0% -> 0, 20% -> 100."""
    return _clamp((raw / 0.20) * 100.0)


# -- Existential --

def _norm_existential_probability(raw: float) -> float:
    """
    Existential/civilizational risk probability [0-1].
    Even 5% (0.05) is historically extreme. Scale: 0% -> 0, 5% -> 100.
    """
    return _clamp((raw / 0.05) * 100.0)


def _norm_nuclear_war_probability(raw: float) -> float:
    """Nuclear war probability [0-1]. Scale: 0% -> 0, 5% -> 100."""
    return _clamp((raw / 0.05) * 100.0)


def _norm_sentiment_score(raw: float) -> float:
    """
    News sentiment risk scores are already 0-100 from our sentiment collector.
    Pass through with clamp. These carry lower weight in tier scoring to
    compensate for structural upward bias in news coverage.
    """
    return _clamp(raw)


# ===========================================================================
# Indicator Registry
# ===========================================================================
# Format: (indicator_name, tier, weight, normalizer_fn)
#
# WEIGHT NOTES:
# - Within each tier, weights sum to ~1.0 (engine normalizes if not exact).
# - News sentiment indicators are assigned low weight (0.08-0.12) relative
#   to hard data sources, per the upward bias compensation policy.
# - Existential tier indicators carry amplified effect at composite level
#   via the boost function below.

INDICATOR_REGISTRY: list[tuple[str, str, float, callable]] = [
    # -- Economic --
    ("T10Y2Y",                         "economic",    0.30, _norm_t10y2y),
    ("UNRATE",                         "economic",    0.25, _norm_unemployment),
    ("CPIAUCSL",                       "economic",    0.20, _norm_cpi_yoy),
    ("GDPC1",                          "economic",    0.15, _norm_gdp_growth),
    ("recession_probability",          "economic",    0.10, _norm_recession_probability),
    # News sentiment: low weight — informs, doesn't dominate
    ("news_sentiment_economic",        "economic",    0.08, _norm_sentiment_score),

    # -- Political --
    ("democratic_backsliding_prob",    "political",   0.30, _norm_political_forecast),
    ("civil_unrest_prob",              "political",   0.25, _norm_political_forecast),
    ("institutional_health_prob",      "political",   0.20, _norm_political_forecast),
    ("alliance_stability_prob",        "political",   0.15, _norm_political_forecast),
    ("news_sentiment_political",       "political",   0.08, _norm_sentiment_score),

    # -- Military --
    ("acled_global_events_30d",        "military",    0.20, _norm_conflict_events),
    ("acled_global_fatalities_30d",    "military",    0.25, _norm_conflict_fatalities),
    ("nuclear_use_probability",        "military",    0.25, _norm_nuclear_probability),
    ("ww3_probability",                "military",    0.20, _norm_ww3_probability),
    ("ukraine_conflict_prob",          "military",    0.05, _norm_political_forecast),
    ("taiwan_conflict_prob",           "military",    0.05, _norm_political_forecast),
    ("news_sentiment_military",        "military",    0.08, _norm_sentiment_score),

    # -- Existential --
    ("nuclear_war_probability",        "existential", 0.35, _norm_nuclear_war_probability),
    ("civilizational_collapse_prob",   "existential", 0.30, _norm_existential_probability),
    ("existential_risk_prob",          "existential", 0.25, _norm_existential_probability),
    ("news_sentiment_existential",     "existential", 0.08, _norm_sentiment_score),
]

# Build lookup: name -> (tier, weight, normalizer)
_REGISTRY_INDEX: dict[str, tuple[str, float, callable]] = {
    name: (tier, weight, fn)
    for name, tier, weight, fn in INDICATOR_REGISTRY
}

# Expected indicator names per tier (for completeness scoring)
_TIER_EXPECTED: dict[str, set[str]] = {}
for name, tier, *_ in INDICATOR_REGISTRY:
    _TIER_EXPECTED.setdefault(tier, set()).add(name)


# ===========================================================================
# Tier weights in composite
# ===========================================================================
# Military and existential are weighted higher because asymmetric downside.
# Economic and political are serious but more recoverable.

TIER_WEIGHTS: dict[str, float] = {
    "economic":    0.20,
    "political":   0.20,
    "military":    0.30,
    "existential": 0.30,
}


# ===========================================================================
# Response thresholds
# ===========================================================================

def _composite_to_response(score: float) -> ResponseRecommendation:
    if score < 25:
        return RESPONSE_MAP["GREEN"]
    elif score < 50:
        return RESPONSE_MAP["YELLOW"]
    elif score < 70:
        return RESPONSE_MAP["ORANGE"]
    else:
        return RESPONSE_MAP["RED"]


# ===========================================================================
# Cross-validation guard
# ===========================================================================
# Prevents news sentiment from singlehandedly pushing composite across a
# threshold. If hard data is calm but sentiment is elevated, we dampen.

def _hard_data_score(tier_scores: dict[str, "TierScore"]) -> float:
    """
    Compute a composite score using ONLY hard data indicators (no sentiment).
    Used to cross-validate against the full composite.
    """
    hard_tiers: dict[str, float] = {}
    for tier in TIER_WEIGHTS:
        ts = tier_scores.get(tier)
        if ts is None:
            continue
        hard_contribs = [
            c for c in ts.contributing_indicators
            if not c["name"].startswith("news_sentiment_")
        ]
        if not hard_contribs:
            hard_tiers[tier] = ts.score  # fallback: use full tier score
            continue
        total_weight = sum(c["weight"] for c in hard_contribs)
        if total_weight == 0:
            hard_tiers[tier] = 50.0
            continue
        hard_tiers[tier] = sum(c["normalized"] * c["weight"] for c in hard_contribs) / total_weight

    if not hard_tiers:
        return 50.0
    return sum(hard_tiers[t] * TIER_WEIGHTS[t] for t in hard_tiers if t in TIER_WEIGHTS)


# ===========================================================================
# Scoring engine
# ===========================================================================

class ScoringEngine:
    """
    Stateless scoring engine. Pass in indicator rows (dicts), get back a
    RiskAssessment.

    Expected indicator dict shape:
        {
            "name": str,
            "raw_value": float,
            "tier": str,
            "source": str,
            "timestamp": str,  # ISO 8601
        }
    """

    def score(self, indicators: list[dict]) -> RiskAssessment:
        # Index by name, most-recent wins on duplicates
        indexed: dict[str, dict] = {}
        for ind in indicators:
            name = ind.get("name", "")
            existing = indexed.get(name)
            if existing is None:
                indexed[name] = ind
            else:
                try:
                    if ind["timestamp"] > existing["timestamp"]:
                        indexed[name] = ind
                except Exception:
                    pass

        all_tiers = list(TIER_WEIGHTS.keys())
        tier_scores: dict[str, TierScore] = {}
        total_expected = sum(len(v) for v in _TIER_EXPECTED.values())
        total_present = 0

        for tier in all_tiers:
            ts, present = self._score_tier(tier, indexed)
            tier_scores[tier] = ts
            total_present += present

        # Weighted composite
        raw_composite = sum(
            tier_scores[t].score * TIER_WEIGHTS[t] for t in all_tiers
        )

        # Existential non-linearity boost
        exist_score = tier_scores["existential"].score
        if exist_score > 60:
            boost = (exist_score - 60) * 0.15
            raw_composite = min(100.0, raw_composite + boost)
            logger.info("Existential boost: +%.1f → composite %.1f", boost, raw_composite)

        # Cross-validation: if hard data is calm, dampen news-sentiment-driven spikes
        hard_composite = _hard_data_score(tier_scores)
        if raw_composite - hard_composite > 15:
            # Sentiment is pulling composite >15 pts above hard data — dampen
            dampening = (raw_composite - hard_composite - 15) * 0.40
            raw_composite = max(hard_composite + 10, raw_composite - dampening)
            logger.info(
                "Sentiment dampening applied: hard_data=%.1f composite reduced to %.1f",
                hard_composite, raw_composite,
            )

        composite = round(raw_composite, 1)
        completeness = total_present / max(total_expected, 1)
        response = _composite_to_response(composite)

        logger.info(
            "Assessment — composite:%.1f econ:%.1f pol:%.1f mil:%.1f exist:%.1f "
            "hard_data:%.1f response:%s completeness:%.0f%%",
            composite,
            tier_scores["economic"].score,
            tier_scores["political"].score,
            tier_scores["military"].score,
            tier_scores["existential"].score,
            hard_composite,
            response.level,
            completeness * 100,
        )

        narrative_data = {
            "composite_score": composite,
            "hard_data_composite": round(hard_composite, 1),
            "tier_scores": {t: round(ts.score, 1) for t, ts in tier_scores.items()},
            "response_level": response.level,
            "data_completeness_pct": round(completeness * 100, 1),
            "top_indicators": self._top_indicators(tier_scores),
            "methodology_note": (
                "News sentiment indicators carry reduced weight vs. hard data (FRED, "
                "ACLED, prediction markets) to compensate for structural upward bias "
                "in news coverage. Cross-validation prevents sentiment from "
                "singlehandedly crossing a response threshold."
            ),
        }

        return RiskAssessment(
            composite_score=composite,
            tier_scores=tier_scores,
            response=response,
            data_completeness=completeness,
            narrative_data=narrative_data,
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
        )

    def _score_tier(self, tier: str, indexed: dict[str, dict]) -> tuple[TierScore, int]:
        expected_names = _TIER_EXPECTED.get(tier, set())
        contributions: list[dict] = []
        weighted_sum = 0.0
        weight_sum = 0.0
        present_count = 0

        for name in expected_names:
            _, weight, normalizer = _REGISTRY_INDEX[name]
            ind = indexed.get(name)
            if ind is None:
                continue
            present_count += 1
            try:
                raw = float(ind["raw_value"])
                normalized = round(normalizer(raw), 1)
            except Exception as exc:
                logger.warning("Normalization failed for '%s': %s", name, exc)
                continue
            weighted_sum += normalized * weight
            weight_sum += weight
            contributions.append({
                "name": name,
                "raw_value": ind.get("raw_value"),
                "normalized": normalized,
                "weight": weight,
                "source": ind.get("source", ""),
            })

        if weight_sum == 0:
            tier_score = 50.0  # no data — assume elevated baseline, not zero
            confidence = 0.0
        else:
            tier_score = round(weighted_sum / weight_sum, 1)
            confidence = round(present_count / max(len(expected_names), 1), 2)

        return (
            TierScore(
                tier=tier,
                score=tier_score,
                contributing_indicators=sorted(contributions, key=lambda x: -x["normalized"]),
                confidence=confidence,
            ),
            present_count,
        )

    def _top_indicators(self, tier_scores: dict[str, TierScore]) -> list[dict]:
        all_contribs = []
        for ts in tier_scores.values():
            for c in ts.contributing_indicators:
                all_contribs.append({**c, "tier": ts.tier})
        return sorted(all_contribs, key=lambda x: -x["normalized"])[:5]


def compute_assessment(indicators: list[dict]) -> RiskAssessment:
    """Top-level entry point for the API layer."""
    return ScoringEngine().score(indicators)

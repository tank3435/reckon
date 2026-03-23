"""
Core scoring engine.

Scoring pipeline:
1. Load most recent indicator value per (tier, name) from the DB.
2. Load baselines for each indicator name.
3. Compute z-score: (value - mean) / stddev, clamped to [-clamp, +clamp].
4. Map to 0–100: ((z + clamp) / (2 * clamp)) * 100.
   Higher score = worse (further from normal / more alarming).
5. Compute weighted average within each tier → TierScore.
6. Compute weighted average across tiers (config weights) → composite score.
7. Derive severity label and recommendations.
8. Persist RiskAssessment + TierScore rows (immutable append).
"""

from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from reckon.analysis.weights import DEFAULT_WEIGHT, INDICATOR_WEIGHTS
from reckon.config import settings
from reckon.models.assessment import RiskAssessment, TierScore
from reckon.models.indicator import Baseline, Indicator, Tier

SEVERITY_THRESHOLDS = [
    (80, "CRITICAL", "Immediate action warranted. Serious disruption is likely or underway."),
    (60, "HIGH", "Elevated risk across multiple dimensions. Monitor closely and prepare."),
    (40, "ELEVATED", "Above-baseline stress in several indicators. Stay informed."),
    (20, "GUARDED", "Mild deviation from historical norms. Normal vigilance sufficient."),
    (0,  "NORMAL",   "Conditions within historical norms. No unusual action needed."),
]

TIER_WEIGHTS = {
    Tier.ECONOMIC:    lambda: settings.tier_weight_economic,
    Tier.POLITICAL:   lambda: settings.tier_weight_political,
    Tier.MILITARY:    lambda: settings.tier_weight_military,
    Tier.EXISTENTIAL: lambda: settings.tier_weight_existential,
}


def _zscore_to_100(value: float, mean: float, stddev: float, clamp: float) -> float:
    if stddev == 0:
        return 50.0
    z = (value - mean) / stddev
    z = max(-clamp, min(clamp, z))
    return ((z + clamp) / (2 * clamp)) * 100.0


def _severity(score: float) -> tuple[str, str]:
    for threshold, label, desc in SEVERITY_THRESHOLDS:
        if score >= threshold:
            return label, desc
    return "NORMAL", ""


async def score_assessment(db: AsyncSession) -> RiskAssessment:
    clamp = settings.zscore_clamp

    # Fetch latest value per indicator name within each tier
    latest_stmt = text(
        """
        SELECT DISTINCT ON (tier, name)
            tier, name, raw_value
        FROM indicators
        ORDER BY tier, name, collected_at DESC
        """
    )
    rows = (await db.execute(latest_stmt)).fetchall()

    # Load all baselines keyed by indicator_name
    baselines: dict[str, Baseline] = {
        b.indicator_name: b
        for b in (await db.execute(select(Baseline))).scalars().all()
    }

    tier_buckets: dict[str, list[tuple[float, float]]] = {t.value: [] for t in Tier}

    for row in rows:
        tier, name, raw_value = row.tier, row.name, row.raw_value
        baseline = baselines.get(name)
        if baseline is None:
            continue
        indicator_score = _zscore_to_100(raw_value, baseline.mean, baseline.stddev, clamp)
        weight = INDICATOR_WEIGHTS.get(name, DEFAULT_WEIGHT) * baseline.weight
        tier_buckets[tier].append((indicator_score, weight))

    tier_score_records: list[TierScore] = []
    composite_numerator = 0.0
    composite_denominator = 0.0

    for tier_enum in Tier:
        tier_val = tier_enum.value
        bucket = tier_buckets[tier_val]
        if not bucket:
            tier_score = 50.0  # unknown → mid-range
            count = 0
        else:
            total_weight = sum(w for _, w in bucket)
            tier_score = sum(s * w for s, w in bucket) / total_weight if total_weight else 50.0
            count = len(bucket)

        tier_weight = TIER_WEIGHTS[tier_enum]()
        composite_numerator += tier_score * tier_weight
        composite_denominator += tier_weight

        tier_score_records.append(
            TierScore(tier=tier_val, score=round(tier_score, 2), indicator_count=count)
        )

    composite = composite_numerator / composite_denominator if composite_denominator else 50.0
    composite = round(composite, 2)
    severity_label, recommendations = _severity(composite)

    assessment = RiskAssessment(
        composite_score=composite,
        severity_label=severity_label,
        summary=f"Composite risk score: {composite}/100 ({severity_label})",
        recommendations=recommendations,
        indicator_count=len(rows),
        assessed_at=datetime.utcnow(),
        tier_scores=tier_score_records,
    )
    db.add(assessment)
    await db.commit()
    await db.refresh(assessment)
    return assessment

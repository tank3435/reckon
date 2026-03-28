"""
GET /api/assessment
Returns the current scored risk assessment from all stored indicators.
"""

from __future__ import annotations
import asyncio
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reckon.db import get_db
from reckon.models.indicator import Indicator
from reckon.analysis.scoring import compute_assessment, RiskAssessment
from reckon.analysis.narrative import generate_narrative

logger = logging.getLogger(__name__)
router = APIRouter()


def _to_dict(ind: Indicator) -> dict:
    return {
        "name": ind.name,
        "raw_value": float(ind.raw_value),
        "unit": ind.unit,
        "tier": ind.tier,
        "source": ind.source,
        "source_id": ind.source_id,
        "timestamp": ind.collected_at.isoformat() if ind.collected_at else None,
    }


@router.get("/assessment")
async def get_assessment(db: AsyncSession = Depends(get_db)):
    try:
        indicators_raw = (await db.execute(select(Indicator))).scalars().all()
    except Exception as exc:
        logger.error("DB query failed: %s", exc)
        raise HTTPException(status_code=500, detail="Database error")

    if not indicators_raw:
        raise HTTPException(
            status_code=503,
            detail="No indicator data available. Run ingestion first.",
        )

    assessment: RiskAssessment = compute_assessment([_to_dict(i) for i in indicators_raw])

    response = {
        "composite_score": assessment.composite_score,
        "response": {
            "level": assessment.response.level,
            "color_hex": assessment.response.color_hex,
            "tagline": assessment.response.tagline,
            "actions": assessment.response.actions,
        },
        "tier_scores": {
            tier: {
                "score": ts.score,
                "confidence": ts.confidence,
                "top_indicators": ts.contributing_indicators[:3],
            }
            for tier, ts in assessment.tier_scores.items()
        },
        "data_completeness": assessment.data_completeness,
        "narrative_data": assessment.narrative_data,
        "timestamp_utc": assessment.timestamp_utc,
        "indicator_count": len(indicators_raw),
    }

    loop = asyncio.get_event_loop()
    narrative_result = await loop.run_in_executor(
        None, generate_narrative, assessment.narrative_data
    )

    if narrative_result is not None:
        response["narrative"] = narrative_result

    return response

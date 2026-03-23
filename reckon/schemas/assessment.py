from datetime import datetime

from pydantic import BaseModel


class TierScoreOut(BaseModel):
    tier: str
    score: float
    indicator_count: int

    model_config = {"from_attributes": True}


class RiskAssessmentOut(BaseModel):
    id: int
    composite_score: float
    severity_label: str
    summary: str
    recommendations: str
    indicator_count: int
    assessed_at: datetime
    tier_scores: list[TierScoreOut]

    model_config = {"from_attributes": True}


class AssessmentListOut(BaseModel):
    assessments: list[RiskAssessmentOut]
    total: int

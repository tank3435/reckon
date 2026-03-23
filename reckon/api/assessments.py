from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from reckon.analysis.scorer import score_assessment
from reckon.db import get_db
from reckon.models.assessment import RiskAssessment
from reckon.schemas.assessment import AssessmentListOut, RiskAssessmentOut

router = APIRouter(prefix="/assessments", tags=["assessments"])


@router.post("/run", response_model=RiskAssessmentOut, status_code=201)
async def run_assessment(db: AsyncSession = Depends(get_db)) -> RiskAssessmentOut:
    """Trigger a new scoring run against the current indicator data."""
    assessment = await score_assessment(db)
    return RiskAssessmentOut.model_validate(assessment)


@router.get("/latest", response_model=RiskAssessmentOut)
async def get_latest(db: AsyncSession = Depends(get_db)) -> RiskAssessmentOut:
    stmt = (
        select(RiskAssessment)
        .options(selectinload(RiskAssessment.tier_scores))
        .order_by(RiskAssessment.assessed_at.desc())
        .limit(1)
    )
    result = (await db.execute(stmt)).scalar_one_or_none()
    if result is None:
        raise HTTPException(status_code=404, detail="No assessments found. Run /assessments/run first.")
    return RiskAssessmentOut.model_validate(result)


@router.get("/", response_model=AssessmentListOut)
async def list_assessments(
    limit: int = 20,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
) -> AssessmentListOut:
    total = (await db.execute(select(func.count()).select_from(RiskAssessment))).scalar_one()
    stmt = (
        select(RiskAssessment)
        .options(selectinload(RiskAssessment.tier_scores))
        .order_by(RiskAssessment.assessed_at.desc())
        .limit(limit)
        .offset(offset)
    )
    rows = (await db.execute(stmt)).scalars().all()
    return AssessmentListOut(
        assessments=[RiskAssessmentOut.model_validate(r) for r in rows],
        total=total,
    )


@router.get("/{assessment_id}", response_model=RiskAssessmentOut)
async def get_assessment(
    assessment_id: int, db: AsyncSession = Depends(get_db)
) -> RiskAssessmentOut:
    stmt = (
        select(RiskAssessment)
        .options(selectinload(RiskAssessment.tier_scores))
        .where(RiskAssessment.id == assessment_id)
    )
    result = (await db.execute(stmt)).scalar_one_or_none()
    if result is None:
        raise HTTPException(status_code=404, detail="Assessment not found.")
    return RiskAssessmentOut.model_validate(result)

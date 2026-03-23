from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from reckon.db import get_db
from reckon.models.indicator import Baseline, Indicator
from reckon.schemas.indicator import BaselineIn, BaselineOut, IndicatorOut

router = APIRouter(prefix="/indicators", tags=["indicators"])


@router.get("/", response_model=list[IndicatorOut])
async def list_indicators(
    tier: str | None = None,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
) -> list[IndicatorOut]:
    stmt = select(Indicator).order_by(Indicator.collected_at.desc()).limit(limit)
    if tier:
        stmt = stmt.where(Indicator.tier == tier)
    rows = (await db.execute(stmt)).scalars().all()
    return [IndicatorOut.model_validate(r) for r in rows]


@router.get("/baselines", response_model=list[BaselineOut])
async def list_baselines(db: AsyncSession = Depends(get_db)) -> list[BaselineOut]:
    rows = (await db.execute(select(Baseline))).scalars().all()
    return [BaselineOut.model_validate(r) for r in rows]


@router.post("/baselines", response_model=BaselineOut, status_code=201)
async def upsert_baseline(payload: BaselineIn, db: AsyncSession = Depends(get_db)) -> BaselineOut:
    """Create or update a baseline for a named indicator."""
    from sqlalchemy.dialects.postgresql import insert

    stmt = (
        insert(Baseline)
        .values(**payload.model_dump())
        .on_conflict_do_update(
            constraint="uq_baseline_indicator",
            set_={
                "mean": payload.mean,
                "stddev": payload.stddev,
                "weight": payload.weight,
            },
        )
        .returning(Baseline)
    )
    result = (await db.execute(stmt)).scalar_one()
    await db.commit()
    return BaselineOut.model_validate(result)

from dataclasses import asdict

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from reckon.db import get_db
from reckon.ingestion import (
    EconomicIngester,
    ExistentialIngester,
    IngestionResult,
    MilitaryIngester,
    PoliticalIngester,
)

router = APIRouter(prefix="/ingest", tags=["ingestion"])

_INGESTERS = {
    "economic": EconomicIngester,
    "political": PoliticalIngester,
    "military": MilitaryIngester,
    "existential": ExistentialIngester,
}


@router.post("/all")
async def ingest_all(db: AsyncSession = Depends(get_db)) -> dict:
    """Run all four tier ingesters and return a summary."""
    results = {}
    for name, cls in _INGESTERS.items():
        ingester = cls()
        result: IngestionResult = await ingester.ingest(db)
        await ingester.close()
        results[name] = asdict(result)
    return results


@router.post("/{tier}")
async def ingest_tier(tier: str, db: AsyncSession = Depends(get_db)) -> dict:
    """Run a single tier ingester."""
    cls = _INGESTERS.get(tier)
    if cls is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail=f"Unknown tier: {tier}. Valid: {list(_INGESTERS)}")
    ingester = cls()
    result = await ingester.ingest(db)
    await ingester.close()
    return asdict(result)

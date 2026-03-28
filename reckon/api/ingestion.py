import asyncio
from dataclasses import asdict

from fastapi import APIRouter, Depends
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from reckon.db import get_db
from reckon.ingestion import (
    AcledIngester,
    EconomicIngester,
    ExistentialIngester,
    IngestionResult,
    MetaculusIngester,
    MilitaryIngester,
    PoliticalIngester,
    PolymarketIngester,
)
from reckon.ingestion.news_sentiment import NewsSentimentIngester
from reckon.models.indicator import Indicator

router = APIRouter(prefix="/ingest", tags=["ingestion"])

_INGESTERS = {
    "economic": EconomicIngester,
    "political": PoliticalIngester,
    "military": MilitaryIngester,
    "existential": ExistentialIngester,
    "polymarket": PolymarketIngester,
    "metaculus": MetaculusIngester,
    "acled": AcledIngester,
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


@router.post("/news_sentiment")
async def ingest_news_sentiment(db: AsyncSession = Depends(get_db)) -> dict:
    """Fetch news sentiment scores via RSS + Claude and store in the indicators table."""
    ingester = NewsSentimentIngester()
    # fetch() is synchronous (feedparser + Anthropic SDK) — run off the event loop
    loop = asyncio.get_event_loop()
    indicators = await loop.run_in_executor(None, ingester.fetch)

    inserted, skipped, errors = 0, 0, []
    for ind in indicators:
        try:
            stmt = (
                insert(Indicator)
                .values(
                    tier=ind.tier,
                    name=ind.name,
                    source=ind.source,
                    source_id=ind.source_id,
                    raw_value=ind.raw_value,
                    unit=ind.unit,
                    collected_at=ind.timestamp,
                )
                .on_conflict_do_update(
                    constraint="uq_indicator_source_id",
                    set_={"raw_value": ind.raw_value, "collected_at": ind.timestamp},
                )
            )
            await db.execute(stmt)
            inserted += 1
        except Exception as exc:
            errors.append(f"{ind.source_id}: {exc}")
            skipped += 1

    await db.commit()
    return {"tier": "news_sentiment", "inserted": inserted, "skipped": skipped, "errors": errors}


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

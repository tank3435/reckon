"""
Base ingester protocol. Each tier subclass implements `fetch()` which returns
a list of raw indicator dicts. The base class handles upsert into the DB.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from reckon.models.indicator import Indicator


@dataclass
class RawIndicator:
    tier: str
    name: str
    source: str
    source_id: str
    raw_value: float
    unit: str = ""
    collected_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class IngestionResult:
    tier: str
    inserted: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


class BaseIngester(ABC):
    tier: str  # must be set by subclass

    def __init__(self, http_client: httpx.AsyncClient | None = None):
        self._client = http_client or httpx.AsyncClient(timeout=30.0)

    @abstractmethod
    async def fetch(self) -> list[RawIndicator]:
        """Fetch raw indicators from external sources."""
        ...

    async def ingest(self, db: AsyncSession) -> IngestionResult:
        result = IngestionResult(tier=self.tier)
        try:
            raw = await self.fetch()
        except Exception as exc:
            result.errors.append(f"fetch failed: {exc}")
            return result

        for item in raw:
            try:
                stmt = (
                    insert(Indicator)
                    .values(
                        tier=item.tier,
                        name=item.name,
                        source=item.source,
                        source_id=item.source_id,
                        raw_value=item.raw_value,
                        unit=item.unit,
                        collected_at=item.collected_at,
                    )
                    .on_conflict_do_update(
                        constraint="uq_indicator_source_id",
                        set_={"raw_value": item.raw_value, "collected_at": item.collected_at},
                    )
                )
                await db.execute(stmt)
                result.inserted += 1
            except Exception as exc:
                result.errors.append(f"{item.source_id}: {exc}")
                result.skipped += 1

        await db.commit()
        return result

    async def close(self) -> None:
        await self._client.aclose()

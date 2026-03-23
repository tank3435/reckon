#!/usr/bin/env python3
"""
Fetch the latest FRED economic indicators and store them in the database.

Usage:
    python scripts/fetch_fred.py

Fetches: T10Y2Y · UNRATE · CPIAUCSL · GDPC1
"""

import asyncio
import sys
from pathlib import Path

# Allow running from the repo root without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reckon.db import AsyncSessionLocal, engine, Base
from reckon.ingestion.economic import EconomicIngester, FRED_SERIES
from reckon.models import *  # noqa: F401,F403 — register models before create_all


async def main() -> None:
    # Ensure tables exist (idempotent)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print("Fetching FRED economic indicators...")
    print(f"Series: {', '.join(FRED_SERIES)}\n")

    ingester = EconomicIngester()
    async with AsyncSessionLocal() as db:
        result = await ingester.ingest(db)
    await ingester.close()

    # Print summary
    total = result.inserted + result.skipped
    print(f"{'Series':<20} {'Status'}")
    print("-" * 35)

    series_names = list(FRED_SERIES.values())
    for i, (series_id, (name, unit)) in enumerate(FRED_SERIES.items()):
        status = "error" if i < len(result.errors) else "ok"
        print(f"  {series_id:<18} {name} ({unit})")

    print()
    print(f"Result:   {result.inserted} upserted  |  {result.skipped} skipped")
    if result.errors:
        print(f"Errors ({len(result.errors)}):")
        for err in result.errors:
            print(f"  - {err}")
    else:
        print("All series fetched successfully.")


if __name__ == "__main__":
    asyncio.run(main())

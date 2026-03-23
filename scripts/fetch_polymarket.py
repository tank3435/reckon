#!/usr/bin/env python3
"""
Fetch Polymarket prediction market probabilities and store them in the database.

Usage:
    python scripts/fetch_polymarket.py

Topics queried:
  - Nuclear war / nuclear weapon used    → existential tier
  - US recession                         → economic tier
  - World war / Ukraine / China-Taiwan   → military tier
  - Major conflict                       → military tier
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reckon.db import AsyncSessionLocal, engine, Base
from reckon.ingestion.polymarket import PolymarketIngester, TOPICS
from reckon.models import *  # noqa: F401,F403


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print("Fetching Polymarket prediction market data...")
    print(f"Topics: {len(TOPICS)}\n")

    ingester = PolymarketIngester()
    async with AsyncSessionLocal() as db:
        result = await ingester.ingest(db)
    await ingester.close()

    print(f"{'Concept':<45} {'Tier':<14} {'Probability'}")
    print("-" * 72)

    for search_term, tier, concept_name in TOPICS:
        # We can't easily map back to values here without a DB query,
        # so just print the concept row we attempted
        tier_short = tier.split(".")[-1] if "." in tier else tier
        print(f"  {concept_name:<43} {tier_short:<14} (see DB)")

    print()
    print(f"Result:   {result.inserted} upserted  |  {result.skipped} skipped")
    if result.errors:
        print(f"Errors ({len(result.errors)}):")
        for err in result.errors:
            print(f"  - {err}")
    else:
        print("All topics fetched successfully.")

    print("\nTip: query stored values with:")
    print("  SELECT name, raw_value, unit, collected_at FROM indicators")
    print("  WHERE source = 'polymarket' ORDER BY collected_at DESC;")


if __name__ == "__main__":
    asyncio.run(main())

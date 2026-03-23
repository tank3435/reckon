#!/usr/bin/env python3
"""
Fetch Metaculus community forecasts and store them in the database.

Requires METACULUS_API_TOKEN in your .env file.
Get a free token at: https://metaculus.com/aib

Usage:
    python scripts/fetch_metaculus.py

Topics queried:
  - Nuclear war                → existential
  - US recession               → economic
  - Major armed conflict       → military
  - Civilizational collapse    → existential
  - Existential risk           → existential

Two indicator rows are stored per topic:
  - <concept>_probability  (0–100 scale, community median forecast)
  - <concept>_forecasters  (raw count, measures question credibility)
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reckon.config import settings
from reckon.db import AsyncSessionLocal, Base, engine
from reckon.ingestion.metaculus import TOPICS, MetaculusIngester
from reckon.models import *  # noqa: F401,F403


async def main() -> None:
    if not settings.metaculus_api_token:
        print("Warning: METACULUS_API_TOKEN not set — storing stub data.")
        print("Get a free token at https://metaculus.com/aib\n")
    else:
        print("Metaculus API token: configured")
        print()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print(f"Fetching {len(TOPICS)} Metaculus topics...\n")

    ingester = MetaculusIngester()
    async with AsyncSessionLocal() as db:
        result = await ingester.ingest(db)
    await ingester.close()

    print(f"{'Concept':<32} {'Tier':<14} {'Indicators stored'}")
    print("-" * 60)
    for _search_term, tier, concept in TOPICS:
        tier_label = tier.split(".")[-1] if "." in tier else tier
        print(f"  {concept:<30} {tier_label:<14} probability + forecasters")

    print()
    print(f"Result:   {result.inserted} upserted  |  {result.skipped} skipped")
    if result.errors:
        print(f"Errors ({len(result.errors)}):")
        for err in result.errors:
            print(f"  - {err}")
    else:
        print("Done.")

    print("\nQuery stored values:")
    print("  SELECT name, raw_value, unit, collected_at")
    print("  FROM indicators WHERE source = 'metaculus'")
    print("  ORDER BY name;")


if __name__ == "__main__":
    asyncio.run(main())

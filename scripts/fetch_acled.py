#!/usr/bin/env python3
"""
Fetch ACLED conflict data and store it in the database.

Requires ACLED_EMAIL and ACLED_PASSWORD in your .env file.
Register free at: https://acleddata.com/user/register

Usage:
    python scripts/fetch_acled.py

Covers the last 90 days globally. Stores 12 indicators:
  - Total events and fatalities
  - Per event-type counts (battles, explosions, violence vs civilians,
    protests, riots, strategic developments)
  - Regional breakdowns (Middle East, Europe, South Asia, Eastern Africa)
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reckon.config import settings
from reckon.db import AsyncSessionLocal, Base, engine
from reckon.ingestion.acled import (
    WINDOW_DAYS,
    AcledIngester,
    EVENT_TYPES,
    KEY_REGIONS,
    REGION_LABELS,
    _date_range,
)
from reckon.models import *  # noqa: F401,F403


async def main() -> None:
    if not (settings.acled_email and settings.acled_password):
        print("Warning: ACLED_EMAIL / ACLED_PASSWORD not set — storing stub data.")
        print("Register free at https://acleddata.com/user/register\n")
    else:
        print(f"ACLED credentials: configured ({settings.acled_email})")
        print()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    start, end = _date_range()
    print(f"Fetching ACLED conflict data ({start} → {end}, last {WINDOW_DAYS} days)...\n")

    ingester = AcledIngester()
    async with AsyncSessionLocal() as db:
        result = await ingester.ingest(db)
    await ingester.close()

    # Pull stored indicators back out to display values
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select, text
        rows = (
            await db.execute(
                text(
                    "SELECT name, raw_value FROM indicators "
                    "WHERE source = 'acled' ORDER BY name"
                )
            )
        ).fetchall()

    stored = {r.name: int(r.raw_value) for r in rows}

    print("Global summary")
    print("-" * 44)
    print(f"  {'Total events (90d)':<30} {stored.get('acled_total_events', '—'):>8,}")
    print(f"  {'Total fatalities (sample)':<30} {stored.get('acled_total_fatalities', '—'):>8,}")
    print()

    print("By event type")
    print("-" * 44)
    for et, name in EVENT_TYPES.items():
        val = stored.get(name, "—")
        val_str = f"{val:,}" if isinstance(val, int) else str(val)
        print(f"  {et:<35} {val_str:>6}")
    print()

    print("By region (key conflict zones)")
    print("-" * 44)
    for code, name in KEY_REGIONS.items():
        label = REGION_LABELS[code]
        val = stored.get(name, "—")
        val_str = f"{val:,}" if isinstance(val, int) else str(val)
        print(f"  {label:<35} {val_str:>6}")
    print()

    print(f"Ingestion result: {result.inserted} upserted  |  {result.skipped} skipped")
    if result.errors:
        print(f"Errors ({len(result.errors)}):")
        for err in result.errors:
            print(f"  - {err}")


if __name__ == "__main__":
    asyncio.run(main())

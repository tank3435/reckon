"""
Military/Conflict tier ingester.

Sources:
  - ACLED (Armed Conflict Location & Event Data) — requires API key
  - SIPRI arms trade data (scraped/manual for now)
  - Stub fallback when no key is available

ACLED API docs: https://developer.acleddata.com/
"""

from datetime import datetime, timedelta

from reckon.config import settings
from reckon.ingestion.base import BaseIngester, RawIndicator
from reckon.models.indicator import Tier

ACLED_BASE = "https://api.acleddata.com/acled/read"


class MilitaryIngester(BaseIngester):
    tier = Tier.MILITARY

    async def fetch(self) -> list[RawIndicator]:
        # ACLED requires registration; fall back to stubs when key absent
        return self._stub_data()

    def _stub_data(self) -> list[RawIndicator]:
        now = datetime.utcnow()
        return [
            RawIndicator(Tier.MILITARY, "active_conflict_zones", "stub", "stub:conflict_zones", 14.0, "count", now),
            RawIndicator(Tier.MILITARY, "battle_deaths_30d", "stub", "stub:battle_deaths", 2300.0, "count", now),
            RawIndicator(Tier.MILITARY, "nuclear_launch_readiness", "stub", "stub:nuclear", 2.0, "defcon_approx", now),
            RawIndicator(Tier.MILITARY, "arms_transfer_volume", "stub", "stub:arms", 8.4, "index", now),
        ]

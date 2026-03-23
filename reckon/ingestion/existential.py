"""
Existential tier ingester.

Sources:
  - WHO disease outbreak alerts (RSS → parsed)
  - Copernicus Climate Change Service for CO2 / temperature anomaly
  - Bulletin of the Atomic Scientists Doomsday Clock position (manual/scraped)

This tier carries the highest default weight (0.30) in the composite score.
"""

from datetime import datetime

from reckon.ingestion.base import BaseIngester, RawIndicator
from reckon.models.indicator import Tier

WHO_OUTBREAK_RSS = "https://www.who.int/rss-feeds/news-releases.xml"


class ExistentialIngester(BaseIngester):
    tier = Tier.EXISTENTIAL

    async def fetch(self) -> list[RawIndicator]:
        # Live parsing of WHO / Copernicus left as integration TODO
        return self._stub_data()

    def _stub_data(self) -> list[RawIndicator]:
        now = datetime.utcnow()
        return [
            # Doomsday Clock: 90 seconds to midnight as of 2024 → encode as seconds
            RawIndicator(Tier.EXISTENTIAL, "doomsday_clock_seconds", "stub", "stub:doomsday", 90.0, "seconds", now),
            # Global average temperature anomaly (°C above pre-industrial)
            RawIndicator(Tier.EXISTENTIAL, "global_temp_anomaly", "stub", "stub:temp_anomaly", 1.45, "celsius", now),
            # Active WHO outbreak alerts count
            RawIndicator(Tier.EXISTENTIAL, "who_outbreak_alerts", "stub", "stub:who_alerts", 3.0, "count", now),
            # CO2 ppm (Mauna Loa)
            RawIndicator(Tier.EXISTENTIAL, "co2_ppm", "stub", "stub:co2", 424.0, "ppm", now),
        ]

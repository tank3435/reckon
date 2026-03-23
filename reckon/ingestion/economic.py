"""
Economic tier ingester.

Uses FRED's keyless CSV endpoint — no API key required.
CSV URL pattern: https://fred.stlouisfed.org/graph/fredgraph.csv?id=SERIES_ID

Series collected:
  - T10Y2Y   : 10Y-2Y Treasury yield spread (recession indicator), percent
  - UNRATE   : Unemployment rate, %
  - CPIAUCSL : Consumer Price Index (all urban consumers), index
  - GDPC1    : Real GDP (quarterly, chained 2017 dollars), billions USD
"""

import csv
import io
from datetime import datetime

from reckon.ingestion.base import BaseIngester, RawIndicator
from reckon.models.indicator import Tier

FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"

# series_id → (indicator_name, unit)
FRED_SERIES: dict[str, tuple[str, str]] = {
    "T10Y2Y":   ("yield_curve_spread", "percent"),
    "UNRATE":   ("unemployment_rate", "%"),
    "CPIAUCSL": ("cpi_inflation", "index"),
    "GDPC1":    ("real_gdp", "billions_usd"),
}


class EconomicIngester(BaseIngester):
    tier = Tier.ECONOMIC

    async def fetch(self) -> list[RawIndicator]:
        indicators: list[RawIndicator] = []
        for series_id, (name, unit) in FRED_SERIES.items():
            try:
                indicator = await self._fetch_series(series_id, name, unit)
                if indicator:
                    indicators.append(indicator)
            except Exception:
                pass  # individual series failures are non-fatal
        return indicators

    async def _fetch_series(
        self, series_id: str, name: str, unit: str
    ) -> RawIndicator | None:
        resp = await self._client.get(FRED_CSV_URL, params={"id": series_id})
        resp.raise_for_status()

        # Parse CSV — last non-missing row is the latest observation
        reader = csv.reader(io.StringIO(resp.text))
        next(reader)  # skip header: DATE,VALUE
        latest_date: str | None = None
        latest_value: float | None = None
        for date_str, value_str in reader:
            if value_str and value_str != ".":
                latest_date = date_str
                latest_value = float(value_str)

        if latest_date is None or latest_value is None:
            return None

        return RawIndicator(
            tier=Tier.ECONOMIC,
            name=name,
            source="FRED",
            source_id=f"FRED:{series_id}:{latest_date}",
            raw_value=latest_value,
            unit=unit,
            collected_at=datetime.fromisoformat(latest_date),
        )

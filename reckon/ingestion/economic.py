"""
Economic tier ingester.

Pulls from FRED (Federal Reserve Economic Data) for US indicators.
Add more sources by extending fetch().

FRED series used:
  - UNRATE    : Unemployment rate
  - CPIAUCSL  : CPI (inflation proxy)
  - T10Y2Y    : 10Y-2Y Treasury spread (recession indicator)
  - VIXCLS    : CBOE Volatility Index
"""

from datetime import datetime

from reckon.config import settings
from reckon.ingestion.base import BaseIngester, RawIndicator
from reckon.models.indicator import Tier

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

FRED_SERIES = {
    "UNRATE": ("unemployment_rate", "%"),
    "CPIAUCSL": ("cpi_inflation", "index"),
    "T10Y2Y": ("yield_curve_spread", "percent"),
    "VIXCLS": ("vix_volatility", "index"),
}


class EconomicIngester(BaseIngester):
    tier = Tier.ECONOMIC

    async def fetch(self) -> list[RawIndicator]:
        if not settings.fred_api_key:
            return self._stub_data()

        indicators: list[RawIndicator] = []
        for series_id, (name, unit) in FRED_SERIES.items():
            try:
                resp = await self._client.get(
                    FRED_BASE,
                    params={
                        "series_id": series_id,
                        "api_key": settings.fred_api_key,
                        "file_type": "json",
                        "sort_order": "desc",
                        "limit": 1,
                    },
                )
                resp.raise_for_status()
                obs = resp.json()["observations"]
                if obs and obs[0]["value"] != ".":
                    indicators.append(
                        RawIndicator(
                            tier=Tier.ECONOMIC,
                            name=name,
                            source="FRED",
                            source_id=f"FRED:{series_id}:{obs[0]['date']}",
                            raw_value=float(obs[0]["value"]),
                            unit=unit,
                            collected_at=datetime.fromisoformat(obs[0]["date"]),
                        )
                    )
            except Exception:
                pass  # individual series failures are non-fatal

        return indicators

    def _stub_data(self) -> list[RawIndicator]:
        """Return plausible stub values when no API key is configured."""
        now = datetime.utcnow()
        return [
            RawIndicator(Tier.ECONOMIC, "unemployment_rate", "stub", "stub:UNRATE", 4.1, "%", now),
            RawIndicator(Tier.ECONOMIC, "cpi_inflation", "stub", "stub:CPIAUCSL", 314.0, "index", now),
            RawIndicator(Tier.ECONOMIC, "yield_curve_spread", "stub", "stub:T10Y2Y", -0.5, "percent", now),
            RawIndicator(Tier.ECONOMIC, "vix_volatility", "stub", "stub:VIXCLS", 18.5, "index", now),
        ]

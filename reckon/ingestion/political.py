"""
Political/Social tier ingester.

Sources:
  - GDELT GKG summary: conflict event counts, tone indicators
  - Placeholder hooks for V-Dem, Freedom House, ACLED

Real GDELT integration uses their BigQuery export or the GKG REST endpoint.
"""

from datetime import datetime, timedelta

from reckon.ingestion.base import BaseIngester, RawIndicator
from reckon.models.indicator import Tier

GDELT_GKG_URL = "https://api.gdeltproject.org/api/v2/summary/summary"


class PoliticalIngester(BaseIngester):
    tier = Tier.POLITICAL

    async def fetch(self) -> list[RawIndicator]:
        try:
            return await self._fetch_gdelt()
        except Exception:
            return self._stub_data()

    async def _fetch_gdelt(self) -> list[RawIndicator]:
        resp = await self._client.get(
            GDELT_GKG_URL,
            params={"d": "summary", "t": "summary", "fmt": "json"},
        )
        resp.raise_for_status()
        data = resp.json()
        now = datetime.utcnow()
        results: list[RawIndicator] = []

        # GDELT returns a "tone" field ranging roughly -10 (negative) to +10 (positive)
        if "tone" in data:
            results.append(
                RawIndicator(
                    tier=Tier.POLITICAL,
                    name="global_media_tone",
                    source="GDELT",
                    source_id=f"GDELT:tone:{now.date()}",
                    raw_value=float(data["tone"]),
                    unit="tone_score",
                    collected_at=now,
                )
            )
        if "conflict" in data:
            results.append(
                RawIndicator(
                    tier=Tier.POLITICAL,
                    name="global_conflict_events",
                    source="GDELT",
                    source_id=f"GDELT:conflict:{now.date()}",
                    raw_value=float(data["conflict"]),
                    unit="count",
                    collected_at=now,
                )
            )
        return results

    def _stub_data(self) -> list[RawIndicator]:
        now = datetime.utcnow()
        return [
            RawIndicator(Tier.POLITICAL, "global_media_tone", "stub", "stub:tone", -2.1, "tone_score", now),
            RawIndicator(Tier.POLITICAL, "global_conflict_events", "stub", "stub:conflict", 1340.0, "count", now),
            RawIndicator(Tier.POLITICAL, "protest_intensity_index", "stub", "stub:protest", 42.0, "index", now),
        ]

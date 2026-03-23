"""
Polymarket ingester.

Uses Polymarket's public Gamma API — no API key required.
  https://gamma-api.polymarket.com/public-search?q=<term>

For each configured topic, fetches the most liquid active Yes/No market,
extracts the Yes-outcome probability, and stores it as raw_value on a
0–100 scale (e.g. 7.3 means the market implies a 7.3% probability).

One indicator row is maintained per concept via upsert on source_id, so
the row always reflects the current top market for that topic.

Tier assignment per topic:
  - nuclear war, doomsday     → existential
  - recession, depression     → economic
  - world war, major conflict → military
"""

from datetime import datetime, timezone

from reckon.ingestion.base import BaseIngester, RawIndicator
from reckon.models.indicator import Tier

GAMMA_SEARCH = "https://gamma-api.polymarket.com/public-search"

MIN_LIQUIDITY = 500.0  # ignore thin markets below this USD threshold

# (search_term, tier, concept_name)
# concept_name becomes the indicator `name` and is the stable key for baselines.
TOPICS: list[tuple[str, str, str]] = [
    ("nuclear war",         Tier.EXISTENTIAL, "pm_nuclear_war_probability"),
    ("nuclear weapon used", Tier.EXISTENTIAL, "pm_nuclear_weapon_used_probability"),
    ("US recession",        Tier.ECONOMIC,    "pm_us_recession_probability"),
    ("world war",           Tier.MILITARY,    "pm_world_war_probability"),
    ("Russia Ukraine war",  Tier.MILITARY,    "pm_ukraine_war_probability"),
    ("China Taiwan war",    Tier.MILITARY,    "pm_china_taiwan_probability"),
    ("major conflict",      Tier.MILITARY,    "pm_major_conflict_probability"),
]


class PolymarketIngester(BaseIngester):
    # This ingester spans multiple tiers; the tier field here is a placeholder —
    # each RawIndicator carries its own tier assignment.
    tier = Tier.EXISTENTIAL

    async def fetch(self) -> list[RawIndicator]:
        indicators: list[RawIndicator] = []
        seen_condition_ids: set[str] = set()

        for search_term, tier, concept_name in TOPICS:
            try:
                indicator = await self._fetch_top_market(
                    search_term, tier, concept_name, seen_condition_ids
                )
                if indicator:
                    indicators.append(indicator)
            except Exception:
                pass  # non-fatal per topic

        return indicators

    async def _fetch_top_market(
        self,
        query: str,
        tier: str,
        concept_name: str,
        seen: set[str],
    ) -> RawIndicator | None:
        resp = await self._client.get(
            GAMMA_SEARCH,
            params={"q": query, "limit_per_type": 20},
        )
        resp.raise_for_status()
        data = resp.json()

        # public-search returns {markets: [...], events: [...], profiles: [...]}
        raw_markets: list[dict] = data.get("markets", [])

        candidates = _filter_markets(raw_markets, seen)
        if not candidates:
            return None

        # Pick highest-liquidity candidate
        best = max(candidates, key=lambda m: float(m.get("liquidity") or 0))
        condition_id: str = best.get("conditionId", best.get("id", ""))
        seen.add(condition_id)

        yes_price = _yes_price(best)
        if yes_price is None:
            return None

        return RawIndicator(
            tier=tier,
            name=concept_name,
            source="polymarket",
            # Stable per concept — upserts to the same row each run
            source_id=f"polymarket:{concept_name}",
            raw_value=round(yes_price * 100, 4),  # store as 0–100 percentage points
            unit="probability_%",
            collected_at=datetime.now(timezone.utc),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _filter_markets(markets: list[dict], seen: set[str]) -> list[dict]:
    """Keep only active, open, binary (Yes/No) markets above the liquidity floor."""
    out: list[dict] = []
    for m in markets:
        if m.get("closed") or not m.get("active", True):
            continue
        outcomes: list[str] = m.get("outcomes", [])
        prices: list[str] = m.get("outcomePrices", [])
        if len(outcomes) != 2 or len(prices) != 2:
            continue
        if not _is_yes_no(outcomes):
            continue
        liquidity = float(m.get("liquidity") or 0)
        if liquidity < MIN_LIQUIDITY:
            continue
        condition_id = m.get("conditionId", m.get("id", ""))
        if condition_id in seen:
            continue
        out.append(m)
    return out


def _is_yes_no(outcomes: list[str]) -> bool:
    normalized = {o.strip().lower() for o in outcomes}
    return normalized == {"yes", "no"}


def _yes_price(market: dict) -> float | None:
    """Return the Yes-outcome price (0.0–1.0), or None if unparseable."""
    outcomes: list[str] = market.get("outcomes", [])
    prices: list[str] = market.get("outcomePrices", [])
    try:
        yes_idx = next(i for i, o in enumerate(outcomes) if o.strip().lower() == "yes")
        return float(prices[yes_idx])
    except (StopIteration, IndexError, ValueError):
        return None

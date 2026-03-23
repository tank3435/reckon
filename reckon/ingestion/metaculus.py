"""
Metaculus ingester.

Requires a free API token from https://metaculus.com/aib
Set METACULUS_API_TOKEN in your .env file.

Authentication header: Authorization: Token <token>
Base URL: https://www.metaculus.com/api2/questions/

For each configured topic this ingester:
  1. Searches for active binary forecasting questions matching the topic.
  2. Picks the question with the most forecasters (highest signal quality).
  3. Stores TWO indicator rows per topic:
       - <concept>_probability : community median prediction scaled 0–100
       - <concept>_forecasters : raw forecaster count (measures question credibility)

Community prediction is extracted from:
  - aggregations.recency_weighted.latest  (current API)
  - community_prediction (older API / fallback)

Both probability rows and forecaster rows use stable source_id keys so each
run upserts to the same DB row rather than accumulating duplicates.

Note: Metaculus required auth for all API access as of late 2024. Without a
token the ingester returns stub data so the rest of the pipeline stays functional.
"""

from datetime import datetime, timezone

from reckon.config import settings
from reckon.ingestion.base import BaseIngester, RawIndicator
from reckon.models.indicator import Tier

METACULUS_API = "https://www.metaculus.com/api2/questions/"
MIN_FORECASTERS = 5  # ignore questions with fewer than this many forecasters

# (search_term, tier, concept_name)
TOPICS: list[tuple[str, str, str]] = [
    ("nuclear war",             Tier.EXISTENTIAL, "mc_nuclear_war"),
    ("US recession",            Tier.ECONOMIC,    "mc_us_recession"),
    ("major armed conflict",    Tier.MILITARY,    "mc_major_armed_conflict"),
    ("civilizational collapse", Tier.EXISTENTIAL, "mc_civilizational_collapse"),
    ("existential risk",        Tier.EXISTENTIAL, "mc_existential_risk"),
]


class MetaculusIngester(BaseIngester):
    tier = Tier.EXISTENTIAL  # placeholder — each RawIndicator carries its own tier

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Token {settings.metaculus_api_token}"}

    async def fetch(self) -> list[RawIndicator]:
        if not settings.metaculus_api_token:
            return _stub_data()

        indicators: list[RawIndicator] = []
        for search_term, tier, concept in TOPICS:
            try:
                new = await self._fetch_topic(search_term, tier, concept)
                indicators.extend(new)
            except Exception:
                pass  # non-fatal per topic
        return indicators

    async def _fetch_topic(
        self, search_term: str, tier: str, concept: str
    ) -> list[RawIndicator]:
        resp = await self._client.get(
            METACULUS_API,
            headers=self._auth_headers(),
            params={
                "search": search_term,
                "status": "active",
                "type": "forecast",
                "limit": 20,
                "order_by": "-nr_forecasters",
            },
        )
        resp.raise_for_status()
        questions: list[dict] = resp.json().get("results", [])

        candidates = [
            q for q in questions
            if _is_binary(q) and _forecaster_count(q) >= MIN_FORECASTERS
        ]
        if not candidates:
            return []

        # Best = most forecasters among binary candidates
        best = max(candidates, key=_forecaster_count)
        prob = _community_probability(best)
        if prob is None:
            return []

        count = _forecaster_count(best)
        title = best.get("title", "")
        now = datetime.now(timezone.utc)

        return [
            RawIndicator(
                tier=tier,
                name=f"{concept}_probability",
                source="metaculus",
                source_id=f"metaculus:{concept}:probability",
                raw_value=round(prob * 100, 4),  # 0–100 percentage points
                unit="probability_%",
                collected_at=now,
            ),
            RawIndicator(
                tier=tier,
                name=f"{concept}_forecasters",
                source="metaculus",
                source_id=f"metaculus:{concept}:forecasters",
                raw_value=float(count),
                unit="forecasters",
                collected_at=now,
            ),
        ]


# ---------------------------------------------------------------------------
# Parsing helpers — handle both current and legacy Metaculus API shapes
# ---------------------------------------------------------------------------

def _is_binary(q: dict) -> bool:
    return q.get("question_type") == "binary"


def _forecaster_count(q: dict) -> int:
    # Current API: nr_forecasters; older API: number_of_forecasters
    return int(q.get("nr_forecasters") or q.get("number_of_forecasters") or 0)


def _community_probability(q: dict) -> float | None:
    """
    Extract the community median probability (0.0–1.0) from a question dict.

    Tries in order:
      1. aggregations.recency_weighted.latest  (current API)
      2. community_prediction as a direct float (older API)
      3. community_prediction.full.q2 (older nested format)
    """
    # -- Current API: aggregations object --
    aggs = q.get("aggregations") or {}
    for agg_key in ("recency_weighted", "unweighted", "single_aggregation"):
        agg = aggs.get(agg_key) or {}
        latest = agg.get("latest")
        if latest is None:
            continue
        prob = _extract_from_latest(latest)
        if prob is not None:
            return _clamp01(prob)

    # -- Older API: community_prediction --
    cp = q.get("community_prediction")
    if cp is None:
        return None
    if isinstance(cp, (int, float)):
        return _clamp01(float(cp))
    if isinstance(cp, dict):
        # Nested format: {full: {q2: 0.07}} or {q2: 0.07}
        full = cp.get("full") or cp
        for key in ("q2", "median", "mean"):
            val = full.get(key)
            if val is not None:
                return _clamp01(float(val))

    return None


def _extract_from_latest(latest: dict | float | None) -> float | None:
    """Parse community prediction out of the aggregations.*.latest object."""
    if latest is None:
        return None
    if isinstance(latest, (int, float)):
        return float(latest)
    if not isinstance(latest, dict):
        return None
    # Binary questions store probability in 'centers' (single-element list) or 'means'
    for key in ("value", "q2", "median"):
        val = latest.get(key)
        if val is not None:
            return float(val)
    for key in ("centers", "means"):
        arr = latest.get(key)
        if arr and isinstance(arr, list):
            return float(arr[0])
    return None


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


# ---------------------------------------------------------------------------
# Stub data — used when METACULUS_API_TOKEN is not configured
# ---------------------------------------------------------------------------

def _stub_data() -> list[RawIndicator]:
    now = datetime.now(timezone.utc)
    rows: list[RawIndicator] = []
    stubs = [
        (Tier.EXISTENTIAL, "mc_nuclear_war",             1.8,  312),
        (Tier.ECONOMIC,    "mc_us_recession",            35.0, 890),
        (Tier.MILITARY,    "mc_major_armed_conflict",    22.0, 540),
        (Tier.EXISTENTIAL, "mc_civilizational_collapse", 3.5,  210),
        (Tier.EXISTENTIAL, "mc_existential_risk",        5.0,  450),
    ]
    for tier, concept, prob, count in stubs:
        rows.append(RawIndicator(tier, f"{concept}_probability", "metaculus",
                                 f"metaculus:{concept}:probability", prob, "probability_%", now))
        rows.append(RawIndicator(tier, f"{concept}_forecasters", "metaculus",
                                 f"metaculus:{concept}:forecasters", float(count), "forecasters", now))
    return rows

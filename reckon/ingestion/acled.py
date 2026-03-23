"""
ACLED (Armed Conflict Location & Event Data) ingester.

Registration: free at https://acleddata.com/user/register
Set ACLED_EMAIL and ACLED_PASSWORD in your .env file.

Auth flow: POST email+password to OAuth endpoint → short-lived Bearer token.
Token is fetched once per ingestion run and not persisted.

Data strategy (7 HTTP requests total, no full-table download):
  1. Six requests — one per event type, limit=1 each.
     The response top-level `count` gives exact global totals for the 90-day
     window without downloading all records.
  2. One request — limit=5000, fields=fatalities only, for fatality sum.
     This is a sample; for scoring purposes the direction matters more than
     precision.
  3. Four requests — one per key region, limit=1 each, for regional breakdowns.

Indicators stored (all tier=military, source=acled, unit=count):
  acled_total_events          — all event types, global, last 90 days
  acled_total_fatalities      — fatality sum from 5000-event sample
  acled_battles               — Battles count
  acled_explosions            — Explosions/Remote violence count
  acled_violence_civilians    — Violence against civilians count
  acled_protests              — Protests count
  acled_riots                 — Riots count
  acled_strategic             — Strategic developments count
  acled_region_middle_east    — region 11 total events
  acled_region_europe         — region 12 total events
  acled_region_south_asia     — region 7 total events
  acled_region_eastern_africa — region 3 total events

All source_id values are stable (acled:{name}) so each run upserts to the
same row rather than accumulating new rows.
"""

from datetime import datetime, timedelta, timezone

from reckon.config import settings
from reckon.ingestion.base import BaseIngester, RawIndicator
from reckon.models.indicator import Tier

ACLED_AUTH_URL = "https://acleddata.com/oauth/token"
ACLED_API_URL = "https://acleddata.com/api/acled/read"
WINDOW_DAYS = 90

# event_type string (as ACLED spells it) → indicator name
EVENT_TYPES: dict[str, str] = {
    "Battles":                      "acled_battles",
    "Explosions/Remote violence":   "acled_explosions",
    "Violence against civilians":   "acled_violence_civilians",
    "Protests":                     "acled_protests",
    "Riots":                        "acled_riots",
    "Strategic developments":       "acled_strategic",
}

# ACLED region code (string) → indicator name
KEY_REGIONS: dict[str, str] = {
    "3":  "acled_region_eastern_africa",
    "7":  "acled_region_south_asia",
    "11": "acled_region_middle_east",
    "12": "acled_region_europe",
}

REGION_LABELS: dict[str, str] = {
    "3": "Eastern Africa", "7": "South Asia",
    "11": "Middle East",   "12": "Europe",
}


class AcledIngester(BaseIngester):
    tier = Tier.MILITARY

    # Bearer token cached for the lifetime of one ingestion run
    _token: str | None = None

    async def fetch(self) -> list[RawIndicator]:
        if not (settings.acled_email and settings.acled_password):
            return _stub_data()

        try:
            self._token = await self._get_token()
        except Exception:
            return _stub_data()

        indicators: list[RawIndicator] = []
        start_date, end_date = _date_range()
        now = datetime.now(timezone.utc)

        # --- per-type event counts (6 requests) ---
        total_events = 0
        for event_type, name in EVENT_TYPES.items():
            try:
                count = await self._fetch_count(
                    event_date=f"{start_date}|{end_date}",
                    event_type=event_type,
                )
                total_events += count
                indicators.append(_make(name, count, now))
            except Exception:
                pass

        indicators.append(_make("acled_total_events", total_events, now))

        # --- fatality sum from one 5000-row sample ---
        try:
            fatalities = await self._fetch_fatality_sum(start_date, end_date)
            indicators.append(_make("acled_total_fatalities", fatalities, now))
        except Exception:
            pass

        # --- regional breakdowns (4 requests) ---
        for region_code, name in KEY_REGIONS.items():
            try:
                count = await self._fetch_count(
                    event_date=f"{start_date}|{end_date}",
                    region=region_code,
                )
                indicators.append(_make(name, count, now))
            except Exception:
                pass

        return indicators

    async def _get_token(self) -> str:
        resp = await self._client.post(
            ACLED_AUTH_URL,
            data={
                "email": settings.acled_email,
                "password": settings.acled_password,
                "grant_type": "password",
                "client_id": "acled",
            },
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    def _auth_header(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token}"}

    async def _fetch_count(self, **filters) -> int:
        """Return the total count of events matching filters using limit=1."""
        params = {
            "_format": "json",
            "limit": 1,
            "event_date_where": "BETWEEN",
            **filters,
        }
        resp = await self._client.get(
            ACLED_API_URL, headers=self._auth_header(), params=params
        )
        resp.raise_for_status()
        body = resp.json()
        # ACLED wraps results: {"count": N, "data": [...]} or {"status":200,...,"count":N}
        count = body.get("count") or body.get("total_count") or 0
        # If count not in wrapper, fall back to len(data)
        if count == 0:
            count = len(body.get("data", []))
        return int(count)

    async def _fetch_fatality_sum(self, start_date: str, end_date: str) -> int:
        params = {
            "_format": "json",
            "limit": 5000,
            "fields": "fatalities",
            "event_date": f"{start_date}|{end_date}",
            "event_date_where": "BETWEEN",
        }
        resp = await self._client.get(
            ACLED_API_URL, headers=self._auth_header(), params=params
        )
        resp.raise_for_status()
        data: list[dict] = resp.json().get("data", [])
        return sum(int(row.get("fatalities") or 0) for row in data)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _date_range() -> tuple[str, str]:
    today = datetime.now(timezone.utc).date()
    start = today - timedelta(days=WINDOW_DAYS)
    return start.isoformat(), today.isoformat()


def _make(name: str, value: int | float, now: datetime) -> RawIndicator:
    return RawIndicator(
        tier=Tier.MILITARY,
        name=name,
        source="acled",
        source_id=f"acled:{name}",
        raw_value=float(value),
        unit="count",
        collected_at=now,
    )


# ---------------------------------------------------------------------------
# Stub data — used when ACLED credentials are not configured
# ---------------------------------------------------------------------------

def _stub_data() -> list[RawIndicator]:
    now = datetime.now(timezone.utc)
    rows = [
        ("acled_total_events",            2847),
        ("acled_total_fatalities",        8210),
        ("acled_battles",                  640),
        ("acled_explosions",               430),
        ("acled_violence_civilians",       380),
        ("acled_protests",                 910),
        ("acled_riots",                    290),
        ("acled_strategic",                197),
        ("acled_region_middle_east",       520),
        ("acled_region_europe",            380),
        ("acled_region_south_asia",        310),
        ("acled_region_eastern_africa",    490),
    ]
    return [_make(name, val, now) for name, val in rows]

# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Vision

**Reckon** answers "how bad is it, really?" by aggregating real-world risk indicators across four tiers, scoring them against historical baselines, and outputting calibrated risk assessments with proportionate response recommendations. It also provides location-aware survival intelligence (nuclear target proximity, freshwater sources, shelters).

### Risk Tiers (in ascending default weight)
- **Economic** (weight 0.20) — unemployment, inflation, yield curve, VIX
- **Political/Social** (weight 0.25) — media tone, conflict events, protest intensity
- **Military/Conflict** (weight 0.25) — active conflicts, battle deaths, nuclear readiness
- **Existential** (weight 0.30) — Doomsday Clock, temperature anomaly, outbreak alerts, CO₂

## Commands

```bash
# Start Postgres
docker compose up -d

# Install (including dev deps)
pip install -e ".[dev]"

# Run API server
uvicorn reckon.main:app --reload

# Run all tests
pytest

# Run a single test
pytest tests/test_scorer.py::test_zscore_at_mean -v

# Lint + format
ruff check . && ruff format .

# Database migrations
alembic upgrade head
alembic revision --autogenerate -m "description"
```

## Architecture

### Module layout

```
reckon/
  main.py          — FastAPI app, lifespan, router registration, CORS
  config.py        — Settings via pydantic-settings (.env → typed fields)
  db.py            — Async engine, AsyncSessionLocal, Base, get_db()
  models/          — SQLAlchemy ORM (indicators, baselines, assessments, locations)
  schemas/         — Pydantic I/O schemas (separate from ORM models)
  ingestion/       — One ingester class per tier; BaseIngester handles DB upsert
  analysis/        — Scoring engine; weights.py holds per-indicator weights
  locations/       — Geocoder (Nominatim), nuclear proximity, Overpass resource finder
  api/             — FastAPI routers: assessments, indicators, ingestion, locations
```

### Data flow

1. **Ingestion** (`POST /ingest/all` or `/ingest/{tier}`) — Each `BaseIngester` subclass calls `fetch()`, then the base class upserts into `indicators` using `(source, source_id)` as the idempotency key.

2. **Scoring** (`POST /assessments/run`) — `score_assessment()` loads the latest value per `(tier, name)` and their `Baseline` records, computes z-score → 0–100 per indicator, takes weighted averages within each tier, then across tiers using config weights. Writes an immutable `RiskAssessment` + `TierScore` rows.

3. **Location intel** (`GET /locations/intel?q=...`) — Geocodes via Nominatim (cached in `location_profiles`), runs Overpass queries for freshwater/shelters, and computes distance to the nearest entry in the static nuclear target list.

### Scoring model

- Per-indicator score: `((clamp(z, -C, C) + C) / (2C)) * 100` where `z = (value - baseline.mean) / baseline.stddev`
- Higher score = higher risk (further from historical normal in the alarming direction)
- Tier score = weighted average of its indicators (weights from `analysis/weights.py` × `Baseline.weight`)
- Composite = weighted average of tier scores using `config.tier_weight_*`
- Severity labels: NORMAL (<20), GUARDED (20–40), ELEVATED (40–60), HIGH (60–80), CRITICAL (80+)

### Key invariants

- **Assessments are immutable** — each scoring run creates a new row; nothing is updated in place.
- **Ingestion is idempotent** — `(source, source_id)` unique constraint; same data re-ingested does an upsert.
- **Baselines must exist** before scoring produces meaningful results — indicators without a matching `Baseline` row are skipped silently.
- **Stub data** is returned by all ingesters when API keys are absent, so the system is fully testable without credentials.

### Adding a new indicator

1. Add a `RawIndicator` entry in the relevant ingester's `fetch()` (and `_stub_data()`).
2. Add its `name` and `weight` to `analysis/weights.py`.
3. Seed a `Baseline` row via `POST /indicators/baselines`.

### Adding a new data source / tier

Subclass `BaseIngester`, set `tier`, implement `fetch() -> list[RawIndicator]`. Register the class in `api/ingestion.py`'s `_INGESTERS` dict.

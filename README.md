# Reckon

**How bad is it, really?**

Reckon is an empirical grounding tool that cuts through catastrophizing and complacency alike. It aggregates real-world risk indicators across four tiers, scores them against historical baselines, and returns a calibrated composite risk assessment with proportionate response recommendations.

It also tells you how close you are to a nuclear target.

---

## What it does

**Risk Assessment** — Reckon pulls live data across four tiers and scores each indicator against its historical baseline using a normalized deviation model. The result is a single composite score (0–100) with a severity label and response recommendations.

| Tier | What it tracks |
|------|---------------|
| Economic | Unemployment, inflation, yield curve, market volatility |
| Political/Social | Global media tone, conflict events, protest intensity |
| Military/Conflict | Active conflict zones, battle deaths, nuclear readiness |
| Existential | Doomsday Clock, temperature anomaly, outbreak alerts, CO₂ |

**Location Intelligence** — Enter a city or zip code and get:
- Distance to the nearest nuclear target
- Nearby freshwater sources (rivers, springs, lakes)
- Emergency shelters and hospitals within 50km
- Evacuation-relevant geographic context

---

## Quickstart

```bash
# 1. Start Postgres
docker compose up -d

# 2. Install dependencies
pip install -e ".[dev]"

# 3. Copy and configure environment
cp .env.example .env

# 4. Run the API
uvicorn reckon.main:app --reload
```

Tables are created automatically on first startup. Visit `http://localhost:8000/docs` for the interactive API.

### First run

```bash
# Ingest indicator data (uses stubs without API keys)
curl -X POST http://localhost:8000/ingest/all

# Seed baselines (required before scoring)
# See scripts/seed_baselines.py (TODO)

# Run a risk assessment
curl -X POST http://localhost:8000/assessments/run

# Get location intel
curl "http://localhost:8000/locations/intel?q=Denver,CO"
```

---

## Configuration

Copy `.env.example` to `.env`. All settings have defaults that work without API keys (using stub data).

To get live data, add API keys for:
- `FRED_API_KEY` — [Federal Reserve Economic Data](https://fred.stlouisfed.org/docs/api/api_key.html)
- `GDELT_API_KEY` — GDELT (free, no key required for basic endpoints)

---

## Tech stack

Python 3.11 · FastAPI · PostgreSQL · SQLAlchemy (async) · Alembic · Geopy · Overpass API

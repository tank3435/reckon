#!/usr/bin/env python3
"""
Standalone script to generate a narrative from the current assessment data.

Usage:
    python scripts/generate_narrative.py

Requires ANTHROPIC_API_KEY in environment (or .env file).
When the API key is absent, prints the stub response instead.
"""

import json
import sys
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from reckon.analysis.narrative import generate_narrative


def _sample_narrative_data() -> dict:
    """
    Build narrative_data by calling the scoring engine against the database,
    or fall back to a representative sample for testing.
    """
    try:
        # Try to pull live data from the scoring engine
        from reckon.db import SessionLocal
        from reckon.analysis.scoring import compute_assessment

        db = SessionLocal()
        try:
            assessment = compute_assessment(db)
            return assessment.get("narrative_data", assessment)
        finally:
            db.close()
    except Exception as exc:
        print(f"[!] Could not load live data ({exc}), using sample narrative_data")
        return {
            "composite_score": 47.3,
            "hard_data_composite": 44.1,
            "tier_scores": {
                "economic": 38.5,
                "political": 52.0,
                "military": 55.8,
                "existential": 41.2,
            },
            "response_level": "YELLOW",
            "data_completeness_pct": 72.0,
            "top_indicators": [
                {
                    "name": "acled_global_fatalities_last_30d",
                    "normalized_value": 68.2,
                    "tier": "military",
                    "source": "acled",
                },
                {
                    "name": "polymarket_nuclear_use",
                    "normalized_value": 61.5,
                    "tier": "existential",
                    "source": "polymarket",
                },
                {
                    "name": "polymarket_us_recession_2026",
                    "normalized_value": 55.0,
                    "tier": "economic",
                    "source": "polymarket",
                },
                {
                    "name": "fred_t10y2y",
                    "normalized_value": 52.3,
                    "tier": "economic",
                    "source": "fred",
                },
                {
                    "name": "acled_protests_last_30d",
                    "normalized_value": 49.7,
                    "tier": "political",
                    "source": "acled",
                },
            ],
            "methodology_note": (
                "Composite is a weighted average of tier scores. News sentiment "
                "is capped at 0.08 weight per indicator. Hard data anchors the "
                "composite; sentiment informs but does not dominate."
            ),
        }


def main():
    narrative_data = _sample_narrative_data()

    print("=" * 60)
    print("INPUT: narrative_data")
    print("=" * 60)
    print(json.dumps(narrative_data, indent=2))
    print()

    result = generate_narrative(narrative_data)

    print("=" * 60)
    print("OUTPUT: narrative")
    print("=" * 60)

    if result is None:
        print("[ERROR] Narrative generation failed — returned None")
        sys.exit(1)

    print(json.dumps(result, indent=2))

    # Quick validation
    headline_words = len(result.get("headline", "").split())
    if headline_words > 15:
        print(f"\n[WARN] Headline is {headline_words} words (max 15)")

    if result.get("_stub"):
        print(f"\n[INFO] Stub returned — reason: {result.get('_stub_reason')}")


if __name__ == "__main__":
    main()

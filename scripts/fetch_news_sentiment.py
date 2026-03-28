#!/usr/bin/env python3
"""Standalone runner: python scripts/fetch_news_sentiment.py"""
import logging, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from reckon.ingestion.news_sentiment import NewsSentimentIngester

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s — %(message)s")

def main():
    indicators = NewsSentimentIngester().fetch()
    print(f"\n{'─'*60}\n  News Sentiment — {len(indicators)} indicators\n{'─'*60}")
    for i in indicators:
        stub = " [STUB]" if i.source.endswith("stub") else ""
        print(f"  {i.name:<42} {i.raw_value:>6.1f}  ({i.tier}){stub}")
    signals = next((i.metadata.get("top_signals") for i in indicators if i.metadata.get("top_signals")), [])
    if signals:
        print("\n  Top signals:")
        for s in signals: print(f"    • {s}")
    reasoning = next((i.metadata.get("reasoning") for i in indicators if i.metadata.get("reasoning")), "")
    if reasoning:
        print(f"\n  Reasoning: {reasoning}")
    print(f"{'─'*60}\n")

if __name__ == "__main__":
    main()

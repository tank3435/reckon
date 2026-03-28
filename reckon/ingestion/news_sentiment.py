"""
News Sentiment Collector
========================
Collects headlines from a globally diverse, credibility-weighted set of RSS
sources and uses the Claude API to produce per-tier risk sentiment scores
(0-100).

Key design decisions (see CLAUDE.md and Architectural Decisions page in Notion):

1. SOURCE DIVERSITY: Sources span regions, not just Western outlets. The list
   is config-driven and designed for expansion — not a hardcoded 10.

2. SOURCE CREDIBILITY WEIGHTING: Sources are weighted by fact-based track
   record. Wire services (Reuters, AP) score highest because their structural
   incentives are against sensationalism. Credibility rationale is documented
   per-source in SOURCE_REGISTRY. All weights are revisitable.

3. UPWARD BIAS COMPENSATION: News by definition covers abnormal events. Raw
   sentiment scores will trend elevated regardless of source selection. The
   scoring engine accounts for this by giving news sentiment lower weight
   vs. hard data. Outputs are flagged as sentiment-class accordingly.

4. BEHAVIORAL DATA LAYER: Not implemented here. Behavioral signals (capital
   flows, positioning data, etc.) are to be collected and logged separately
   as an observatory layer — NOT scored in v0.1. See scoring.py.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import feedparser

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Source Registry
# ---------------------------------------------------------------------------
# Each entry is a dict:
#   url          : RSS feed URL
#   label        : Human-readable name (for logging / audit trail)
#   region       : Geographic focus
#   credibility  : Float [0.0-1.0]. Fact-based track record weight.
#                  1.0 = wire-service level. Rationale documented inline.
#   max_items    : Max headlines to pull per run
#
# TO ADD A SOURCE: append a dict. Credibility rationale must be documented.
# ---------------------------------------------------------------------------

SOURCE_REGISTRY: list[dict] = [
    # ---- Wire Services (highest credibility — structurally anti-sensationalist) ----
    {
        "url": "https://feeds.reuters.com/reuters/worldNews",
        "label": "Reuters World",
        "region": "global",
        "credibility": 1.0,  # Wire service. Clients are other newsrooms who need reliability.
        "max_items": 15,
    },
    {
        "url": "https://feeds.reuters.com/reuters/businessNews",
        "label": "Reuters Business",
        "region": "global",
        "credibility": 1.0,
        "max_items": 10,
    },
    {
        "url": "https://rsshub.app/apnews/topics/apf-topnews",
        "label": "AP Top News",
        "region": "global",
        "credibility": 1.0,  # Wire service. Structural incentive for accuracy.
        "max_items": 15,
    },
    # ---- Established International ----
    {
        "url": "https://news.un.org/feed/subscribe/en/news/all/rss.xml",
        "label": "UN News",
        "region": "global",
        "credibility": 0.90,  # Institutional bias but factually careful.
        "max_items": 10,
    },
    {
        "url": "https://www.economist.com/the-world-this-week/rss.xml",
        "label": "The Economist",
        "region": "global",
        "credibility": 0.85,  # Long track record, strong editorial standards. Some slant.
        "max_items": 8,
    },
    {
        "url": "https://foreignpolicy.com/feed/",
        "label": "Foreign Policy",
        "region": "global",
        "credibility": 0.82,  # Policy-focused, expert sourcing. US-centric framing.
        "max_items": 8,
    },
    {
        "url": "https://www.ft.com/rss/home",
        "label": "Financial Times",
        "region": "europe",
        "credibility": 0.85,
        "max_items": 10,
    },
    {
        "url": "https://feeds.bbci.co.uk/news/world/rss.xml",
        "label": "BBC World",
        "region": "europe",
        "credibility": 0.80,  # UK institutional perspective. Generally measured.
        "max_items": 10,
    },
    # ---- Regional / Non-Western Coverage ----
    {
        "url": "https://www.aljazeera.com/xml/rss/all.xml",
        "label": "Al Jazeera",
        "region": "middle_east",
        "credibility": 0.75,  # Strong MENA coverage. Qatar state funding is a bias factor.
        "max_items": 10,
    },
    {
        "url": "https://www.dw.com/en/rss/rss.xml",
        "label": "Deutsche Welle",
        "region": "europe",
        "credibility": 0.82,  # German state-funded international broadcaster. Generally factual.
        "max_items": 8,
    },
    {
        "url": "https://www.france24.com/en/rss",
        "label": "France 24",
        "region": "europe",
        "credibility": 0.78,  # Strong Africa/Francophone coverage. French state funding factor.
        "max_items": 8,
    },
    {
        "url": "https://rss.rfi.fr/rfi/en/radiofrance/1/rss.xml",
        "label": "RFI (Radio France Internationale)",
        "region": "africa",
        "credibility": 0.78,  # Best consistent Africa coverage from a major outlet.
        "max_items": 8,
    },
    {
        "url": "https://www.channelnewsasia.com/rssfeeds/8395986",
        "label": "Channel NewsAsia",
        "region": "asia",
        "credibility": 0.80,  # Best consistent Southeast Asia coverage. Singapore-based.
        "max_items": 8,
    },
    {
        "url": "https://www3.nhk.or.jp/nhkworld/en/news/rss/rss.xml",
        "label": "NHK World",
        "region": "asia",
        "credibility": 0.82,  # Japan public broadcaster. Strong Asia-Pacific coverage.
        "max_items": 8,
    },
    {
        "url": "https://feeds.feedburner.com/thehindu/news/international",
        "label": "The Hindu (International)",
        "region": "south_asia",
        "credibility": 0.78,  # Strong South Asia coverage, respected editorial standards.
        "max_items": 8,
    },
    {
        "url": "https://allafrica.com/tools/headlines/rdf/latest/headlines.rdf",
        "label": "AllAfrica",
        "region": "africa",
        "credibility": 0.70,  # Aggregates African media. Variable source quality.
        "max_items": 8,
    },
    # ---- Specialist / Domain-Specific ----
    {
        "url": "https://www.armscontrol.org/rss.xml",
        "label": "Arms Control Association",
        "region": "global",
        "credibility": 0.92,  # Subject-matter experts. Non-partisan, deeply sourced.
        "max_items": 8,
    },
    {
        "url": "https://thebulletin.org/feed/",
        "label": "Bulletin of the Atomic Scientists",
        "region": "global",
        "credibility": 0.90,  # Publishes Doomsday Clock. Expert-led. Existential risk focus.
        "max_items": 6,
    },
    {
        "url": "https://www.icij.org/feed/",
        "label": "ICIJ (Investigative Journalism)",
        "region": "global",
        "credibility": 0.88,  # International Consortium of Investigative Journalists. Rigorous.
        "max_items": 6,
    },
    # ---- TODO: Add when RSS available ----
    # Agencia EFE (Spanish wire service — Latin America + Spain)
    # Daily Maverick (South Africa — strong investigative journalism)
    # The Wire India (strong South Asia investigative)
    # Nikkei Asia (Japan financial, strong Asia business coverage)
]

_CLAUDE_MODEL = "claude-opus-4-5-20251001"

_SYSTEM_PROMPT = """\
You are a neutral, empirical risk analyst. You do NOT editorialize, catastrophize,
or speculate beyond what the data shows.

You are reading a weighted set of headlines from globally diverse news sources.
Sources are grouped by credibility tier. Higher-credibility sources (wire services,
specialist outlets) should carry more weight in your assessment.

Score the aggregate signal across four risk tiers. Each score is 0-100:
  0   = no elevated signal / historically normal baseline
  25  = mildly above baseline
  50  = meaningfully elevated above historical norm
  75  = significantly elevated — notable by historical standards
  100 = extreme / historic crisis level

CRITICAL: News inherently over-represents abnormal events. A score of 50 means
the signal is meaningfully above baseline *given* this structural bias — not
just that bad things are being reported. Reserve scores above 65 for genuinely
unusual concentrations of a specific risk type across multiple credible sources.

Tiers:
  economic   — recession signals, financial contagion, supply disruption,
               currency crises, debt/banking stress
  political  — democratic backsliding, civil unrest, institutional breakdown,
               contested elections, alliance fractures, political violence
  military   — armed conflict escalation, troop movements, weapons use,
               ceasefire collapse, naval/air incidents, mobilization signals
  existential — nuclear posture changes, WMD signals, pandemic/bioweapon signals,
               civilizational-scale infrastructure threats

Respond ONLY with a valid JSON object. No commentary, no markdown:
{
  "economic": <0-100>,
  "political": <0-100>,
  "military": <0-100>,
  "existential": <0-100>,
  "headline_count": <int>,
  "top_signals": ["<signal>", ...],
  "reasoning": "<1-2 sentences on dominant signals>"
}

top_signals: at most 5 phrases (10 words max each). For audit trail only.
"""


@dataclass
class WeightedHeadline:
    text: str
    source_label: str
    region: str
    credibility: float


@dataclass
class NewsSentimentIndicator:
    name: str
    raw_value: float
    unit: str
    tier: str
    source: str
    source_id: str
    timestamp: datetime
    metadata: dict = field(default_factory=dict)


class NewsSentimentIngester:

    def __init__(self) -> None:
        self.api_key: Optional[str] = os.getenv("ANTHROPIC_API_KEY")
        self._client = None
        if self.api_key:
            try:
                import anthropic
                self._client = anthropic.Anthropic(api_key=self.api_key)
            except ImportError:
                logger.error("anthropic package not installed. Run: pip install anthropic")

    def fetch(self) -> list[NewsSentimentIndicator]:
        headlines = self._collect_headlines()
        logger.info("Collected %d headlines from %d sources", len(headlines), len(SOURCE_REGISTRY))
        if not headlines:
            return self._stub_data()
        if not self._client:
            logger.warning("ANTHROPIC_API_KEY not set — returning stub data")
            return self._stub_data()
        scores = self._score_with_claude(headlines)
        if scores is None:
            return self._stub_data()
        return self._build_indicators(scores, len(headlines))

    def _collect_headlines(self) -> list[WeightedHeadline]:
        headlines: list[WeightedHeadline] = []
        for source in SOURCE_REGISTRY:
            try:
                feed = feedparser.parse(source["url"])
                for entry in feed.entries[: source["max_items"]]:
                    title = entry.get("title", "").strip()
                    summary = entry.get("summary", "").strip()
                    text = title + (" — " + summary[:120] if summary else "")
                    if text.strip():
                        headlines.append(WeightedHeadline(
                            text=text,
                            source_label=source["label"],
                            region=source["region"],
                            credibility=source["credibility"],
                        ))
            except Exception as exc:
                logger.warning("Failed to fetch '%s': %s", source["label"], exc)
        return headlines

    def _score_with_claude(self, headlines: list[WeightedHeadline]) -> Optional[dict]:
        high = [h for h in headlines if h.credibility >= 0.88]
        mid = [h for h in headlines if 0.75 <= h.credibility < 0.88]
        low = [h for h in headlines if h.credibility < 0.75]

        def fmt(group, label):
            if not group:
                return ""
            lines = "\n".join(f"  [{h.source_label}/{h.region}] {h.text}" for h in group)
            return f"\n{label}:\n{lines}"

        block = (
            fmt(high, "HIGH CREDIBILITY (wire services, specialists)")
            + fmt(mid, "MID CREDIBILITY (established regional)")
            + fmt(low, "LOWER CREDIBILITY (treat with more skepticism)")
        )

        try:
            response = self._client.messages.create(
                model=_CLAUDE_MODEL,
                max_tokens=600,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": (
                    f"Score these {len(headlines)} headlines. "
                    f"Higher-credibility sources carry more weight.\n\nHEADLINES:{block}"
                )}],
            )
            raw = response.content[0].text.strip()
            scores = json.loads(raw)
            logger.info(
                "Sentiment — econ:%s pol:%s mil:%s exist:%s | %s",
                scores.get("economic"), scores.get("political"),
                scores.get("military"), scores.get("existential"),
                scores.get("reasoning", ""),
            )
            return scores
        except json.JSONDecodeError:
            logger.error("Claude returned non-JSON: %s", response.content[0].text[:200])
            return None
        except Exception as exc:
            logger.error("Claude API error: %s", exc)
            return None

    def _build_indicators(self, scores: dict, headline_count: int) -> list[NewsSentimentIndicator]:
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y-%m-%d")
        fp = hashlib.md5(
            f"{date_str}{scores.get('economic')}{scores.get('political')}"
            f"{scores.get('military')}{scores.get('existential')}".encode()
        ).hexdigest()[:8]

        meta = {
            "headline_count": headline_count,
            "source_count": len(SOURCE_REGISTRY),
            "regions_covered": list({s["region"] for s in SOURCE_REGISTRY}),
            "top_signals": scores.get("top_signals", []),
            "reasoning": scores.get("reasoning", ""),
            "model": _CLAUDE_MODEL,
            "bias_note": "News sentiment has structural upward bias. Weight lower than hard data.",
        }

        tier_map = {
            "news_sentiment_economic":    ("economic",    scores.get("economic", 0)),
            "news_sentiment_political":   ("political",   scores.get("political", 0)),
            "news_sentiment_military":    ("military",    scores.get("military", 0)),
            "news_sentiment_existential": ("existential", scores.get("existential", 0)),
        }

        indicators = [
            NewsSentimentIndicator(
                name=name, raw_value=float(value), unit="risk_score_0_100",
                tier=tier, source="news_sentiment",
                source_id=f"{name}_{date_str}_{fp}",
                timestamp=now, metadata=meta,
            )
            for name, (tier, value) in tier_map.items()
        ]

        composite = sum(scores.get(t, 0) for t in ("economic", "political", "military", "existential")) / 4.0
        indicators.append(NewsSentimentIndicator(
            name="news_sentiment_composite", raw_value=round(composite, 1),
            unit="risk_score_0_100", tier="composite", source="news_sentiment",
            source_id=f"news_sentiment_composite_{date_str}_{fp}",
            timestamp=now, metadata=meta,
        ))
        return indicators

    def _stub_data(self) -> list[NewsSentimentIndicator]:
        now = datetime.now(timezone.utc)
        date_str = now.strftime("%Y-%m-%d")
        return [
            NewsSentimentIndicator(
                name=name, raw_value=value, unit="risk_score_0_100",
                tier=tier, source="news_sentiment_stub",
                source_id=f"{name}_stub_{date_str}",
                timestamp=now, metadata={"stub": True},
            )
            for name, tier, value in [
                ("news_sentiment_economic",    "economic",    42.0),
                ("news_sentiment_political",   "political",   48.0),
                ("news_sentiment_military",    "military",    55.0),
                ("news_sentiment_existential", "existential", 30.0),
                ("news_sentiment_composite",   "composite",   43.75),
            ]
        ]

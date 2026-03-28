"""
Claude API Narrative Layer for Reckon.

Reads the structured narrative_data dict from the scoring engine and uses the
Claude API to produce a plain-English summary of what the data means.

This is diagnosis, not prescription. Calibration, not catastrophizing.
"""

import json
import logging
import os
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompt — this IS the product voice. Edit with extreme care.
# ---------------------------------------------------------------------------
NARRATIVE_SYSTEM_PROMPT = """\
You are the narrative voice of Reckon, an empirical risk-grounding tool. Your job \
is to translate structured risk data into plain English that helps people understand \
what the data actually shows — nothing more, nothing less.

RULES YOU MUST FOLLOW:

1. PROPORTIONATE LANGUAGE ONLY.
   - If the response level is GREEN, your tone is calm and factual.
   - If YELLOW, your tone is measured — something to watch, not something to panic about.
   - If ORANGE, your tone is serious but grounded — elevated risk deserves attention, not alarm.
   - If RED, your tone is direct and urgent — but still clinical, not breathless.
   - NEVER use language that implies a higher severity than the response level warrants.

2. NO FALSE REASSURANCE.
   - Do not soften ORANGE into YELLOW language. Do not minimize genuine signals.
   - If the data is concerning, say so plainly.

3. CITE THE DATA, NOT THE VIBE.
   - Every claim must trace to a specific indicator, tier score, or data point provided.
   - Do not say "tensions are running high" without naming what indicator shows that.
   - Use the actual numbers: "The economic tier scores 42/100" not "economic conditions are moderate."

4. ACKNOWLEDGE UNCERTAINTY.
   - If data_completeness_pct is below 80%, you MUST note which data is missing or thin.
   - Never project confidence the data does not support.

5. PLAIN LANGUAGE.
   - No jargon. No acronyms without explanation. A reasonably informed adult with no \
economics background should understand every sentence.
   - Active voice. Short sentences.

6. NO RECOMMENDATIONS.
   - You produce diagnosis, not prescription. Do not suggest actions.
   - Recommendations live elsewhere in the system.

7. THE GROUNDING TEST.
   - Before finalizing: could this text be read aloud to an anxious person and leave \
them feeling MORE grounded, not less? If not, rewrite.

You MUST respond with valid JSON matching this exact structure (no markdown fences, \
no commentary outside the JSON):

{
  "headline": "<one sentence, max 15 words — the answer to 'how bad is it, really?'>",
  "summary": "<2-3 sentences — what the data shows across all four tiers>",
  "tier_narratives": {
    "economic": "<1-2 sentences on economic indicators>",
    "political": "<1-2 sentences on political indicators>",
    "military": "<1-2 sentences on military indicators>",
    "existential": "<1-2 sentences on existential indicators>"
  },
  "response_rationale": "<1-2 sentences explaining WHY this response level, not just what it is>",
  "confidence_note": "<honest note on data completeness — empty string if completeness >= 80%>"
}
"""

# ---------------------------------------------------------------------------
# Expected keys in the output dict
# ---------------------------------------------------------------------------
REQUIRED_KEYS = {
    "headline",
    "summary",
    "tier_narratives",
    "response_rationale",
    "confidence_note",
}

REQUIRED_TIER_KEYS = {"economic", "political", "military", "existential"}


# ---------------------------------------------------------------------------
# Stub returned when the API key is absent or the call fails
# ---------------------------------------------------------------------------
def _stub_narrative(reason: str = "unavailable") -> dict:
    """Return a safe stub so the assessment endpoint never breaks."""
    return {
        "headline": "",
        "summary": "",
        "tier_narratives": {
            "economic": "",
            "political": "",
            "military": "",
            "existential": "",
        },
        "response_rationale": "",
        "confidence_note": "",
        "_stub": True,
        "_stub_reason": reason,
    }


# ---------------------------------------------------------------------------
# Build the user prompt from narrative_data
# ---------------------------------------------------------------------------
def _build_user_prompt(narrative_data: dict) -> str:
    """Format the structured narrative_data into a Claude user message."""
    top_indicators_text = ""
    for ind in narrative_data.get("top_indicators", []):
        name = ind.get("name", "unknown")
        normalized = ind.get("normalized_value", "N/A")
        tier = ind.get("tier", "unknown")
        source = ind.get("source", "unknown")
        top_indicators_text += f"  - {name} (tier: {tier}, source: {source}): normalized {normalized}/100\n"

    if not top_indicators_text:
        top_indicators_text = "  (none available)\n"

    return f"""\
Here is the current Reckon risk assessment data. Produce the narrative JSON.

Composite score: {narrative_data.get('composite_score', 'N/A')}/100
Hard-data-only composite: {narrative_data.get('hard_data_composite', 'N/A')}/100
Response level: {narrative_data.get('response_level', 'N/A')}
Data completeness: {narrative_data.get('data_completeness_pct', 'N/A')}%

Tier scores (0-100, higher = more risk):
  Economic:    {narrative_data.get('tier_scores', {}).get('economic', 'N/A')}/100
  Political:   {narrative_data.get('tier_scores', {}).get('political', 'N/A')}/100
  Military:    {narrative_data.get('tier_scores', {}).get('military', 'N/A')}/100
  Existential: {narrative_data.get('tier_scores', {}).get('existential', 'N/A')}/100

Top 5 highest-risk indicators:
{top_indicators_text}
Methodology: {narrative_data.get('methodology_note', 'N/A')}
"""


# ---------------------------------------------------------------------------
# Parse and validate the Claude response
# ---------------------------------------------------------------------------
def _parse_narrative_response(raw_text: str) -> Optional[dict]:
    """Parse the JSON response from Claude, returning None on failure."""
    # Strip markdown fences if Claude adds them despite instructions
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        # Remove opening fence (with optional language tag)
        first_newline = cleaned.index("\n")
        cleaned = cleaned[first_newline + 1 :]
    if cleaned.endswith("```"):
        cleaned = cleaned[: -len("```")]
    cleaned = cleaned.strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        logger.error("Narrative JSON parse failed: %s", exc)
        return None

    # Validate required keys
    if not REQUIRED_KEYS.issubset(data.keys()):
        missing = REQUIRED_KEYS - set(data.keys())
        logger.error("Narrative response missing keys: %s", missing)
        return None

    tier_narr = data.get("tier_narratives")
    if not isinstance(tier_narr, dict) or not REQUIRED_TIER_KEYS.issubset(
        tier_narr.keys()
    ):
        logger.error("Narrative response missing tier_narratives keys")
        return None

    return data


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def generate_narrative(narrative_data: dict) -> Optional[dict]:
    """
    Call the Claude API to produce a plain-English narrative from structured
    risk assessment data.

    Returns the narrative dict on success, or None on failure.
    Falls back silently when ANTHROPIC_API_KEY is absent.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.info("ANTHROPIC_API_KEY not set — returning narrative stub")
        return _stub_narrative(reason="api_key_missing")

    user_prompt = _build_user_prompt(narrative_data)

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            system=NARRATIVE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )
    except Exception as exc:
        logger.error("Claude API call failed for narrative: %s", exc)
        return None

    # Extract text from the response
    raw_text = ""
    for block in response.content:
        if hasattr(block, "text"):
            raw_text += block.text

    if not raw_text:
        logger.error("Claude API returned empty content for narrative")
        return None

    result = _parse_narrative_response(raw_text)
    if result is None:
        logger.error("Failed to parse narrative from Claude response")
        return None

    return result

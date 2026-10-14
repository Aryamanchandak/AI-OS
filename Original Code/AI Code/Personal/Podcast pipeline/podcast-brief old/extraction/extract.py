"""
extract.py — Pass 1: extract typed claims from transcript using Claude.
"""

import json
import re

from core.models import Claim, ExtractionResult, Transcript
from core.config import MODEL_EXTRACT, EXTRACTION_DIR, require_env
from core.llm import call_anthropic


CLAIM_TYPES_BY_PROFILE = {
    "academic": [
        "paper_reference",
        "statistic",
        "model_or_method",
        "prediction",
    ],
    "current_events": [
        "political",
        "statistic",
        "historical",
        "prediction",
    ],
    "hybrid": [
        "paper_reference",
        "book_reference",
        "historical",
        "statistic",
        "prediction",
        "political",
    ],
}


def extract_claims(transcript: Transcript, profile: str, show_name: str) -> ExtractionResult:
    """Extract structured claims from a transcript for downstream research."""
    require_env("ANTHROPIC_API_KEY")

    claim_types = CLAIM_TYPES_BY_PROFILE.get(profile, CLAIM_TYPES_BY_PROFILE["hybrid"])
    types_doc = "\n".join(f"  - {t}" for t in claim_types)

    prompt = f"""You are extracting research-worthy claims from a podcast transcript.

SHOW: {show_name}
PROFILE: {profile}

TRANSCRIPT:
{transcript.to_prompt_format(max_chars=150_000)}

---

TASK: Extract every significant claim worth verifying or researching.

Eligible claim types for this profile:
{types_doc}

For each claim, output:
- type: one of the eligible types above
- speaker: the speaker's name as labelled in the transcript
- timestamp: the timestamp string (e.g. "01:23:45")
- quote: the VERBATIM quote — exact words from the transcript, no paraphrasing
- summary: 1-2 sentence plain English restatement
- search_query: a 4-8 word search query that would find verification or context

Also output:
- episode_description: 2-3 sentences on what the episode is actually about

RULES:
- Quotes MUST be verbatim. Copy exact words from the transcript.
- Skip filler, jokes, small talk, and meta-commentary about the podcast itself.
- Aim for 10-20 substantive claims. Quality over quantity.
- search_query should be what you'd type into Google or Semantic Scholar.

Return ONLY a single JSON object — no preamble, no markdown fences:

{{
  "episode_description": "...",
  "claims": [
    {{
      "type": "paper_reference",
      "speaker": "Andrej Karpathy",
      "timestamp": "00:23:45",
      "quote": "exact verbatim quote here",
      "summary": "what they're saying in plain English",
      "search_query": "transformer scaling laws Chinchilla"
    }}
  ]
}}"""

    raw = call_anthropic(
        model=MODEL_EXTRACT,
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    )

    data = _parse_json_response(raw)

    claims = []
    for c in data.get("claims", []):
        if not c.get("quote") or not c.get("type"):
            continue
        claims.append(Claim(
            type=str(c.get("type", "unknown")),
            speaker=str(c.get("speaker", "Unknown")),
            timestamp=str(c.get("timestamp", "")),
            quote=str(c.get("quote", "")),
            summary=str(c.get("summary", "")),
            search_query=str(c.get("search_query", "")),
        ))

    result = ExtractionResult(
        episode_id=transcript.episode_id,
        profile=profile,
        claims=claims,
        episode_description=str(data.get("episode_description", "")),
    )

    out_path = EXTRACTION_DIR / f"{transcript.episode_id}.json"
    result.save(out_path)

    return result


def _parse_json_response(raw: str) -> dict:
    """Parse a Claude response that should contain JSON. Tolerates fences."""
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```\s*$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        raise ValueError(f"Could not parse JSON response. First 500 chars:\n{raw[:500]}")

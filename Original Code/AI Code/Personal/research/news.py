"""
research/news.py — Verify political/current-events claims via Brave Search,
filtered to a whitelist of trusted sources.
"""

import os
import time
import json
import re
import requests
from dataclasses import dataclass, asdict

from core.config import MODEL_EXTRACT, load_trusted_domains


@dataclass
class NewsResult:
    title: str
    url: str
    description: str
    source: str    # domain


@dataclass
class NewsFinding:
    claim_summary: str
    claim_quote: str
    claim_speaker: str
    claim_timestamp: str
    results: list[NewsResult]
    verification: str
    verdict: str   # "confirmed" | "contradicted" | "contested" | "unverified" | "nuanced"
    missing_context: str

    def to_dict(self) -> dict:
        return {
            "claim_summary": self.claim_summary,
            "claim_quote": self.claim_quote,
            "claim_speaker": self.claim_speaker,
            "claim_timestamp": self.claim_timestamp,
            "results": [asdict(r) for r in self.results],
            "verification": self.verification,
            "verdict": self.verdict,
            "missing_context": self.missing_context,
        }


# ─── Brave Search ────────────────────────────────────────────────────────────

def search_brave(query: str, limit: int = 5, freshness: str = "py") -> list[NewsResult]:
    """
    Search Brave Search API, filtered to trusted_sources.yaml domains.
    freshness: 'pd' (day), 'pw' (week), 'pm' (month), 'py' (year), or '' (all)
    """
    api_key = os.getenv("BRAVE_API_KEY")
    if not api_key:
        return []

    trusted_domains = load_trusted_domains()

    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": api_key,
    }
    params = {"q": query, "count": 15}
    if freshness:
        params["freshness"] = freshness

    try:
        resp = requests.get(
            "https://api.search.brave.com/res/v1/web/search",
            headers=headers,
            params=params,
            timeout=15,
        )
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception:
        return []

    results = []
    for item in data.get("web", {}).get("results", []):
        url = item.get("url", "")
        if not url:
            continue

        # Extract domain
        try:
            domain = url.split("/")[2].replace("www.", "").lower()
        except IndexError:
            continue

        # Filter to trusted only (if whitelist is non-empty)
        if trusted_domains:
            if not any(d in domain for d in trusted_domains):
                continue

        results.append(NewsResult(
            title=item.get("title", ""),
            url=url,
            description=(item.get("description") or "")[:400],
            source=domain,
        ))

        if len(results) >= limit:
            break

    return results


# ─── Research over a list of claims ──────────────────────────────────────────

def research_news_claims(claims: list, max_claims: int = 15) -> list[NewsFinding]:
    """For each political/current-events claim, search trusted sources and assess."""
    import anthropic

    relevant_types = {"political", "statistic", "historical", "prediction"}
    relevant = [c for c in claims if c.type in relevant_types][:max_claims]

    if not relevant:
        return []

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    findings = []

    for claim in relevant:
        time.sleep(0.5)
        results = search_brave(claim.search_query, limit=5)

        if not results:
            findings.append(NewsFinding(
                claim_summary=claim.summary,
                claim_quote=claim.quote,
                claim_speaker=claim.speaker,
                claim_timestamp=claim.timestamp,
                results=[],
                verification="No results found from trusted sources for this claim.",
                verdict="unverified",
                missing_context="Could not locate verification through the configured trusted source whitelist.",
            ))
            continue

        assessment = _assess_with_claude(client, claim, results)
        findings.append(NewsFinding(
            claim_summary=claim.summary,
            claim_quote=claim.quote,
            claim_speaker=claim.speaker,
            claim_timestamp=claim.timestamp,
            results=results,
            verification=assessment.get("verification", ""),
            verdict=assessment.get("verdict", "unverified"),
            missing_context=assessment.get("missing_context", ""),
        ))

    return findings


def _assess_with_claude(client, claim, results: list[NewsResult]) -> dict:
    """Have Claude assess the claim against the search results."""
    sources_text = "\n\n".join([
        f"SOURCE {i+1}: {r.source}\n"
        f"TITLE: {r.title}\n"
        f"URL: {r.url}\n"
        f"SNIPPET: {r.description}"
        for i, r in enumerate(results)
    ])

    prompt = f"""A current-affairs podcast speaker made this claim:

SPEAKER: {claim.speaker}
QUOTE: "{claim.quote}"
PLAIN SUMMARY: {claim.summary}

Here are results from a whitelist of trusted news and primary sources:

{sources_text}

Assess the speaker's claim against these sources. Be honest about ambiguity — political claims are often contested, and surfacing disagreement between sources is more valuable than forcing a verdict.

Return ONLY this JSON, no preamble or fences:
{{
  "verification": "2-3 sentences on what the trusted sources actually say about this",
  "verdict": "confirmed" or "contradicted" or "contested" or "nuanced" or "unverified",
  "missing_context": "1-2 sentences on what context, statistics, or perspective the speaker omitted that a listener should know"
}}"""

    try:
        response = client.messages.create(
            model=MODEL_EXTRACT,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```\s*$", "", raw)
        return json.loads(raw)
    except Exception:
        return {
            "verification": "Assessment unavailable.",
            "verdict": "unverified",
            "missing_context": "",
        }

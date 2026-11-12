"""
research/academic.py — Find papers and cross-check claims against real research.
Uses Semantic Scholar (free) and arXiv (free).
"""

import os
import time
import json
import re
import requests
from dataclasses import dataclass, asdict
from typing import Optional

from core.config import MODEL_EXTRACT


@dataclass
class Paper:
    title: str
    authors: list[str]
    year: Optional[int]
    abstract: str
    url: str
    source: str   # "semantic_scholar" | "arxiv"


@dataclass
class AcademicFinding:
    claim_summary: str
    claim_quote: str
    claim_speaker: str
    claim_timestamp: str
    papers_found: list[Paper]
    comparison: str
    verdict: str   # "supported" | "overstated" | "contradicted" | "nuanced" | "unverified"
    caveat: str

    def to_dict(self) -> dict:
        return {
            "claim_summary": self.claim_summary,
            "claim_quote": self.claim_quote,
            "claim_speaker": self.claim_speaker,
            "claim_timestamp": self.claim_timestamp,
            "papers_found": [asdict(p) for p in self.papers_found],
            "comparison": self.comparison,
            "verdict": self.verdict,
            "caveat": self.caveat,
        }


# ─── Semantic Scholar ────────────────────────────────────────────────────────

def search_semantic_scholar(query: str, limit: int = 3) -> list[Paper]:
    """Search Semantic Scholar (free, no key required, but rate-limited)."""
    url = "https://api.semanticscholar.org/graph/v1/paper/search"
    params = {
        "query": query,
        "limit": limit,
        "fields": "title,authors,year,abstract,externalIds,openAccessPdf,url",
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code != 200:
            return []
        data = resp.json()
    except Exception:
        return []

    papers = []
    for item in data.get("data", []):
        abstract = item.get("abstract") or ""
        if not abstract.strip():
            continue

        paper_url = ""
        if item.get("openAccessPdf") and item["openAccessPdf"].get("url"):
            paper_url = item["openAccessPdf"]["url"]
        elif item.get("url"):
            paper_url = item["url"]
        else:
            paper_id = item.get("paperId", "")
            if paper_id:
                paper_url = f"https://www.semanticscholar.org/paper/{paper_id}"

        papers.append(Paper(
            title=item.get("title", ""),
            authors=[a.get("name", "") for a in item.get("authors", [])[:3]],
            year=item.get("year"),
            abstract=abstract[:800],
            url=paper_url,
            source="semantic_scholar",
        ))

    return papers


# ─── arXiv ───────────────────────────────────────────────────────────────────

def search_arxiv(query: str, limit: int = 2) -> list[Paper]:
    """Search arXiv API (free)."""
    import xml.etree.ElementTree as ET

    try:
        resp = requests.get(
            "http://export.arxiv.org/api/query",
            params={
                "search_query": f"all:{query}",
                "start": 0,
                "max_results": limit,
                "sortBy": "relevance",
            },
            timeout=15,
        )
        resp.raise_for_status()
    except Exception:
        return []

    papers = []
    try:
        root = ET.fromstring(resp.text)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        for entry in root.findall("atom:entry", ns):
            title_el = entry.find("atom:title", ns)
            summary_el = entry.find("atom:summary", ns)
            if title_el is None or summary_el is None:
                continue

            title = (title_el.text or "").strip().replace("\n", " ")
            abstract = (summary_el.text or "").strip().replace("\n", " ")[:800]
            if not abstract:
                continue

            authors = []
            for author_el in entry.findall("atom:author", ns)[:3]:
                name_el = author_el.find("atom:name", ns)
                if name_el is not None and name_el.text:
                    authors.append(name_el.text)

            link = ""
            for link_el in entry.findall("atom:link", ns):
                if link_el.get("type") == "text/html":
                    link = link_el.get("href", "")
                    break

            published_el = entry.find("atom:published", ns)
            year = int(published_el.text[:4]) if (published_el is not None and published_el.text) else None

            papers.append(Paper(
                title=title,
                authors=authors,
                year=year,
                abstract=abstract,
                url=link,
                source="arxiv",
            ))
    except ET.ParseError:
        return []

    return papers


# ─── Research over a list of claims ──────────────────────────────────────────

def research_academic_claims(claims: list, max_claims: int = 15) -> list[AcademicFinding]:
    """For each academic claim, find papers and have Claude compare."""
    import anthropic

    relevant_types = {"paper_reference", "statistic", "model_or_method", "prediction"}
    relevant = [c for c in claims if c.type in relevant_types][:max_claims]

    if not relevant:
        return []

    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    findings = []

    for claim in relevant:
        # Polite rate limiting
        time.sleep(0.3)

        ss_papers = search_semantic_scholar(claim.search_query, limit=3)
        time.sleep(0.3)
        arxiv_papers = search_arxiv(claim.search_query, limit=2)

        # Dedupe by title
        seen_titles = set()
        all_papers = []
        for p in ss_papers + arxiv_papers:
            key = p.title.lower().strip()
            if key and key not in seen_titles:
                all_papers.append(p)
                seen_titles.add(key)

        if not all_papers:
            findings.append(AcademicFinding(
                claim_summary=claim.summary,
                claim_quote=claim.quote,
                claim_speaker=claim.speaker,
                claim_timestamp=claim.timestamp,
                papers_found=[],
                comparison="No matching papers found via Semantic Scholar or arXiv.",
                verdict="unverified",
                caveat="Could not locate supporting research.",
            ))
            continue

        comparison = _compare_with_claude(client, claim, all_papers[:3])
        findings.append(AcademicFinding(
            claim_summary=claim.summary,
            claim_quote=claim.quote,
            claim_speaker=claim.speaker,
            claim_timestamp=claim.timestamp,
            papers_found=all_papers[:3],
            comparison=comparison.get("comparison", ""),
            verdict=comparison.get("verdict", "unverified"),
            caveat=comparison.get("caveat", ""),
        ))

    return findings


def _compare_with_claude(client, claim, papers: list[Paper]) -> dict:
    """Have Claude compare the speaker's claim against the papers found."""
    papers_text = "\n\n".join([
        f"PAPER {i+1}: {p.title}\n"
        f"Authors: {', '.join(p.authors)}\n"
        f"Year: {p.year}\n"
        f"Abstract: {p.abstract}"
        for i, p in enumerate(papers)
    ])

    prompt = f"""A podcast speaker made this claim:

SPEAKER: {claim.speaker}
QUOTE: "{claim.quote}"
PLAIN SUMMARY: {claim.summary}

The following papers were found in academic search:

{papers_text}

Compare the speaker's claim against what the papers actually say. Be honest — if the speaker overstated findings, say so; if the papers support the claim, say that too; if the papers are tangentially related but don't directly address the claim, say that.

Return ONLY this JSON, no preamble or fences:
{{
  "comparison": "2-3 sentences comparing the claim to the papers' actual findings",
  "verdict": "supported" or "overstated" or "contradicted" or "nuanced" or "unverified",
  "caveat": "1-2 sentences on what's missing, contested, or needs context"
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
            "comparison": "Comparison unavailable.",
            "verdict": "unverified",
            "caveat": "",
        }

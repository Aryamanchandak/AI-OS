"""Bounded web research: plan -> retrieve -> rank -> extract claims.

Retrieval finds candidate URLs via Gemini's Google Search grounding tool, then
fetches and extracts each page's own text directly (grounding only supplies
citations, not full source text). The planner is one structured call and
claim extraction is batched at ten sources per structured call. Failures are
raised as ResearchError so the UI can visibly degrade to ungrounded extraction.
"""

from __future__ import annotations

import html
import ipaddress
import json
import os
import re
import socket
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Protocol
from urllib.parse import (
    parse_qsl,
    urlencode,
    urlparse,
)
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

from engine.schema import (
    EvidenceClaim,
    EvidenceClaimsOut,
    ResearchPlan,
    ResearchPlanOut,
    ResearchQueryGroup,
    SourceRecord,
)

MODEL = "gemini-3.1-pro-preview"
CLAIM_BATCH_SIZE = 10


class ResearchError(RuntimeError):
    """A recoverable research-stage failure."""


@dataclass(frozen=True)
class SearchResult:
    """Minimal provider-neutral representation of one search hit."""

    url: str
    title: str
    snippet: str = ""


class SearchProvider(Protocol):
    """One-method boundary so the provider can be replaced in Release 4."""

    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        ...


class GeminiSearchProvider:
    """Search provider backed by Gemini's Google Search grounding tool.

    Grounding chunk URIs are opaque Google redirect links, not the publisher's
    own URL. ``_fetch`` resolves each one to its real destination when it
    follows the redirect, so this provider only needs to hand back a URL that
    is safe to open and a title for the initial ranking pass.
    """

    def __init__(self, client: genai.Client) -> None:
        self._client = client

    def search(self, query: str, limit: int = 5) -> list[SearchResult]:
        try:
            response = self._client.models.generate_content(
                model=MODEL,
                contents=query,
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    max_output_tokens=1024,
                    thinking_config=types.ThinkingConfig(thinking_level="LOW"),
                ),
            )
        except Exception as exc:
            raise ResearchError(f"search failed for {query!r}: {exc}") from exc
        candidates = response.candidates or []
        metadata = candidates[0].grounding_metadata if candidates else None
        chunks = metadata.grounding_chunks if metadata else None
        if not chunks:
            return []
        results: list[SearchResult] = []
        for chunk in chunks:
            web = chunk.web
            if web and web.uri:
                results.append(
                    SearchResult(url=web.uri, title=web.title or web.domain or web.uri)
                )
            if len(results) >= limit:
                break
        return results


class _TextExtractor(HTMLParser):
    """Small dependency-free visible-text extractor."""

    _SKIP = {"script", "style", "svg", "noscript", "template"}
    _BREAK = {"p", "div", "article", "section", "li", "h1", "h2", "h3", "br"}

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP:
            self._skip_depth += 1
        elif tag in self._BREAK and not self._skip_depth:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag in self._BREAK and not self._skip_depth:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self._skip_depth:
            self.parts.append(data)

    def text(self) -> str:
        value = html.unescape(" ".join(self.parts))
        value = re.sub(r"[ \t]+", " ", value)
        value = re.sub(r"\n\s*\n+", "\n\n", value)
        return value.strip()


def _client(client: genai.Client | None) -> genai.Client:
    """Return an injected client or construct the default authenticated client."""
    if client is not None:
        return client
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        raise ResearchError("GEMINI_API_KEY is not set.")
    return genai.Client()


def _canonical_url(url: str) -> str:
    """Drop fragments and tracking parameters without breaking real query URLs."""
    parsed = urlparse(url)
    tracking = {"gclid", "fbclid", "mc_cid", "mc_eid"}
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_") and key.casefold() not in tracking
    ]
    return parsed._replace(
        fragment="",
        query=urlencode(query, doseq=True),
    ).geturl().rstrip("/")


def _safe_public_url(url: str) -> bool:
    """Reject non-web and local/private targets before fetching."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    host = parsed.hostname.lower()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        return False
    try:
        for info in socket.getaddrinfo(host, parsed.port or 443):
            address = ipaddress.ip_address(info[4][0])
            if not address.is_global:
                return False
    except (OSError, ValueError):
        return False
    return True


def _fetch(result: SearchResult) -> tuple[SearchResult, str] | None:
    """Fetch one public HTML/text result and return cleaned, bounded text."""
    # Resolve and reject private/local destinations before opening the URL to
    # keep model-generated research queries from becoming an SSRF path.
    if not _safe_public_url(result.url):
        return None
    request = Request(
        result.url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; WhatIfResearch/1.0)",
            "Accept": "text/html,text/plain;q=0.9",
        },
    )
    try:
        with urlopen(request, timeout=12) as response:
            content_type = response.headers.get_content_type()
            if content_type not in {"text/html", "text/plain", "application/xhtml+xml"}:
                return None
            raw = response.read(1_500_000)
            charset = response.headers.get_content_charset() or "utf-8"
            final_url = response.geturl()
    except Exception:
        return None
    decoded = raw.decode(charset, errors="replace")
    if content_type == "text/plain":
        text = decoded
        page_title = ""
    else:
        parser = _TextExtractor()
        parser.feed(decoded)
        text = parser.text()
        title_match = re.search(r"<title[^>]*>(.*?)</title>", decoded, re.I | re.S)
        page_title = html.unescape(title_match.group(1)).strip() if title_match else ""
    text = text.strip()
    if len(text) < 200:
        return None
    # Google Search grounding's chunk title is often just the bare domain, so
    # prefer the page's own <title>. The URL is always replaced with the real
    # destination since grounding hands back opaque Google redirect links.
    if final_url != result.url or page_title:
        result = SearchResult(
            url=final_url, title=page_title or result.title, snippet=result.snippet
        )
    return (result, text[:40_000])


def plan_research(
    situation: str,
    mode: str = "quick",
    client: genai.Client | None = None,
) -> ResearchPlan:
    """Create query families in one structured model call."""
    max_queries = 6 if mode == "quick" else 12
    prompt = f"""Plan web research for this causal question:

{situation}

Return query groups totaling at most {max_queries} concise search queries.
Include current context, causal evidence, and at least TWO explicitly skeptical
or counterevidence queries. Counterevidence is mandatory."""
    # Keep the client strongly referenced for the duration of the request.
    # Newer google-genai releases close a temporary Client before the Models
    # call completes when written as `_client(client).models.generate_content`.
    model_client = _client(client)
    response = model_client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=(
                "You are a research planner. Design bounded, diverse searches; "
                "do not answer the question."
            ),
            response_mime_type="application/json",
            response_schema=ResearchPlanOut,
            max_output_tokens=2400,
            thinking_config=types.ThinkingConfig(thinking_level="LOW"),
        ),
    )
    if response.parsed is None:
        raise ResearchError("research planner returned no structured plan")
    groups = [
        ResearchQueryGroup(
            theme=item.theme,
            intent=item.intent,
            queries=[q.strip() for q in item.queries if q.strip()],
        )
        for item in response.parsed.query_groups
    ]
    counter_groups = [
        group for group in groups if group.intent == "counterevidence"
    ]
    if not counter_groups:
        groups.append(
            ResearchQueryGroup(
                theme="causal challenge",
                intent="counterevidence",
                queries=[f"{situation} evidence against causal effect"],
            )
        )
    if len(counter_groups) < 2:
        groups.append(
            ResearchQueryGroup(
                theme="unintended effects",
                intent="counterevidence",
                queries=[f"{situation} unintended effects criticism"],
            )
        )
    # Keep the model's group structure but enforce the mode's hard request cap.
    remaining = max_queries
    bounded: list[ResearchQueryGroup] = []
    # Counterevidence is prioritized so model verbosity cannot push it past cap.
    ordered_groups = sorted(
        enumerate(groups),
        key=lambda pair: (pair[1].intent != "counterevidence", pair[0]),
    )
    for _, group in ordered_groups:
        selected = group.queries[:remaining]
        if selected:
            bounded.append(ResearchQueryGroup(group.theme, group.intent, selected))
            remaining -= len(selected)
        if remaining == 0:
            break
    return ResearchPlan(bounded)


_AUTHORITY_HIGH = (
    ".gov", ".gov.", ".edu", "worldbank.org", "imf.org", "oecd.org",
    "who.int", "un.org", "reuters.com", "apnews.com",
)
_AUTHORITY_MED = (
    "ft.com", "economist.com", "bbc.", "bloomberg.com", "nature.com",
    "sciencedirect.com", "springer.com", "wiley.com",
)


def _bucket(score: float) -> str:
    """Convert a normalized numeric score into the shared magnitude buckets."""
    return "high" if score >= 0.67 else ("med" if score >= 0.34 else "low")


def _publication_date(url: str, _text: str) -> str | None:
    """Extract an explicit date from the canonical URL; never guess from prose."""
    match = re.search(
        r"\b(20\d{2})[-/](0?[1-9]|1[0-2])[-/](0?[1-9]|[12]\d|3[01])\b",
        url,
    )
    if not match:
        return None
    try:
        return datetime(
            int(match.group(1)), int(match.group(2)), int(match.group(3)),
            tzinfo=timezone.utc,
        ).date().isoformat()
    except ValueError:
        return None


def _rank_source(
    result: SearchResult,
    text: str,
    situation: str,
    published_at: str | None,
) -> tuple[str, str, str]:
    """Assign deterministic authority, recency, and relevance buckets."""
    host = (urlparse(result.url).hostname or "").removeprefix("www.").lower()
    # Authority is intentionally a transparent domain heuristic rather than an
    # LLM judgment, making repeated research runs easier to audit.
    authority = (
        "high" if any(key in host for key in _AUTHORITY_HIGH)
        else "med" if any(key in host for key in _AUTHORITY_MED)
        else "low"
    )
    terms = {word for word in re.findall(r"[a-z0-9]{3,}", situation.lower())}
    haystack = f"{result.title} {text[:5000]}".lower()
    overlap = sum(1 for term in terms if term in haystack) / max(1, len(terms))
    relevance = _bucket(min(1.0, overlap * 1.7))
    recency = "low"
    if published_at:
        age_days = (
            datetime.now(timezone.utc).date()
            - datetime.fromisoformat(published_at).date()
        ).days
        recency = "high" if age_days <= 365 else ("med" if age_days <= 1095 else "low")
    return authority, recency, relevance


def retrieve_sources(
    plan: ResearchPlan,
    situation: str,
    mode: str = "quick",
    provider: SearchProvider | None = None,
    client: genai.Client | None = None,
) -> list[SourceRecord]:
    """Search, deduplicate, fetch, clean, and deterministically rank sources."""
    provider = provider or GeminiSearchProvider(_client(client))
    queries = [query for group in plan.query_groups for query in group.queries]
    per_query = 5
    results: list[SearchResult] = []
    # Search queries are independent I/O operations, so issue them concurrently
    # while preserving a hard worker limit.
    with ThreadPoolExecutor(max_workers=min(8, len(queries) or 1)) as pool:
        futures = [pool.submit(provider.search, query, per_query) for query in queries]
        for future in futures:
            try:
                results.extend(future.result())
            except ResearchError:
                continue

    deduped: list[SearchResult] = []
    seen: set[str] = set()
    # Canonicalization prevents tracking variants of one article from consuming
    # multiple places in the bounded retrieval budget.
    for result in results:
        canonical = _canonical_url(result.url)
        key = canonical.casefold()
        if key and key not in seen:
            seen.add(key)
            deduped.append(SearchResult(canonical, result.title, result.snippet))

    fetch_limit = 20 if mode == "quick" else 40
    with ThreadPoolExecutor(max_workers=8) as pool:
        fetched = list(pool.map(_fetch, deduped[: fetch_limit * 2]))
    now = datetime.now(timezone.utc).isoformat()
    candidates: list[SourceRecord] = []
    seen_final: set[str] = set()
    # Google Search grounding gives each query's citations distinct opaque
    # redirect URLs even when they resolve to the same article, so the
    # pre-fetch dedup above cannot catch cross-query duplicates. Dedup again
    # here on the resolved destination from ``_fetch``.
    for item in fetched:
        if item is None:
            continue
        result, text = item
        final_key = _canonical_url(result.url).casefold()
        if final_key in seen_final:
            continue
        seen_final.add(final_key)
        host = (urlparse(result.url).hostname or "").removeprefix("www.")
        published_at = _publication_date(result.url, text)
        authority, recency, relevance = _rank_source(
            result, text, situation, published_at
        )
        candidates.append(
            SourceRecord(
                id="",
                url=result.url,
                title=result.title,
                publisher=host,
                retrieved_at=now,
                extracted_text=text,
                published_at=published_at,
                authority=authority,
                recency=recency,
                relevance=relevance,
            )
        )
    weight = {"low": 0, "med": 1, "high": 2}
    candidates.sort(
        key=lambda source: (
            weight[source.relevance],
            weight[source.authority],
            weight[source.recency],
            source.title.casefold(),
        ),
        reverse=True,
    )
    # Stable source IDs are assigned only after ranking; claim extraction and
    # later evidence links therefore refer to the final displayed order.
    ranked = candidates[:fetch_limit]
    for index, source in enumerate(ranked, start=1):
        source.id = f"s{index}"
    if not ranked:
        raise ResearchError("no usable public sources could be retrieved")
    return ranked


def _claim_batch_prompt(situation: str, sources: list[SourceRecord]) -> str:
    """Build a bounded prompt containing source identifiers and excerpts."""
    payload = [
        {
            "source_id": source.id,
            "title": source.title,
            "publisher": source.publisher,
            "text": source.extracted_text[:6000],
        }
        for source in sources
    ]
    return f"""Question under analysis:
{situation}

Sources:
{json.dumps(payload, ensure_ascii=False)}

Extract only material, source-supported claims. Copy an exact supporting
passage for every claim. Classify each as fact, forecast, inference, or
assumption and say whether it supports, contradicts, or merely contextualizes
the proposed causal situation. Preserve credible contradictions."""


def _extract_claim_batch(
    situation: str,
    sources: list[SourceRecord],
    client: genai.Client,
) -> list[EvidenceClaim]:
    """Extract and locally verify claims from one bounded source batch."""
    response = client.models.generate_content(
        model=MODEL,
        contents=_claim_batch_prompt(situation, sources),
        config=types.GenerateContentConfig(
            system_instruction=(
                "You extract an evidence ledger. Never invent a passage, URL, "
                "source ID, or claim not present in the supplied source text."
            ),
            response_mime_type="application/json",
            response_schema=EvidenceClaimsOut,
            max_output_tokens=16384,
            thinking_config=types.ThinkingConfig(thinking_level="LOW"),
        ),
    )
    if response.parsed is None:
        raise ResearchError("claim extraction returned no structured claims")
    valid_source_ids = {source.id for source in sources}
    source_text = {
        source.id: re.sub(r"\s+", " ", source.extracted_text).strip().casefold()
        for source in sources
    }
    claims: list[EvidenceClaim] = []
    for item in response.parsed.claims:
        # Exact normalized substring matching rejects invented or paraphrased
        # passages that cannot be traced back to the supplied source text.
        normalized_passage = re.sub(
            r"\s+", " ", item.supporting_passage
        ).strip().casefold()
        if (
            item.source_id not in valid_source_ids
            or not normalized_passage
            or normalized_passage not in source_text[item.source_id]
        ):
            continue
        claims.append(
            EvidenceClaim(
                id="",
                text=item.text.strip(),
                source_id=item.source_id,
                supporting_passage=item.supporting_passage.strip(),
                claim_type=item.claim_type,
                stance=item.stance,
                confidence=item.confidence,
                geography=item.geography,
                time_horizon=item.time_horizon,
                concepts=list(item.concepts),
            )
        )
    return claims


def extract_claims(
    situation: str,
    sources: list[SourceRecord],
    client: genai.Client | None = None,
) -> list[EvidenceClaim]:
    """Extract source-linked claims in independent ten-source batches."""
    model_client = _client(client)
    batches = [
        sources[index : index + CLAIM_BATCH_SIZE]
        for index in range(0, len(sources), CLAIM_BATCH_SIZE)
    ]
    with ThreadPoolExecutor(max_workers=len(batches) or 1) as pool:
        futures = [
            pool.submit(_extract_claim_batch, situation, batch, model_client)
            for batch in batches
        ]
        claims = [claim for future in futures for claim in future.result()]
    for index, claim in enumerate(claims, start=1):
        claim.id = f"c{index}"
    return claims

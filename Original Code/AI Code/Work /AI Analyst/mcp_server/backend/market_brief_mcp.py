import os
import urllib.parse
import feedparser
from googlenewsdecoder import gnewsdecoder
from google import genai
from google.genai import types
from pydantic import BaseModel, RootModel
from typing import List
import json
import re
from urllib.parse import urlparse

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("market-news")

# =========================================================
# QUERY GROUPS
# =========================================================
QUERY_GROUPS = {

    "Real Estate": [
        'et realty estate (site:realty.economictimes.indiatimes.com) when:24h',
        '"real estate news" hindustantimes.com when:24h',
        'https://www.moneycontrol.com/news/business/real-estate/ when:24h',
        'business standard real estate news (site:business-standard.com) when:24h',
        'livemint real estate (site:livemint.com) when:24h',
        'real estate (site:constructionworld.in) when:24h'
    ],

    # "Fixed Income": [...],
    # "Equity Markets": [...],
    # "Macro & Policy": [...],
    # "Credit & Banking": [...],
    # "Corporate": [...],
    # "Infrastructure": [...],
}

# =========================================================
# PYDANTIC MODELS (internal)
# =========================================================
class _NewsScore(BaseModel):
    index: int
    relevant: int

class _ClassifyResponse(RootModel[List[_NewsScore]]):
    pass

class _Cluster(BaseModel):
    cluster_id: int
    articles: List[int]

class _ClusterResponse(RootModel[List[_Cluster]]):
    pass

class _Point(BaseModel):
    sentence: str
    sources: List[int]

class _FinalSummary(BaseModel):
    points: List[_Point]

# =========================================================
# PRIVATE HELPERS
# =========================================================
def _get_client() -> genai.Client:
    return genai.Client(api_key=os.environ["GEMINI_API_KEY"])

def _decode_url(url: str) -> str:
    try:
        decoded = gnewsdecoder(url)
        return decoded["decoded_url"] if decoded.get("status") else url
    except Exception:
        return url

def _extract_source(title: str, url: str) -> str:
    try:
        parts = title.split(" - ")
        source = parts[-1].strip()
        if "|" in source:
            source = source.split("|")[-1].strip()
        source = re.sub(r"\s+", " ", source)
        if len(source) > 40 or len(source) < 2:
            raise ValueError("Bad source")
        return source
    except Exception:
        return urlparse(url).netloc.replace("www.", "")

def _render_html(clusters: list[dict], title: str = "Market Brief") -> str:
    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; background: #fafafa; color: #111; }}
.container {{ max-width: 700px; margin: 40px auto; padding: 0 20px; }}
.title {{ font-size: 28px; font-weight: 600; margin-bottom: 20px; }}
.section-title {{ font-size: 18px; font-weight: 600; margin-bottom: 14px; color: #333; }}
.bullet {{ margin-bottom: 16px; font-size: 16px; line-height: 1.7; display: flex; align-items: flex-start; }}
.number {{ min-width: 22px; font-weight: 600; color: #6b7280; }}
.text {{ flex: 1; }}
.source-chip {{ display: inline-block; padding: 2px 8px; margin-left: 6px; border-radius: 10px; background: #f1f3f4; color: #1a73e8; font-size: 12px; text-decoration: none; }}
.source-chip:hover {{ background: #e8f0fe; }}
</style>
</head>
<body>
<div class="container">
<div class="title">📰 {title}</div>
<div class="section-title">Key Points</div>"""

    for i, cluster in enumerate(clusters, 1):
        seen_urls: set[str] = set()
        unique_sources = []
        for s in cluster["sources"]:
            if s["url"] not in seen_urls:
                unique_sources.append(s)
                seen_urls.add(s["url"])

        source_count: dict[str, int] = {}
        for s in unique_sources:
            name = s["name"]
            source_count[name] = source_count.get(name, 0) + 1

        html += f'<div class="bullet"><div class="number">{i}.</div><div class="text">'
        html += cluster["summary"]

        display_count: dict[str, int] = {}
        for source in unique_sources:
            name = source["name"]
            if source_count[name] > 1:
                display_count[name] = display_count.get(name, 0) + 1
                label = f"{name} ({display_count[name]})"
            else:
                label = name
            html += (
                f'<a class="source-chip" href="{source["url"]}" '
                f'target="_blank">{label}</a>'
            )

        html += '</div></div>'

    html += "</div></body></html>"
    return html

# =========================================================
# MCP TOOLS
# =========================================================

@mcp.tool()
def fetch_news(category: str) -> list[dict]:
    """
    Fetch and deduplicate news articles from Google News RSS for a given category.
    Returns a list of article dicts with fields: title, url, source, published_at.

    Valid categories: "Real Estate"
    (full list defined in QUERY_GROUPS)

    Use this standalone to inspect raw articles before running the full pipeline.
    """
    if category not in QUERY_GROUPS:
        raise ValueError(
            f"Unknown category '{category}'. "
            f"Valid categories: {', '.join(QUERY_GROUPS.keys())}"
        )

    raw: list[dict] = []
    for query in QUERY_GROUPS[category]:
        encoded = urllib.parse.quote(query)
        rss_url = (
            f"https://news.google.com/rss/search?"
            f"q={encoded}&hl=en-IN&gl=IN&ceid=IN:en"
        )
        feed = feedparser.parse(rss_url)
        for entry in feed.entries:
            raw.append({
                "title": entry.title,
                "url": entry.link,
                "published_at": getattr(entry, "published", ""),
            })

    for article in raw:
        article["url"] = _decode_url(article["url"])
        article["source"] = _extract_source(article["title"], article["url"])

    seen_titles: set[str] = set()
    articles: list[dict] = []
    for article in raw:
        key = article["title"].strip().lower()
        if key not in seen_titles:
            articles.append(article)
            seen_titles.add(key)

    return articles


@mcp.tool()
def classify_news(articles: list[dict]) -> list[dict]:
    """
    Classify a list of news articles by relevance using Gemini.
    Input: article list from fetch_news or matching schema.
    Returns only the articles classified as relevant.
    """
    if not articles:
        raise ValueError("articles cannot be empty.")

    client = _get_client()
    indexed = [
        {"index": i, "title": a["title"], "url": a["url"]}
        for i, a in enumerate(articles)
    ]

    prompt = f"""
You are a senior equity research analyst at an institutional Asset Management Company.

Your job is to filter ONLY high-signal, investment-relevant news.

Classify each article:
- 1 → relevant (material investment signal)
- 0 → NOT relevant (noise / low-signal)

--------------------------------------------------
STRICT INCLUSION CRITERIA
--------------------------------------------------
Mark as 1 ONLY if the article contains a potentially material investment signal that could impact:

- Company earnings
- Valuation
- Capital flows
- Industry dynamics
- Competitive positioning
- Business operations
- Investor sentiment toward a company or sector

The article should contain clear, actionable, and financially meaningful developments.

--------------------------------------------------
STRICT EXCLUSION CRITERIA
--------------------------------------------------
Mark as 0 for:

- Informational or educational content
- Generic company pages or profiles (e.g., "Godrej Properties Company Page", "Aditya Birla Real Estate P&L", "Brigade Enterprises Ltd announced its quarterly results on May 22, 2026")
- Routine announcements without material impact
- Promotional / PR-style articles
- Broad market commentary without actionable insight
- Minor developments unlikely to affect investment decisions
- Articles lacking clear financial or strategic significance

If the investment impact is weak, speculative, indirect, or unclear → mark 0.

--------------------------------------------------
EDGE CASE RULE
--------------------------------------------------
If unsure → mark 0 (be conservative)

The goal is HIGH PRECISION, not HIGH RECALL.
Only mark 1 when the investment relevance is strong and explicit.

--------------------------------------------------
OUTPUT FORMAT
--------------------------------------------------
Return JSON:
[
{{
    "index": 0,
    "relevant": 1
}}
]

--------------------------------------------------
NEWS
--------------------------------------------------
{json.dumps(indexed, indent=2)}
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema={
                "type": "array",
                "items": _NewsScore.model_json_schema()
            },
            thinking_config=types.ThinkingConfig(thinking_budget=0)
        )
    )

    classified = _ClassifyResponse.model_validate_json(response.text).root
    return [articles[item.index] for item in classified if item.relevant == 1]


@mcp.tool()
def cluster_stories(articles: list[dict]) -> list[dict]:
    """
    Cluster similar news stories and generate a one-sentence summary per cluster.
    Input: relevant article list from classify_news or matching schema.
    Returns a list of cluster dicts with fields: summary, sources (list of {name, url}).
    """
    if not articles:
        raise ValueError("articles cannot be empty.")

    client = _get_client()
    indexed = [{"index": i, "title": a["title"]} for i, a in enumerate(articles)]

    cluster_prompt = f"""
You are a senior equity analyst.

Group the following news into clusters where each cluster represents the SAME underlying story.

CRITICAL RULES:
1. Every article index MUST appear in at least ONE cluster
2. Do NOT leave any article unclustered
3. Do NOT invent indices
4. Group only truly similar news
5. If an article is unique → create a separate cluster

Return JSON:
[
{{
    "cluster_id": 1,
    "articles": [0, 2]
}},
{{
    "cluster_id": 2,
    "articles": [1]
}}
]

News:
{json.dumps(indexed, indent=2)}
"""

    cluster_response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=cluster_prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema={
                "type": "array",
                "items": _Cluster.model_json_schema()
            },
            thinking_config=types.ThinkingConfig(thinking_budget=0)
        )
    )

    clusters = _ClusterResponse.model_validate_json(cluster_response.text).root

    cluster_input_for_summary = [
        {
            "cluster_id": cluster.cluster_id,
            "articles": [
                {"index": idx, "title": articles[idx]["title"]}
                for idx in cluster.articles
            ]
        }
        for cluster in clusters
    ]

    summary_prompt = f"""
You are a senior equity analyst.

Your task is to convert clustered news into a structured set of insights.

Instructions:
- Each cluster = ONE sentence
- The sentence should combine ALL key information from that cluster, but should be extremely crisp
- It should feel like a PERFECT merged headline
- Do NOT summarize loosely — retain ALL important details
- Avoid generic phrasing
- Avoid repetition across sentences
- No titles, no bullets, no redundant words — only one crisp sentence per cluster

CRITICAL:
- Map each sentence to the article indices used
- Use those indices as "sources"

Return JSON:
{{
"points": [
    {{
    "sentence": "...",
    "sources": [0, 2]
    }}
]
}}

Clusters:
{json.dumps(cluster_input_for_summary, indent=2)}
"""

    summary_response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=summary_prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=_FinalSummary.model_json_schema(),
            thinking_config=types.ThinkingConfig(thinking_budget=0)
        )
    )

    final_summary = _FinalSummary.model_validate_json(summary_response.text)

    return [
        {
            "summary": point.sentence,
            "sources": [
                {"name": articles[idx]["source"], "url": articles[idx]["url"]}
                for idx in point.sources
            ]
        }
        for point in final_summary.points
    ]


@mcp.tool()
def generate_news_html(clusters: list[dict]) -> str:
    """
    Render a formatted HTML news brief from clustered stories.
    Input: cluster list from cluster_stories or matching schema.
    Returns HTML string with bullet summaries and clickable source chips.
    """
    if not clusters:
        raise ValueError("clusters cannot be empty.")

    return _render_html(clusters, title="Market Brief")


@mcp.tool()
def run_news_pipeline(category: str) -> str:
    """
    Run the full news brief pipeline for a category.
    Steps: fetch → classify → cluster → generate HTML.
    Returns a rendered HTML brief ready for display.

    Valid categories: "Real Estate"
    (full list defined in QUERY_GROUPS)

    Use component tools individually to inspect intermediate outputs
    or to feed custom article lists into a specific pipeline stage.
    """
    articles = fetch_news(category)
    relevant = classify_news(articles)
    clusters = cluster_stories(relevant)
    return generate_news_html(clusters)

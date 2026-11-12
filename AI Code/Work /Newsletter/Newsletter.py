# Required packages: feedparser, googlenewsdecoder, google-genai, pydantic
# Install with: pip install feedparser googlenewsdecoder google-genai pydantic python-dotenv

# ──────────────────────────────────────────────────────────────────────────────
# STANDARD LIBRARY IMPORTS
# ──────────────────────────────────────────────────────────────────────────────
import os               # To read environment variables (e.g., GEMINI_API_KEY)
import re               # Regular expressions for cleaning source names
import json             # To serialize/deserialize data for LLM prompts
import urllib.parse     # To URL-encode Google News RSS query strings
from urllib.parse import urlparse   # To extract domain from a URL as fallback source name
from datetime import datetime       # To generate today's date for the newsletter header
from typing import List             # For type hints in Pydantic models

# ──────────────────────────────────────────────────────────────────────────────
# THIRD-PARTY IMPORTS
# ──────────────────────────────────────────────────────────────────────────────
from dotenv import load_dotenv      # Loads variables from a .env file into os.environ
load_dotenv()                       # Execute the load — must happen before any os.environ.get() call

import feedparser                   # Parses RSS/Atom feeds (used for Google News RSS)
from googlenewsdecoder import gnewsdecoder  # Decodes obfuscated Google News redirect URLs to real article URLs
from google import genai            # Google Generative AI SDK (Gemini)
from google.genai import types      # Contains config classes like GenerateContentConfig, ThinkingConfig
from pydantic import BaseModel, RootModel  # Data validation and structured JSON parsing

# ──────────────────────────────────────────────────────────────────────────────
# CATEGORY METADATA
# These constants define the 5 investment signal categories used throughout
# the pipeline: ordering, CSS colors, and display labels.
# ──────────────────────────────────────────────────────────────────────────────

# The order in which categories appear in the newsletter layout (left → right)
CATEGORY_ORDER = ["Policy", "Capital", "Demand", "Company", "Infra"]

# Maps each category to its accent color in the HTML output
# Policy and Capital/Demand share orange/red tones; Company/Infra share gold
CATEGORY_COLOR = {
    "Policy":  "var(--red)",
    "Capital": "var(--orange)",
    "Demand":  "var(--orange)",
    "Company": "#b8861a",   # Muted gold — lower urgency than policy/capital
    "Infra":   "#b8861a",   # Same gold as Company
}

# Maps each category to a (heading, subheading) tuple for the section header in HTML
CATEGORY_LABEL = {
    "Policy":  ("Policy &amp; Regulation", "Macro · highest weight in today's brief"),
    "Capital": ("Capital Flows",            "PE deals · debt · funding moves"),
    "Demand":  ("Demand Signals",           "Pre-sales · leasing · pricing"),
    "Company": ("Company Moves",            "Earnings · land acquisitions · launches"),
    "Infra":   ("Infrastructure",           "Metro · highways · TOD impact"),
}

# ──────────────────────────────────────────────────────────────────────────────
# PYDANTIC MODELS
# Each model corresponds to a JSON structure that Gemini is asked to return.
# Using Pydantic ensures structured output validation before the data is used.
# ──────────────────────────────────────────────────────────────────────────────

# Represents one article's relevance score from the classification step
class NewsScore(BaseModel):
    index: int      # Original article index in news_list
    relevant: int   # 1 = investment-relevant, 0 = noise

# Wraps a list of NewsScore objects (top-level JSON array from Gemini)
class ClassifyResponse(RootModel[List[NewsScore]]):
    pass

# One cluster of articles sharing the same underlying news story
class Cluster(BaseModel):
    cluster_id: int         # Unique ID assigned by Gemini
    articles: List[int]     # Indices into relevant_articles list

# Wraps a list of Cluster objects (top-level JSON array from Gemini)
class ClusterResponse(RootModel[List[Cluster]]):
    pass

# One synthesized insight point derived from a cluster
class Point(BaseModel):
    sentence: str       # The merged, crisp headline for the cluster
    sources: List[int]  # Article indices that contributed to this sentence

# Top-level summary containing all synthesized points
class FinalSummary(BaseModel):
    points: List[Point]

# Represents one ranked insight — maps a rank position to a point index
class RankedItem(BaseModel):
    rank: int           # 1 = most important
    point_index: int    # Index into the final_output list

# Wraps a list of RankedItem objects (top-level JSON array from Gemini)
class RankingResponse(RootModel[List[RankedItem]]):
    pass

# Metadata assigned to one ranked signal by the categorization step
class CategorizedSignal(BaseModel):
    point_index: int    # Index into ranked_output
    category: str       # One of: Policy, Capital, Demand, Company, Infra
    tag: str            # Short 1–2 word label (e.g. "RERA", "PE Deal")
    conviction: int     # 1–5 investment signal strength

# Wraps a list of CategorizedSignal objects (top-level JSON array from Gemini)
class CategorizationResponse(RootModel[List[CategorizedSignal]]):
    pass

# The "why it matters" explanation for the top-ranked (lead) signal
class LeadAnalysis(BaseModel):
    why_it_matters: str     # One sentence explaining investment significance

# One forward-looking item in the "what to watch tomorrow" section
class WatchItem(BaseModel):
    title: str  # Short 3–5 word title
    desc: str   # One-line description of what to monitor

# Wraps a list of WatchItem objects (top-level JSON array from Gemini)
class WatchResponse(RootModel[List[WatchItem]]):
    pass

# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def decode_url(url):
    """Resolves a Google News redirect URL to the actual article URL."""
    try:
        decoded = gnewsdecoder(url)
        # gnewsdecoder returns a dict with "status" and "decoded_url" keys
        return decoded["decoded_url"] if decoded.get("status") else url
    except Exception:
        # If decoding fails for any reason, return the original URL unchanged
        return url

def extract_source(title, url):
    """
    Extracts a human-readable publication name from the article title or URL.
    Google News RSS titles follow the pattern: "Headline text - Publication Name"
    """
    try:
        # Split on " - " and take the last segment as the publication name
        parts = title.split(" - ")
        source = parts[-1].strip()

        # Some titles embed extra context after "|" — keep only the last part
        if "|" in source:
            source = source.split("|")[-1].strip()

        # Normalize whitespace (e.g., tabs or double spaces)
        source = re.sub(r"\s+", " ", source)

        # Sanity check: reject if the extracted name is suspiciously long or empty
        if len(source) > 40 or len(source) < 2:
            raise ValueError("Bad source")

        return source
    except Exception:
        # Fallback: derive the source from the URL domain (strip "www." prefix)
        return urlparse(url).netloc.replace("www.", "")

def conviction_html(n, dark=False):
    """
    Generates the HTML for a 5-dot conviction indicator (like a rating bar).
    n filled dots = conviction level; remaining dots are empty.
    dark=True uses the on-dark color scheme (for the lead signal card).
    """
    cls = "conviction on-dark" if dark else "conviction"
    filled = '<span class="fill"></span>' * n          # n orange dots
    empty  = "<span></span>" * (5 - n)                # (5-n) grey dots
    return f'<span class="{cls}">{filled}{empty}</span>'

# ──────────────────────────────────────────────────────────────────────────────
# HTML GENERATOR
# Assembles the full newsletter HTML from the pipeline outputs.
# All data variables come from the main pipeline below.
# ──────────────────────────────────────────────────────────────────────────────
def generate_html(ranked_output, categorization, lead_analysis, watch_items,
                  total_fetched, total_relevant, total_deduped, total_clustered, total_ranked):

    # Format today's date for the dateline (e.g., "Wednesday, 4 June 2026")
    today = datetime.today().strftime("%A, %-d %B %Y")

    # Rough read time estimate: ~3 signals per minute of reading
    read_mins = max(1, total_ranked // 3)

    # Build a dict mapping each category name to a list of (index, item, cs) tuples
    # so we can group signals by category when rendering sections
    cat_map = {cat: [] for cat in CATEGORY_ORDER}

    # Build a lookup from point_index → CategorizedSignal for O(1) access
    cat_lookup = {cs.point_index: cs for cs in categorization}

    # Assign each ranked signal to its category bucket
    for i, item in enumerate(ranked_output):
        cs = cat_lookup.get(i)
        # Fall back to "Company" if the category is unrecognized or missing
        cat = cs.category if cs and cs.category in cat_map else "Company"
        cat_map[cat].append((i, item, cs))

    # ── LEAD SIGNAL (the #1 ranked item) ──────────────────────────────────────
    lead_item = ranked_output[0]                              # Top-ranked signal
    lead_cs   = cat_lookup.get(0)                            # Its category metadata
    lead_conviction = lead_cs.conviction if lead_cs else 4   # Default conviction = 4 if missing
    lead_cat_label  = lead_cs.category if lead_cs else "Signal"  # Category name for display

    # Build source link HTML for the lead card (each source = outlined pill link)
    lead_src_html = ""
    for s in lead_item["sources"]:
        lead_src_html += f'<a class="src-outline" href="{s["url"]}" target="_blank">{s["name"]} ↗</a>\n        '

    # Only include categories that actually have signals today
    active_cats = [cat for cat in CATEGORY_ORDER if cat_map[cat]]

    # ── JUMP NAVIGATION BAR ────────────────────────────────────────────────────
    # Renders the horizontal category nav with colored top bars and signal counts
    jumpnav_html = ""
    for n, cat in enumerate(active_cats, 1):   # n starts at 1 for display numbering
        color = CATEGORY_COLOR[cat]
        count = len(cat_map[cat])
        word  = "signal" if count == 1 else "signals"   # Grammatical singular/plural
        jumpnav_html += f"""      <div class="jump-item">
        <div class="bar" style="background: {color};"></div>
        <div class="jump-head"><span class="jump-num">{n:02d}</span><span class="jump-name">{cat}</span></div>
        <div class="jump-count">{count} {word}</div>
      </div>
"""

    # ── CATEGORY SECTIONS ──────────────────────────────────────────────────────
    # Renders one <section> per active category, each containing its signals
    sections_html = ""
    for n, cat in enumerate(active_cats, 1):
        signals    = cat_map[cat]
        color      = CATEGORY_COLOR[cat]
        label, sub = CATEGORY_LABEL[cat]

        # Company/Infra badges use dark ink text instead of white (gold bg is lighter)
        badge_extra  = "color: var(--ink);" if cat in ("Company", "Infra") else ""
        count_color  = "#b8861a"            if cat in ("Company", "Infra") else color
        word         = "signal" if len(signals) == 1 else "signals"

        # Section header block
        sections_html += f"""
    <section class="section">
      <div class="section-head">
        <div class="section-badge" style="background: {color}; {badge_extra}">{n:02d}</div>
        <div style="flex: 1;">
          <div class="section-title">{label}</div>
          <div class="section-sub">{sub}</div>
        </div>
        <div class="section-count" style="color: {count_color};">{len(signals)} {word}</div>
      </div>
"""
        # Render each signal card inside the section
        for _idx, item, cs in signals:
            tag        = cs.tag        if cs else "Signal"   # Short category tag label
            conviction = cs.conviction if cs else 3          # Default conviction = 3

            # Deduplicate sources by URL (some clusters share the same article URL)
            seen_urls = set()
            unique_sources = []
            for s in item["sources"]:
                if s["url"] not in seen_urls:
                    unique_sources.append(s)
                    seen_urls.add(s["url"])

            # Build chip links — each chip links to the source article
            chips_html = ""
            for s in unique_sources:
                chips_html += (
                    f'<a class="chip" href="{s["url"]}" target="_blank">'
                    f'<span class="chip-dot"></span>{s["name"]}'
                    f'<span class="chip-arrow">↗</span></a>\n              '
                )

            # Signal card HTML: tag column + body (headline + meta row)
            sections_html += f"""
      <div class="signal">
        <div class="signal-tagcol">
          <span class="signal-tag" style="border: 1px solid {color}; color: {color};">{tag}</span>
        </div>
        <div class="signal-body">
          <p class="signal-headline">{item["sentence"]}</p>
          <div class="signal-meta">
            {conviction_html(conviction)}
            <span class="sep"></span>
            <div class="chips">
              {chips_html}
            </div>
          </div>
        </div>
      </div>
"""
        sections_html += "    </section>\n"

    # ── WHAT TO WATCH SECTION ─────────────────────────────────────────────────
    # Three forward-looking items rendered in a 3-column grid
    watch_html = ""
    for w in watch_items:
        watch_html += f"""        <div>
          <p class="watch-item-title">{w.title}</p>
          <div class="watch-item-desc">{w.desc}</div>
        </div>
"""

    # ── FULL HTML DOCUMENT ────────────────────────────────────────────────────
    # Python f-string generates the complete self-contained HTML file.
    # CSS variables (--orange, --red, etc.) are defined in :root for easy theming.
    # Double braces {{ }} are escaped f-string literals for CSS braces.
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>The Daily Brief — Real Estate</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Mulish:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  :root {{
    --orange: #F46523;
    --yellow: #FFD06C;
    --red: #8F1D1C;
    --ink: #1a1614;
    --ink2: #4a423d;
    --paper: #ffffff;
    --bg: #f6f3ee;
    --line: #e6e1d8;
    --mute: #8a807a;
  }}

  * {{ box-sizing: border-box; }}
  html, body {{ margin: 0; padding: 0; }}

  body {{
    background: var(--bg);
    font-family: 'Mulish', system-ui, sans-serif;
    color: var(--ink);
    -webkit-font-smoothing: antialiased;
    padding: 40px 20px;
  }}

  /* Centered card container, max 720px wide */
  .sheet {{
    width: 720px;
    max-width: 100%;
    margin: 0 auto;
    background: var(--paper);
    box-shadow: 0 1px 3px rgba(26,22,20,0.06), 0 12px 40px rgba(26,22,20,0.08);
  }}

  /* Top accent bar: 3 colored segments (red / orange / yellow) */
  .accent-bar {{ display: flex; }}
  .accent-bar > div {{ height: 5px; }}
  .accent-bar .a1 {{ flex: 2; background: var(--red); }}
  .accent-bar .a2 {{ flex: 3; background: var(--orange); }}
  .accent-bar .a3 {{ flex: 2; background: var(--yellow); }}

  /* Main content padding area */
  .pad {{ padding: 36px 48px 0; }}

  /* Masthead: brand name + headline on left, issue number on right */
  .masthead {{
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 28px;
  }}
  .brand-row {{ display: flex; align-items: center; gap: 10px; margin-bottom: 14px; }}

  /* Logo mark: black square with orange offset square (pseudo-element) */
  .logo-mark {{
    width: 26px; height: 26px;
    background: var(--ink);
    position: relative;
    flex: 0 0 auto;
  }}
  .logo-mark::after {{
    content: "";
    position: absolute;
    right: -6px; bottom: -6px;
    width: 14px; height: 14px;
    background: var(--orange);
  }}
  .brand-name {{ font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 1.5px; }}
  .dot {{ width: 4px; height: 4px; border-radius: 99px; background: var(--mute); }}
  .brand-sub {{ font-size: 11px; font-weight: 500; color: var(--mute); }}
  .headline-main {{ font-size: 30px; font-weight: 800; letter-spacing: -0.6px; line-height: 1.1; margin: 0; }}
  .dateline {{ margin-top: 8px; font-size: 13px; font-weight: 500; color: var(--mute); }}
  .issue-no {{ text-align: right; flex: 0 0 auto; }}
  .issue-label {{ font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 1.2px; color: var(--mute); }}
  .issue-num {{ font-size: 28px; font-weight: 800; color: var(--ink); }}

  /* Funnel stats bar: shows the pipeline reduction (Scanned → Ranked) */
  .funnel {{
    display: flex; align-items: stretch;
    background: var(--bg); padding: 14px 18px;
    border-radius: 6px; margin-bottom: 28px;
  }}
  .funnel-step {{ flex: 1; }}
  .funnel-label {{ font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; color: var(--mute); }}
  .funnel-num {{ margin-top: 2px; font-size: 20px; font-weight: 800; color: var(--ink); }}
  .funnel-arrow {{ display: flex; align-items: center; padding: 0 6px; color: var(--mute); font-size: 14px; }}

  /* Lead signal card: dark background, orange left border, yellow accents */
  .lead {{
    position: relative;
    padding: 22px 24px 22px 28px;
    background: var(--ink); color: var(--paper);
    border-radius: 6px; margin-bottom: 36px; overflow: hidden;
  }}
  .lead::before {{
    content: "";
    position: absolute; left: 0; top: 0; bottom: 0;
    width: 5px; background: var(--orange);
  }}
  .lead-tags {{ display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }}
  .tag {{
    display: inline-block; padding: 3px 8px;
    font-size: 10px; font-weight: 700; letter-spacing: 1px;
    text-transform: uppercase; border-radius: 2px; color: #fff;
  }}
  .tag-orange {{ background: var(--orange); }}
  .lead-cat {{ font-size: 10px; font-weight: 700; text-transform: uppercase; letter-spacing: 1.2px; color: var(--yellow); }}
  .lead-headline {{ font-size: 19px; font-weight: 700; line-height: 1.35; letter-spacing: -0.2px; color: var(--paper); margin: 0; }}
  .lead-why {{
    margin-top: 14px; padding-top: 14px;
    border-top: 1px solid #3a342f;
    display: flex; align-items: center; gap: 14px; flex-wrap: wrap;
  }}
  .lead-why-label {{ font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.8px; color: var(--yellow); }}
  .lead-why-text {{ font-size: 12px; font-weight: 400; color: #d8d0c6; flex: 1; min-width: 200px; line-height: 1.5; }}
  .lead-meta {{ margin-top: 14px; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }}
  .lead-meta .sep {{ width: 1px; height: 12px; background: #3a342f; }}

  /* Pill-shaped outline source link used inside the lead card */
  .src-outline {{
    padding: 4px 10px; border-radius: 999px;
    background: transparent; color: var(--paper);
    font-size: 11px; font-weight: 600;
    border: 1px solid #4a423d; text-decoration: none;
  }}

  /* 5-dot conviction indicator: filled dots are orange, empty dots are grey */
  .conviction {{ display: inline-flex; gap: 2px; align-items: center; }}
  .conviction span {{ width: 5px; height: 5px; border-radius: 99px; background: var(--line); }}
  .conviction.on-dark span {{ background: #4a423d; }}   /* darker empty dots for dark bg */
  .conviction span.fill {{ background: var(--orange); }}

  /* Horizontal category navigation bar above sections */
  .jumpnav {{
    display: flex; margin-bottom: 36px;
    border: 1px solid var(--line); border-radius: 6px; overflow: hidden;
  }}
  .jump-item {{ flex: 1; padding: 12px 14px; position: relative; }}
  .jump-item + .jump-item {{ border-left: 1px solid var(--line); }}
  .jump-item .bar {{ position: absolute; top: 0; left: 0; right: 0; height: 3px; }}
  .jump-head {{ display: flex; align-items: baseline; gap: 6px; }}
  .jump-num {{ font-size: 10px; font-weight: 700; color: var(--mute); }}
  .jump-name {{ font-size: 13px; font-weight: 800; }}
  .jump-count {{ margin-top: 2px; font-size: 10px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.8px; color: var(--mute); }}

  /* Section wrapper and header row */
  .section {{ margin-bottom: 36px; }}
  .section-head {{ display: flex; align-items: center; gap: 14px; margin-bottom: 4px; }}
  .section-badge {{
    width: 32px; height: 32px;
    display: flex; align-items: center; justify-content: center;
    color: #fff; font-size: 13px; font-weight: 800; flex: 0 0 auto;
  }}
  .section-title {{ font-size: 16px; font-weight: 800; text-transform: uppercase; letter-spacing: 1.4px; }}
  .section-sub {{ font-size: 11px; font-weight: 500; color: var(--mute); }}
  .section-count {{ font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 1px; }}

  /* Individual signal row: tag column on left, headline + source chips on right */
  .signal {{
    display: flex; gap: 18px;
    padding: 16px 0; border-top: 1px solid var(--line);
    align-items: flex-start;
  }}
  .signal-tagcol {{ flex: 0 0 64px; }}
  .signal-tag {{
    display: inline-block; padding: 3px 8px;
    background: #fff; font-size: 10px; font-weight: 700;
    letter-spacing: 0.8px; text-transform: uppercase; border-radius: 2px;
  }}
  .signal-body {{ flex: 1; min-width: 0; }}
  .signal-headline {{ font-size: 14px; font-weight: 600; color: var(--ink); line-height: 1.45; margin: 0; }}
  .signal-meta {{ display: flex; align-items: center; gap: 14px; margin-top: 10px; flex-wrap: wrap; }}
  .signal-meta .sep {{ width: 1px; height: 12px; background: var(--line); }}

  /* Source chip links: small pill with orange dot and external arrow */
  .chips {{ display: flex; gap: 6px; flex-wrap: wrap; }}
  .chip {{
    display: inline-flex; align-items: center; gap: 6px;
    padding: 4px 10px; border-radius: 999px;
    background: #fff; color: var(--ink2);
    font-size: 11px; font-weight: 600; letter-spacing: 0.2px;
    border: 1px solid var(--line); white-space: nowrap; text-decoration: none;
  }}
  .chip .chip-dot {{ width: 5px; height: 5px; background: var(--orange); border-radius: 99px; }}
  .chip .chip-arrow {{ color: var(--mute); font-weight: 500; }}

  /* "What to watch" panel: beige background, red left border, 3-col grid */
  .watch {{
    margin-top: 8px; padding: 24px 26px;
    background: var(--bg); border-radius: 6px;
    border-left: 4px solid var(--red);
  }}
  .watch-label {{ font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 1.4px; color: var(--red); }}
  .watch-grid {{ margin-top: 14px; display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 18px; }}
  .watch-item-title {{ font-size: 13px; font-weight: 700; color: var(--ink); margin: 0 0 4px; }}
  .watch-item-desc {{ font-size: 11px; font-weight: 500; color: var(--mute); line-height: 1.45; }}

  /* Footer: brand info on left, nav links on right */
  .footer {{
    margin-top: 32px; padding: 22px 0 36px;
    border-top: 1px solid var(--line);
    display: flex; justify-content: space-between; align-items: center;
  }}
  .footer-name {{ font-size: 11px; font-weight: 700; color: var(--ink); }}
  .footer-sub {{ font-size: 10px; font-weight: 500; color: var(--mute); }}
  .footer-links {{ display: flex; gap: 18px; }}
  .footer-links a {{ font-size: 11px; font-weight: 600; color: var(--ink); text-decoration: none; }}
  .footer-links a.feedback {{ color: var(--orange); }}   /* Feedback link uses orange accent */

  /* Mobile: collapse horizontal layouts to vertical stacks */
  @media (max-width: 760px) {{
    .pad {{ padding: 28px 24px 0; }}
    .funnel, .jumpnav {{ flex-wrap: wrap; }}
    .watch-grid {{ grid-template-columns: 1fr; }}
    .signal-tagcol {{ flex-basis: 56px; }}
  }}
</style>
</head>
<body>
<div class="sheet">

  <!-- 3-segment colored accent bar at the very top of the card -->
  <div class="accent-bar">
    <div class="a1"></div>
    <div class="a2"></div>
    <div class="a3"></div>
  </div>

  <div class="pad">

    <!-- Masthead: brand + headline (left) and issue number (right) -->
    <header class="masthead">
      <div>
        <div class="brand-row">
          <div class="logo-mark"></div>
          <span class="brand-name">The Daily Brief</span>
          <span class="dot"></span>
          <span class="brand-sub">Real Estate · India</span>
        </div>
        <h1 class="headline-main">What moved today.</h1>
        <div class="dateline">{today} · {total_ranked} signals · {read_mins} min read</div>
      </div>
      <div class="issue-no">
        <div class="issue-label">Issue</div>
        <div class="issue-num">001</div>
      </div>
    </header>

    <!-- Pipeline funnel stats: shows how many articles were processed at each stage -->
    <div class="funnel">
      <div class="funnel-step">
        <div class="funnel-label">Scanned</div>
        <div class="funnel-num">{total_fetched}</div>
      </div>
      <div class="funnel-arrow">›</div>
      <div class="funnel-step">
        <div class="funnel-label">Relevant</div>
        <div class="funnel-num">{total_relevant}</div>
      </div>
      <div class="funnel-arrow">›</div>
      <div class="funnel-step">
        <div class="funnel-label">Deduped</div>
        <div class="funnel-num">{total_deduped}</div>
      </div>
      <div class="funnel-arrow">›</div>
      <div class="funnel-step">
        <div class="funnel-label">Clustered</div>
        <div class="funnel-num">{total_clustered}</div>
      </div>
      <div class="funnel-arrow">›</div>
      <div class="funnel-step">
        <div class="funnel-label">Ranked</div>
        <div class="funnel-num">{total_ranked}</div>
      </div>
    </div>

    <!-- Lead signal card: the #1 ranked investment signal with "why it matters" -->
    <div class="lead">
      <div class="lead-tags">
        <span class="tag tag-orange">Lead Signal</span>
        <span class="lead-cat">{lead_cat_label} · Highest priority</span>
      </div>
      <p class="lead-headline">{lead_item["sentence"]}</p>
      <div class="lead-why">
        <span class="lead-why-label">Why it matters</span>
        <span class="lead-why-text">{lead_analysis.why_it_matters}</span>
      </div>
      <div class="lead-meta">
        {conviction_html(lead_conviction, dark=True)}
        <span class="sep"></span>
        {lead_src_html}
      </div>
    </div>

    <!-- Jump navigation bar: one tab per active category -->
    <nav class="jumpnav">
{jumpnav_html}    </nav>

    <!-- Category sections: each active category renders its signals here -->
{sections_html}

    <!-- What to watch tomorrow: 3 forward-looking items -->
    <div class="watch">
      <div class="watch-label">What to watch · tomorrow</div>
      <div class="watch-grid">
{watch_html}      </div>
    </div>

    <!-- Footer: publication info + archive / feedback links -->
    <footer class="footer">
      <div>
        <div class="footer-name">Real Estate · India</div>
        <div class="footer-sub">AMC · Equity Research · Real Estate</div>
      </div>
      <div class="footer-links">
        <a href="#">Archive</a>
        <a href="#">Preferences</a>
        <a href="#" class="feedback">Feedback →</a>
      </div>
    </footer>

  </div>
</div>
</body>
</html>
"""


# ──────────────────────────────────────────────────────────────────────────────
# MAIN PIPELINE
# Runs when the script is executed directly (not imported as a module).
# The pipeline has 10 sequential steps, each building on the previous output.
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":

    # Load the Gemini API key from environment (set in .env or shell)
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable not set")

    # Initialize the Gemini client — all LLM calls go through this object
    client = genai.Client(api_key=api_key)

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 1: Define search queries
    # Each query targets a specific publication via Google News RSS.
    # "when:1d" restricts results to articles published in the last 24 hours.
    # "site:" restricts the search to a specific domain.
    # ──────────────────────────────────────────────────────────────────────────
    queries = [
        'et realty estate news (site:realty.economictimes.indiatimes.com) when:1d',
        '"real estate news" hindustantimes.com when:1d',
        'https://www.moneycontrol.com/news/business/real-estate/ when:1d',
        'business standard real estate news (site:business-standard.com) when:1d',
        'livemint real estate news (site:livemint.com) when:1d',
        'cnbc tv18 real estate news (site:cnbctv18.com) when:1d',
        'real estate news (site:constructionworld.in) when:1d'
    ]

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 2: Fetch news articles from Google News RSS
    # For each query, build a Google News RSS URL, parse it with feedparser,
    # and collect all article entries into a flat list.
    # ──────────────────────────────────────────────────────────────────────────
    news_list = []   # Accumulates all articles across all queries

    for query in queries:
        # URL-encode the query string so special characters don't break the URL
        encoded_query = urllib.parse.quote(query)
        # Build the Google News RSS endpoint with Indian locale settings
        rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"
        feed = feedparser.parse(rss_url)   # Parse the RSS feed
        for entry in feed.entries:
            # Assign a sequential index so we can reference articles by number later
            news_list.append({
                "index": len(news_list),   # Current length = next available index
                "title": entry.title,      # Full RSS title (includes publication name)
                "url": entry.link          # Google News redirect URL (not the real article URL yet)
            })

    total_fetched = len(news_list)   # Record count before any filtering

    # Log all fetched articles to the console for inspection
    print("\n" + "="*100)
    print("STEP 2: RAW NEWS FETCHED")
    print("="*100)
    print(f"\nTotal Articles Fetched: {total_fetched}\n")
    for item in news_list:
        print(f"[{item['index']}] {item['title']}")
        print(f"     URL: {item['url']}\n")

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 3: Classify articles as relevant or irrelevant
    # Sends all article titles to Gemini with a detailed prompt that defines
    # inclusion/exclusion criteria. Returns a relevance score (0 or 1) per article.
    # thinking_budget=0 disables extended thinking to keep latency low.
    # ──────────────────────────────────────────────────────────────────────────
    classify_prompt = f"""
You are a senior real estate equity analyst at an Indian Asset Management Company.

Your job is to filter ONLY high-signal, investment-relevant news.

Classify each article:
- 1 → relevant (investment signal)
- 0 → NOT relevant (noise / low-signal)

--------------------------------------------------
STRICT INCLUSION CRITERIA (must meet at least one)
--------------------------------------------------
Mark as 1 ONLY if the article has clear impact on:

1. Policy / regulation affecting real estate (RERA, govt schemes, zoning, TOD, etc.)
2. Capital flows (PE investments, large funding, debt stress, refinancing risk)
3. Demand indicators (sales trends, leasing data, absorption, pricing trends)
4. Large-scale development / redevelopment / infrastructure
5. Meaningful company performance (pre-sales, margins, large deals)

--------------------------------------------------
STRICT EXCLUSION CRITERIA (ALWAYS mark 0)
--------------------------------------------------
Even if related to real estate, mark 0 if:

- Generic company pages:
  (e.g., "Godrej Properties Company Page", "Aditya Birla Real Estate P&L")

- Tax / compliance / generic finance systems:
  (e.g., TRACES, TDS, TCS unless major structural reform)

- Non-core real estate:
  (e.g., solar projects, unrelated subsidiaries)

- Informational / consumer guides:
  (e.g., "what it means for homebuyers")

- Any article that does NOT provide new macro, policy, or capital signal

--------------------------------------------------
EDGE CASE RULE
--------------------------------------------------
If unsure → mark 0 (be conservative)

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
{json.dumps(news_list, indent=2)}
"""

    # Call Gemini with structured JSON output — response is validated against NewsScore schema
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=classify_prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema={
                "type": "array",
                "items": NewsScore.model_json_schema()   # Tells Gemini the exact output shape
            },
            thinking_config=types.ThinkingConfig(thinking_budget=0)  # No chain-of-thought for speed
        )
    )

    # Parse and validate the JSON response into a list of NewsScore objects
    classified = ClassifyResponse.model_validate_json(response.text).root

    # Log classification results
    print("\n" + "="*100)
    print("STEP 3: CLASSIFICATION OUTPUT")
    print("="*100)

    relevant_count = 0
    for item in classified:
        tag = "RELEVANT" if item.relevant == 1 else "NOT RELEVANT"
        print(f"[{item.index}] {tag}")
        if item.relevant == 1:
            relevant_count += 1

    total_relevant = relevant_count
    print(f"\nTotal Relevant: {relevant_count}")
    print(f"Total Irrelevant: {len(classified) - relevant_count}")

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 4: Filter — keep only relevant articles
    # Build a new list with only the articles that scored relevant=1.
    # ──────────────────────────────────────────────────────────────────────────
    relevant_articles = []

    for item in classified:
        if item.relevant == 1:
            # Look up the original article data by index from news_list
            article = news_list[item.index]
            relevant_articles.append({
                "index": item.index,
                "title": article["title"],
                "url": article["url"]    # Still the Google News redirect URL at this point
            })

    print("\n" + "="*100)
    print("STEP 4: RELEVANT ARTICLES (BEFORE DECODE)")
    print("="*100)
    for art in relevant_articles:
        print(f"[{art['index']}] {art['title']}")
        print(f"     URL: {art['url']}\n")

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 4.5: Decode Google News redirect URLs to real article URLs
    # Google News wraps all article links in a redirect. gnewsdecoder resolves
    # these so the final HTML links go directly to the source publication.
    # ──────────────────────────────────────────────────────────────────────────
    for article in relevant_articles:
        article["url"] = decode_url(article["url"])   # Mutate in-place

    print("\n" + "="*100)
    print("STEP 4.5: DECODED URLS")
    print("="*100)
    for art in relevant_articles:
        print(f"[{art['index']}] {art['title']}")
        print(f"     DECODED URL: {art['url']}\n")

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 4.6: Exact title deduplication
    # Multiple queries can surface the same article from different sources.
    # We remove duplicates by comparing lowercase-stripped titles.
    # ──────────────────────────────────────────────────────────────────────────
    print("\n" + "="*100)
    print("STEP 4.6: EXACT DEDUP")
    print("="*100)

    seen_titles = set()      # Track which titles we've already kept
    dedup_articles = []

    for art in relevant_articles:
        title_clean = art["title"].strip().lower()   # Normalize before comparison
        if title_clean not in seen_titles:
            dedup_articles.append(art)
            seen_titles.add(title_clean)
        else:
            print(f"Removed duplicate: {art['title']}")

    relevant_articles = dedup_articles    # Replace with deduplicated list
    total_deduped = len(relevant_articles)
    print(f"\nAfter dedup: {total_deduped} articles")

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 5: Cluster similar articles into story groups
    # Sends article titles to Gemini and asks it to group articles that cover
    # the same underlying news story. Each cluster becomes one summary point.
    # ──────────────────────────────────────────────────────────────────────────

    # Re-index articles from 0 for the clustering prompt (clean sequential indices)
    cluster_input = [
        {"index": i, "title": art["title"]}
        for i, art in enumerate(relevant_articles)
    ]

    cluster_prompt = f"""
You are a real estate equity analyst.

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
{json.dumps(cluster_input, indent=2)}
"""

    cluster_response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=cluster_prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema={
                "type": "array",
                "items": Cluster.model_json_schema()
            },
            thinking_config=types.ThinkingConfig(thinking_budget=0)
        )
    )

    clusters = ClusterResponse.model_validate_json(cluster_response.text).root

    # Safety check: ensure every article appears in at least one cluster.
    # Gemini occasionally misses indices, especially with large article sets.
    all_indices       = set(range(len(relevant_articles)))
    clustered_indices = set()
    for cluster in clusters:
        clustered_indices.update(cluster.articles)

    missing = all_indices - clustered_indices
    if missing:
        print(f"\nMissing indices detected, fixing: {missing}")
        next_id = max(c.cluster_id for c in clusters) + 1 if clusters else 1
        for idx in missing:
            # Create a singleton cluster for each missing article
            clusters.append(Cluster(cluster_id=next_id, articles=[idx]))
            next_id += 1

    total_clustered = len(clusters)

    print("\n" + "="*100)
    print("STEP 5: CLUSTERS")
    print("="*100)
    for cluster in clusters:
        print(f"\nCluster {cluster.cluster_id} ({len(cluster.articles)} articles):")
        for idx in cluster.articles:
            print(f"  [{idx}] {relevant_articles[idx]['title']}")

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 6: Summarize each cluster into one crisp merged headline
    # Gemini synthesizes all articles in a cluster into a single sentence that
    # captures all key information without being generic.
    # ──────────────────────────────────────────────────────────────────────────

    # Build structured input: each cluster has its cluster_id and the titles of its articles
    cluster_input_for_summary = [
        {
            "cluster_id": cluster.cluster_id,
            "articles": [
                {"index": idx, "title": relevant_articles[idx]["title"]}
                for idx in cluster.articles
            ]
        }
        for cluster in clusters
    ]

    summary_prompt = f"""
You are a senior real estate equity analyst.

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

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=summary_prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=FinalSummary.model_json_schema(),
            thinking_config=types.ThinkingConfig(thinking_budget=0)
        )
    )

    final_summary = FinalSummary.model_validate_json(response.text)

    # Resolve article indices in each point's sources to actual name + URL dicts
    # so the HTML generator has everything it needs without further lookups
    final_output = []
    for point in final_summary.points:
        sources = []
        for idx in point.sources:
            art = relevant_articles[idx]
            sources.append({
                "name": extract_source(art["title"], art["url"]),  # Human-readable publication name
                "url":  art["url"]                                  # Decoded article URL
            })
        final_output.append({"sentence": point.sentence, "sources": sources})

    print("\n" + "="*100)
    print("STEP 6: FINAL OUTPUT")
    print("="*100)
    for i, item in enumerate(final_output, 1):
        print(f"\n{i}. {item['sentence']}")
        for s in item["sources"]:
            print(f"     - {s['name']}: {s['url']}")

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 7: Rank insights by investment importance
    # Sends all summary points to Gemini with a ranked priority framework.
    # Returns a list mapping rank positions (1 = best) to point indices.
    # ──────────────────────────────────────────────────────────────────────────

    # Build ranking input — include the sentence text so Gemini can reason about it
    ranking_input = [
        {"point_index": i, "sentence": point.sentence, "sources": point.sources}
        for i, point in enumerate(final_summary.points)
    ]

    ranking_prompt = f"""
You are a senior real estate equity analyst.

Your task is to rank the following insights based on INVESTMENT IMPORTANCE.

--------------------------------------------------
STRICT RANKING PRIORITY
--------------------------------------------------

1. National policy / regulatory change
2. Capital flows (PE, funding, debt stress)
3. Demand indicators (sales, leasing, absorption)
4. Large-scale redevelopment / infrastructure
5. Company-specific performance
6. Project-level announcements
7. Low-signal / informational content

--------------------------------------------------
TIE-BREAKERS
--------------------------------------------------
- Prefer broader macro impact
- Prefer forward-looking signals
- Prefer capital allocation signals over descriptive news

--------------------------------------------------
RULES
--------------------------------------------------
- Assign a UNIQUE rank to each point
- Rank 1 = MOST IMPORTANT
- Use ALL points exactly once
- Do NOT skip or merge anything

--------------------------------------------------
OUTPUT FORMAT
--------------------------------------------------
[
  {{
    "rank": 1,
    "point_index": 2
  }},
  {{
    "rank": 2,
    "point_index": 0
  }}
]

--------------------------------------------------
POINTS
--------------------------------------------------
{json.dumps(ranking_input, indent=2)}
"""

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=ranking_prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema={
                "type": "array",
                "items": RankedItem.model_json_schema()
            },
            thinking_config=types.ThinkingConfig(thinking_budget=0)
        )
    )

    ranking = RankingResponse.model_validate_json(response.text).root

    # Build a lookup from point_index → output item for O(1) reordering
    point_map    = {i: final_output[i] for i in range(len(final_output))}
    sorted_ranks = sorted(ranking, key=lambda x: x.rank)   # Sort by rank ascending (1 first)
    ranked_output = [point_map[item.point_index] for item in sorted_ranks]  # Reorder output
    total_ranked  = len(ranked_output)

    print("\n" + "="*100)
    print("STEP 7: FINAL RANKED OUTPUT")
    print("="*100)
    for i, item in enumerate(ranked_output, 1):
        print(f"\n{i}. {item['sentence']}")
        for s in item["sources"]:
            print(f"     - {s['name']}: {s['url']}")

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 8: Categorize each ranked signal
    # Assigns a category (Policy / Capital / Demand / Company / Infra),
    # a short tag (e.g. "RERA", "PE Deal"), and a conviction score (1–5).
    # ──────────────────────────────────────────────────────────────────────────

    # Use the ranked order's indices so point_index matches ranked_output[i]
    cat_input = [
        {"point_index": i, "sentence": item["sentence"]}
        for i, item in enumerate(ranked_output)
    ]

    cat_prompt = f"""
You are a senior real estate equity analyst.

Categorize each insight and assign a short tag and conviction score.

Categories (use exactly one):
- Policy   → regulatory changes, RERA, GST, zoning, govt schemes
- Capital  → PE deals, funding rounds, debt, refinancing, NBFC exposure
- Demand   → pre-sales, leasing, absorption, pricing trends
- Company  → earnings, land acquisitions, project launches, guidance
- Infra    → metro, highways, TOD, infrastructure projects

Tag: 1–2 word label (e.g. "RERA", "PE deal", "Sales", "Land", "TOD", "Highway", "Earnings", "Debt", "Funding", "Tax")

Conviction (1–5):
5 = very high investment signal
4 = high
3 = moderate
2 = low
1 = marginal

Return JSON:
[
  {{
    "point_index": 0,
    "category": "Policy",
    "tag": "RERA",
    "conviction": 5
  }}
]

Insights:
{json.dumps(cat_input, indent=2)}
"""

    cat_response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=cat_prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema={
                "type": "array",
                "items": CategorizedSignal.model_json_schema()
            },
            thinking_config=types.ThinkingConfig(thinking_budget=0)
        )
    )

    categorization = CategorizationResponse.model_validate_json(cat_response.text).root

    print("\n" + "="*100)
    print("STEP 8: CATEGORIZATION")
    print("="*100)
    for cs in categorization:
        print(f"[{cs.point_index}] {cs.category} | {cs.tag} | conviction: {cs.conviction}")

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 9: Generate "why it matters" for the lead (top-ranked) signal
    # This one-sentence explanation goes in the featured lead card at the top
    # of the newsletter. It must explain the investment mechanism, not restate
    # the headline.
    # ──────────────────────────────────────────────────────────────────────────
    lead_prompt = f"""
You are a senior real estate equity analyst writing for an AMC equity research team.

Write ONE concise sentence explaining the investment significance of this news signal.
Be specific about the mechanism (e.g. cost of capital, demand compression, alpha signal).
Do NOT restate the headline — explain WHY it matters to an equity investor.

Signal: {ranked_output[0]["sentence"]}

Return JSON:
{{
  "why_it_matters": "..."
}}
"""

    lead_response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=lead_prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=LeadAnalysis.model_json_schema(),
            thinking_config=types.ThinkingConfig(thinking_budget=0)
        )
    )

    lead_analysis = LeadAnalysis.model_validate_json(lead_response.text)

    print("\n" + "="*100)
    print("STEP 9: LEAD ANALYSIS")
    print("="*100)
    print(f"Why it matters: {lead_analysis.why_it_matters}")

    # ──────────────────────────────────────────────────────────────────────────
    # STEP 10: Generate "what to watch tomorrow" items
    # Produces exactly 3 forward-looking items based on today's signals.
    # These appear in the bottom panel of the newsletter.
    # [:3] ensures we never render more than 3 items even if Gemini returns more.
    # ──────────────────────────────────────────────────────────────────────────
    watch_prompt = f"""
You are a senior real estate equity analyst.

Based on today's signals, identify exactly 3 forward-looking items to watch tomorrow.
Each should be a specific upcoming data point, event, or decision — not a vague theme.

Return JSON:
[
  {{
    "title": "Short title (3–5 words)",
    "desc": "One-line description of what to watch for"
  }}
]

Today's signals:
{json.dumps([item["sentence"] for item in ranked_output], indent=2)}
"""

    watch_response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=watch_prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema={
                "type": "array",
                "items": WatchItem.model_json_schema()
            },
            thinking_config=types.ThinkingConfig(thinking_budget=0)
        )
    )

    # Slice to exactly 3 items regardless of how many Gemini returned
    watch_items = WatchResponse.model_validate_json(watch_response.text).root[:3]

    print("\n" + "="*100)
    print("STEP 10: WHAT TO WATCH")
    print("="*100)
    for w in watch_items:
        print(f"  {w.title}: {w.desc}")

    # ──────────────────────────────────────────────────────────────────────────
    # GENERATE HTML OUTPUT
    # Pass all pipeline outputs to generate_html() which assembles the final
    # self-contained HTML file. The file is written to market_brief.html.
    # ──────────────────────────────────────────────────────────────────────────
    html_content = generate_html(
        ranked_output   = ranked_output,      # List of {sentence, sources} dicts in rank order
        categorization  = categorization,     # List of CategorizedSignal objects
        lead_analysis   = lead_analysis,      # LeadAnalysis with why_it_matters text
        watch_items     = watch_items,         # List of 3 WatchItem objects
        total_fetched   = total_fetched,       # Count of raw articles from RSS feeds
        total_relevant  = total_relevant,      # Count after LLM relevance filter
        total_deduped   = total_deduped,       # Count after exact title deduplication
        total_clustered = total_clustered,     # Count of story clusters (= summary points)
        total_ranked    = total_ranked,        # Count of final ranked signals (= clustered)
    )

    output_path = "market_brief.html"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"\nDone. HTML saved to {output_path}")

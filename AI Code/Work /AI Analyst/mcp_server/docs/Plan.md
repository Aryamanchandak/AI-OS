# MCP Server Implementation Plan

## Purpose

This document is the single reference for building the MCP server across all tools in the system. It covers the architectural decision made (Option B), the classification of every tool, full signatures for every component and composite, module structure, and the implementation rules that must be followed consistently throughout.

Read this before writing any code. Every structural decision here is deliberate.

---

## Architectural Decision: Option B

Every workflow is exposed as **both** a composite MCP tool and a set of component MCP tools. Simple atomic operations are exposed as single MCP tools with no decomposition.

The key rule is:

> **Composite tools call component functions directly as Python. They do not call components through the MCP protocol.**

The `@mcp.tool()` decorator is purely a registration mechanism — it tells the MCP server to expose that function to the orchestrator. It does not change how the function behaves when called from Python. A composite tool calling a component is an ordinary function call, not a protocol call.

```python
# Both are registered. The composite calls the component directly.

@mcp.tool()
def extract_contracts(pdf_bytes: bytes) -> list[dict]:
    return _extract_with_gemini(pdf_bytes)

@mcp.tool()
def process_lease_deed(pdf_bytes: bytes) -> tuple[bytes, bytes]:
    contracts = extract_contracts(pdf_bytes)   # plain Python call — not MCP
    excel     = build_rent_roll(contracts)
    clauses   = analyze_clauses(pdf_bytes)
    docx      = build_clause_report(clauses)
    return excel, docx
```

### Why this matters

The orchestrator gains the ability to call any step independently. It can extract contracts without generating a rent roll. It can regenerate a single credit note section without rerunning all ten. It can fetch raw news articles and inspect them before committing to a full pipeline run. The composite tools still exist for one-shot full-workflow calls. Nothing is lost, and the orchestrator gets maximum flexibility.

---

## Pre-Build Decisions (Resolve Before Writing Any Tool Code)

### 1. Remove `api_key` from every tool signature

The current design passes `api_key: str` as a parameter to every tool. This is wrong for two reasons: it exposes the key in the orchestrator's context window on every call, and it pollutes 23 tool signatures with infrastructure detail.

**Fix:** Initialise once at server startup and store as module-level state.

```python
# config.py
_api_key: str = ""

def configure(api_key: str) -> None:
    global _api_key
    _api_key = api_key

def get_api_key() -> str:
    if not _api_key:
        raise RuntimeError("API key not configured. Call configure() at startup.")
    return _api_key
```

```python
# server.py (startup)
from config import configure
configure(os.environ["GEMINI_API_KEY"])
```

Every tool that needs the key calls `get_api_key()` internally. No tool takes `api_key` as a parameter.

### 2. Fix `generate_credit_note` output type

The current spec says it returns `dict[str, str]` or a single assembled string. Pick one. The decision here is **`dict[str, str]`** — section name mapped to generated text. The orchestrator can join sections itself if it needs a flat string. A flat string cannot be split back into sections cleanly.

### 3. Expose valid categories for `fetch_news`

`fetch_news` requires a `category` string that must match a key in `QUERY_GROUPS`. The orchestrator has no way to know valid values without being told. Include the full list of valid category strings in the tool's description string — not as a parameter enum, just in the docstring the MCP server surfaces.

### 4. Extract the `summarize_youtube_video` inline logic

The summarisation logic in `youtube_intelligence.py` is currently inline. Before registration, extract it into a named function `summarize_transcript(transcript: str) -> str`. This is a prerequisite for registering it as a component tool.

---

## Tool Classification

### Workflows — Composite + Components (both registered as MCP tools)

| Composite Tool | Component Tools |
|---|---|
| `process_lease_deed` | `extract_contracts`, `build_rent_roll`, `analyze_clauses`, `build_clause_report` |
| `generate_credit_note` | `generate_credit_section` |
| `run_news_pipeline` | `fetch_news`, `classify_news`, `cluster_stories`, `generate_news_html` |
| `summarize_youtube_video` | `fetch_youtube_transcript`, `summarize_transcript` |
| `process_meeting_audio` | `transcribe_audio`, `summarize_meeting` |

### Simple Tools — Single MCP call, no decomposition

| Tool | What it does |
|---|---|
| `analyze_annual_report` | PDF → full ARA markdown |
| `generate_credit_one_pager` | PDF → credit risk markdown |
| `generate_image` | Prompt → PNG bytes |
| `search_youtube` | Query → video metadata list |

### Companion Tool — Standalone, part of meeting workflow

| Tool | What it does |
|---|---|
| `chat_with_meeting` | Context + question → follow-up answer |

**Total registered MCP tools: 23**
(5 composites + 14 components + 4 simple + 1 companion)

---

## Shared Utilities

Before writing any tool, create `tools/shared/backend_utils.py`. Every tool that needs these capabilities imports from here — never duplicates the logic.

```python
# tools/shared/backend_utils.py

import google.generativeai as genai
import json, re

def upload_pdf_to_gemini(pdf_bytes: bytes, display_name: str = "document.pdf"):
    """
    Upload a PDF to the Gemini Files API and return the file object.
    Used by: analyze_annual_report, generate_credit_one_pager,
             generate_credit_note, process_lease_deed.
    """
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(pdf_bytes)
        tmp_path = f.name
    try:
        file = genai.upload_file(path=tmp_path, display_name=display_name)
        return file
    finally:
        os.unlink(tmp_path)


def parse_llm_json(raw: str) -> list[dict]:
    """
    Extract and parse a JSON array from an LLM response string.
    Handles markdown code fences and trailing prose.
    Used by: extract_contracts, analyze_clauses (inside process_lease_deed).
    Replaces: parse_json_response (extractor.py) and _parse_clause_response (clause_analyzer.py).
    """
    cleaned = re.sub(r"```(?:json)?|```", "", raw).strip()
    match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if not match:
        raise ValueError(f"No JSON array found in LLM response: {raw[:200]}")
    return json.loads(match.group())
```

---

## Workflow 1: Lease Deed Processing

**File:** `tools/document/lease_deed.py`

### Component tools

```python
@mcp.tool()
def extract_contracts(pdf_bytes: bytes) -> list[dict]:
    """
    Extract structured contract data from a lease deed PDF.
    Returns a list of contract dicts with fields: tenant, premises,
    start_date, end_date, rent, escalation, security_deposit, etc.
    Use this before build_rent_roll, or standalone to inspect extracted data.
    """

@mcp.tool()
def build_rent_roll(contracts: list[dict]) -> bytes:
    """
    Build a 41-column rent roll Excel file from extracted contract data.
    Input must be the output of extract_contracts or a list matching that schema.
    Returns xlsx bytes.
    """

@mcp.tool()
def analyze_clauses(pdf_bytes: bytes) -> list[dict]:
    """
    Analyse critical clauses in a lease deed PDF.
    Returns a list of clause dicts with fields: clause_type, text,
    risk_category (high/medium/low), remarks.
    Use this before build_clause_report, or standalone to review clause risks.
    """

@mcp.tool()
def build_clause_report(clauses: list[dict]) -> bytes:
    """
    Build a formatted Word document from analysed lease clauses.
    Input must be the output of analyze_clauses or a list matching that schema.
    Returns docx bytes, with clauses grouped and colour-coded by risk category.
    """
```

### Composite tool

```python
@mcp.tool()
def process_lease_deed(pdf_bytes: bytes) -> dict:
    """
    Full end-to-end lease deed review. Extracts contracts, builds rent roll Excel,
    analyses critical clauses, and produces a clause report Word document.
    Returns: { "rent_roll_excel": bytes, "clause_report_docx": bytes }
    Use this for a complete one-shot review. Use component tools individually
    to run partial workflows or inspect intermediate outputs.
    """
    contracts = extract_contracts(pdf_bytes)
    excel     = build_rent_roll(contracts)
    clauses   = analyze_clauses(pdf_bytes)
    docx      = build_clause_report(clauses)
    return {"rent_roll_excel": excel, "clause_report_docx": docx}
```

**Note on output type:** Changed from `tuple[bytes, bytes]` to `dict` with named keys. Tuples are ambiguous to the orchestrator — it cannot tell which bytes is which. Named keys are self-documenting.

---

## Workflow 2: Credit Note Generation

**File:** `tools/document/credit_note.py`

### Component tool

```python
@mcp.tool()
def generate_credit_section(
    section_name: str,
    annual_report_bytes: bytes,
    rationale_bytes_list: list[bytes]
) -> str:
    """
    Generate one section of a credit note.

    Valid section names:
      "Company Profile", "Credit Rating", "ESG Profile", "Business Profile",
      "Key Risks & Mitigants", "Capital", "Asset Quality", "Earnings",
      "Management", "Liquidity"

    Source file routing is handled internally:
      - Company Profile, Liquidity  → Annual Report only
      - All other sections          → Rating Rationale PDFs only

    Use this to regenerate a single section without rerunning the full note.
    """
```

### Composite tool

```python
@mcp.tool()
def generate_credit_note(
    annual_report_bytes: bytes,
    rationale_bytes_list: list[bytes]
) -> dict[str, str]:
    """
    Generate a complete 10-section internal credit note.
    Sections: Company Profile, Credit Rating, ESG Profile, Business Profile,
    Key Risks & Mitigants, Capital, Asset Quality, Earnings, Management, Liquidity.
    Returns a dict mapping section name to generated text.
    All 10 sections are generated concurrently.
    """
    from concurrent.futures import ThreadPoolExecutor

    SECTIONS = [
        "Company Profile", "Credit Rating", "ESG Profile", "Business Profile",
        "Key Risks & Mitigants", "Capital", "Asset Quality",
        "Earnings", "Management", "Liquidity"
    ]

    def run_section(name):
        return name, generate_credit_section(name, annual_report_bytes, rationale_bytes_list)

    with ThreadPoolExecutor(max_workers=10) as executor:
        results = dict(executor.map(lambda s: run_section(s), SECTIONS))

    return results
```

**Note on concurrency:** The 10 sections are independent — there is no reason to run them sequentially. Using `ThreadPoolExecutor` here cuts wall-clock time from ~10× single-section latency to ~1× single-section latency (plus overhead). This is a direct fix to the known performance issue in the original design.

---

## Workflow 3: News Pipeline

**File:** `tools/market/news.py`

### Component tools

```python
@mcp.tool()
def fetch_news(category: str) -> list[dict]:
    """
    Fetch and deduplicate news articles from Google News RSS for a given category.
    Returns a list of article dicts with fields: title, url, source, published_at.

    Valid categories: "Real Estate", "Fixed Income", "Equity Markets",
    "Macro & Policy", "Credit & Banking", "Corporate", "Infrastructure"
    (full list defined in QUERY_GROUPS in market_brief.py)

    Use this standalone to inspect raw articles before running the full pipeline.
    """

@mcp.tool()
def classify_news(articles: list[dict]) -> list[dict]:
    """
    Classify a list of news articles by relevance using Gemini.
    Input: article list from fetch_news or matching schema.
    Returns only the articles classified as relevant.
    """

@mcp.tool()
def cluster_stories(articles: list[dict]) -> list[dict]:
    """
    Cluster similar news stories and generate a one-sentence summary per cluster.
    Input: relevant article list from classify_news or matching schema.
    Returns a list of cluster dicts with fields: summary, articles (list of sources).
    """

@mcp.tool()
def generate_news_html(clusters: list[dict]) -> str:
    """
    Render a formatted HTML news brief from clustered stories.
    Input: cluster list from cluster_stories or matching schema.
    Returns HTML string with bullet summaries and clickable source chips.
    """
```

### Composite tool

```python
@mcp.tool()
def run_news_pipeline(category: str) -> str:
    """
    Run the full news brief pipeline for a category.
    Steps: fetch → classify → cluster → generate HTML.
    Returns a rendered HTML brief ready for display.

    Valid categories: "Real Estate", "Fixed Income", "Equity Markets",
    "Macro & Policy", "Credit & Banking", "Corporate", "Infrastructure"

    Use component tools individually to inspect intermediate outputs
    or to feed custom article lists into a specific pipeline stage.
    """
    articles  = fetch_news(category)
    relevant  = classify_news(articles)
    clusters  = cluster_stories(relevant)
    return generate_news_html(clusters)
```

---

## Workflow 4: YouTube Video Summarisation

**File:** `tools/media/youtube.py`

### Component tools

```python
@mcp.tool()
def fetch_youtube_transcript(url: str) -> str:
    """
    Fetch and clean the transcript from a YouTube video URL.
    Returns plain text transcript.
    Raises ValueError if captions are unavailable (auto-generated or private video).
    Use this before summarize_transcript, or standalone to inspect transcript length
    or language before deciding whether to summarise.
    """

@mcp.tool()
def summarize_transcript(transcript: str) -> str:
    """
    Generate an investment-analyst-style summary from a video transcript.
    Input: plain text transcript from fetch_youtube_transcript or any source.
    Returns structured markdown summary covering key points, data cited,
    investment relevance, and notable quotes.
    """
```

### Composite tool

```python
@mcp.tool()
def summarize_youtube_video(url: str) -> str:
    """
    Fetch the transcript from a YouTube URL and generate an analyst-style summary.
    Returns structured markdown.
    Use search_youtube first to find relevant videos, then call this with the URL.
    Use component tools individually if you need the raw transcript or want to
    summarise a transcript from a non-YouTube source.
    """
    transcript = fetch_youtube_transcript(url)
    return summarize_transcript(transcript)
```

**Prerequisite:** The inline summarisation logic in `youtube_intelligence.py` must be extracted into `summarize_transcript()` before this workflow can be registered. This is the pre-build fix noted above.

---

## Workflow 5: Meeting Audio Processing

**File:** `tools/media/meeting.py`

### Component tools

```python
@mcp.tool()
def transcribe_audio(audio_bytes: bytes) -> str:
    """
    Upload an audio recording to Gemini Files API and return the transcript.
    Accepts WAV or MP3. Waits for the file to reach ACTIVE state before processing.
    Returns plain text transcript.
    Use this standalone if you only need the transcript, or before summarize_meeting
    if you want to inspect the transcript before generating a summary.
    """

@mcp.tool()
def summarize_meeting(transcript: str) -> dict:
    """
    Generate an institutional-grade meeting summary from a transcript.
    Strictly grounded — only what is explicitly stated in the transcript is reported.
    Returns: { "summary": str, "context": str }
    The context field is the same summary, formatted for use as input to chat_with_meeting.
    Use chat_with_meeting afterwards for follow-up Q&A against the meeting content.
    """
```

### Composite tool

```python
@mcp.tool()
def process_meeting_audio(audio_bytes: bytes) -> dict:
    """
    Transcribe an audio recording and generate a structured meeting summary.
    Accepts WAV or MP3.
    Returns: { "summary": str, "context": str }
    Pass the context value to chat_with_meeting for follow-up questions.
    """
    transcript = transcribe_audio(audio_bytes)
    return summarize_meeting(transcript)
```

### Companion tool

```python
@mcp.tool()
def chat_with_meeting(context: str, question: str, history: list[dict] = None) -> str:
    """
    Ask a follow-up question about a meeting that has already been summarised.
    context: the context value returned by process_meeting_audio or summarize_meeting.
    question: the question to answer.
    history: optional list of prior Q&A turns as [{"role": "user"|"assistant", "content": str}].
    Returns a grounded answer drawn strictly from the meeting content.
    """
```

**Note on companion tool design:** `chat_with_meeting` is registered as its own independent MCP tool. It is not a component of `process_meeting_audio`. The orchestrator calls `process_meeting_audio` first, extracts the `context` field from the result, and then calls `chat_with_meeting` with that context for any follow-up questions. The two tools are linked by data, not by workflow nesting.

---

## Simple Tools

These tools have no decomposable workflow. Each is a single MCP registration.

### `analyze_annual_report`

**File:** `tools/document/annual_report.py`

```python
@mcp.tool()
def analyze_annual_report(pdf_bytes: bytes) -> str:
    """
    Run a full Annual Report Analysis (ARA) against a company's annual report PDF.
    Produces an institutional-grade markdown document covering financials, governance,
    related-party transactions, auditor remarks, management commentary, and more.
    Returns full ARA markdown text.
    """
```

### `generate_credit_one_pager`

**File:** `tools/document/credit_one_pager.py`

```python
@mcp.tool()
def generate_credit_one_pager(pdf_bytes: bytes) -> str:
    """
    Generate a concise credit one-pager from an annual report PDF.
    Focused on debt serviceability, leverage, liquidity, and governance risks.
    Returns structured markdown suitable for quick credit screening.
    Use generate_credit_note for a full multi-section internal credit note.
    """
```

**Note:** `analyze_annual_report` and `generate_credit_one_pager` are structurally identical — both upload a PDF and call Gemini with a different prompt. They share `upload_pdf_to_gemini` from `backend_utils.py`. Do not duplicate the upload logic.

### `generate_image`

**File:** `tools/market/image.py`

```python
@mcp.tool()
def generate_image(
    prompt: str,
    template: str | None = None,
    ref_image_bytes: bytes | None = None,
    aspect_ratio: str = "16:9",
    resolution: str = "1K"
) -> dict:
    """
    Generate an image from a text prompt using Gemini's image generation model.
    template: optional ICICI Prudential brand template name.
              Valid values: "Bar Chart — ICICI Brand", "Line Chart — ICICI Brand",
              "Infographic — ICICI Brand", "Cover Slide — ICICI Brand"
    ref_image_bytes: optional reference image for edit-based generation.
    aspect_ratio: "16:9", "1:1", "9:16", "4:3"
    resolution: "1K", "2K"
    Returns: { "image_bytes": bytes, "caption_text": str | None }
    """
```

### `search_youtube`

**File:** `tools/media/youtube.py`

```python
@mcp.tool()
def search_youtube(query: str) -> list[dict]:
    """
    Search YouTube for videos matching a query.
    Returns up to 40 results, each with:
      title, url, channel, view_count, duration, thumbnail
    Use this before summarize_youtube_video to find the right video URL.
    """
```

---

## Module Structure

```
mcp_server/
│
├── server.py                      # Entry point. Configures API key, registers all tools.
│
├── config.py                      # API key initialisation and get_api_key().
│
├── tools/
│   ├── shared/
│   │   └── backend_utils.py       # upload_pdf_to_gemini, parse_llm_json
│   │
│   ├── document/
│   │   ├── lease_deed.py          # process_lease_deed + 4 components
│   │   ├── annual_report.py       # analyze_annual_report (simple)
│   │   ├── credit_one_pager.py    # generate_credit_one_pager (simple)
│   │   └── credit_note.py         # generate_credit_note + generate_credit_section
│   │
│   ├── market/
│   │   ├── news.py                # run_news_pipeline + 4 components
│   │   └── image.py               # generate_image (simple)
│   │
│   └── media/
│       ├── youtube.py             # search_youtube (simple) + summarize workflow
│       └── meeting.py             # process_meeting_audio + components + chat_with_meeting
│
└── backend/                       # Existing business logic — do not modify
    ├── extractor.py
    ├── gemini_extractor.py
    ├── clause_analyzer.py
    ├── clause_doc_builder.py
    ├── ara.py
    ├── credit_one_pager.py
    ├── credit_note_eval.py
    ├── market_brief.py
    ├── image_gen.py
    └── youtube_intelligence.py
```

The `backend/` directory is read-only from the MCP layer's perspective. All existing logic lives there untouched. The `tools/` layer imports from `backend/` and wraps it with MCP registration, input validation, and clean return types.

---

## Server Registration

```python
# server.py

import os
from mcp import MCPServer
from config import configure

# Document tools
from tools.document.lease_deed import (
    extract_contracts, build_rent_roll,
    analyze_clauses, build_clause_report,
    process_lease_deed
)
from tools.document.annual_report import analyze_annual_report
from tools.document.credit_one_pager import generate_credit_one_pager
from tools.document.credit_note import generate_credit_section, generate_credit_note

# Market tools
from tools.market.news import (
    fetch_news, classify_news,
    cluster_stories, generate_news_html,
    run_news_pipeline
)
from tools.market.image import generate_image

# Media tools
from tools.media.youtube import (
    fetch_youtube_transcript, summarize_transcript,
    summarize_youtube_video, search_youtube
)
from tools.media.meeting import (
    transcribe_audio, summarize_meeting,
    process_meeting_audio, chat_with_meeting
)

def main():
    configure(os.environ["GEMINI_API_KEY"])
    server = MCPServer(name="icici-pru-tools")
    server.run()

if __name__ == "__main__":
    main()
```

---

## Error Handling Conventions

Apply these consistently across all tool implementations.

```python
# Input validation — raise early, before any API call
if not pdf_bytes:
    raise ValueError("pdf_bytes cannot be empty.")

# Known-failure domains — catch and re-raise with context
try:
    file = upload_pdf_to_gemini(pdf_bytes)
except Exception as e:
    raise RuntimeError(f"Failed to upload PDF to Gemini: {e}") from e

# LLM JSON parse failures — always include raw output in error
try:
    contracts = parse_llm_json(raw_response)
except ValueError as e:
    raise ValueError(f"extract_contracts: failed to parse Gemini response. {e}") from e

# Transcript unavailable — specific, actionable message
if not transcript.strip():
    raise ValueError(
        f"No transcript available for {url}. "
        "The video may have captions disabled or be private."
    )
```

Every tool should fail loudly with a message that tells the orchestrator what went wrong and whether a retry makes sense. Silent failures (returning empty strings or empty lists) make orchestrator debugging nearly impossible.

---

## Implementation Sequence

Build in this order. Each phase is independently testable before moving to the next.

**Phase 1 — Foundation**
1. Create `config.py` with `configure()` and `get_api_key()`
2. Create `tools/shared/backend_utils.py` with `upload_pdf_to_gemini` and `parse_llm_json`
3. Create `server.py` skeleton that starts without errors

**Phase 2 — Simple tools first**
4. `analyze_annual_report`
5. `generate_credit_one_pager`
6. `search_youtube`
7. `generate_image`

These are the lowest-risk registrations. They validate the server setup and the shared utility pattern before you touch workflows.

**Phase 3 — Workflows, shortest first**
8. `summarize_youtube_video` (2 components — simplest workflow)
9. `process_meeting_audio` + `chat_with_meeting` (2 components + companion)
10. `generate_credit_note` + `generate_credit_section` (1 component, but concurrent)
11. `run_news_pipeline` (4 components)
12. `process_lease_deed` (4 components — most complex)

**Phase 4 — Integration test**
13. Run the orchestrator against all 23 tools
14. Verify composite tools produce identical output to their pre-MCP equivalents
15. Verify component tools can be called independently with correct partial outputs

---

## Decision Log

| Decision | Rationale |
|---|---|
| Option B (both levels exposed) | Orchestrator needs ability to call partial workflows without rerunning full pipelines |
| `api_key` moved to config | Keys should not flow through orchestrator context on every call |
| `generate_credit_note` returns `dict[str, str]` | Named keys prevent ambiguity; orchestrator can join sections if needed |
| 10 credit sections run concurrently | Sections are independent; sequential execution is ~10× slower for no reason |
| Composites call components as Python functions | No protocol overhead; components remain individually testable |
| `backend/` directory is read-only | Existing Streamlit UI depends on it; changes there break the UI layer |
| `chat_with_meeting` is a companion, not a component | It is not called by `process_meeting_audio`; it is called after, with the context output |
| `process_lease_deed` returns a dict not a tuple | Named keys (`rent_roll_excel`, `clause_report_docx`) are self-documenting to the orchestrator |
# Agentic Architecture — Tool Design Summary

## Core Principle

A **tool** = a capability the agent can choose to invoke.  
An **implementation step** = internal detail the tool handles itself.

The agent should think:  
> "The user has a lease deed — I'll call `process_lease_deed`."

Not:  
> "I'll call `extract_contracts`, then `build_excel`, then `analyze_clauses`, then `build_docx`."

The sub-steps are plumbing. Tools are capabilities.

---

## The 9 Tools

### 1. `process_lease_deed`
**What it does:** Takes a lease deed PDF end-to-end — extracts all contracts, builds the rent roll Excel, and runs the critical clause analysis, returning both output artifacts.

**Agent use case:** User uploads a lease agreement and wants a full review.

**Inputs:**
- `pdf_bytes: bytes` — raw PDF content
- `api_key: str`

**Outputs:**
- `rent_roll_excel: bytes` — 41-column Excel file
- `clause_report_docx: bytes` — formatted Word doc with risk-categorized clauses

**Internal steps (not exposed):**
1. `extract_with_gemini(pdf_bytes)` → `list[dict]` (gemini_extractor.py)
2. `build_excel(contracts)` → xlsx bytes (extractor.py)
3. `analyze_clauses_gemini(pdf_bytes)` → `list[dict]` (clause_analyzer.py)
4. `build_clause_report(clauses)` → docx bytes (clause_doc_builder.py)

---

### 2. `analyze_annual_report`
**What it does:** Runs the full ARA (Annual Report Analysis) prompt against a PDF — produces an institutional-grade analysis covering financials, governance, RPTs, auditor remarks, and more.

**Agent use case:** User uploads an annual report and wants a CIO-ready ARA document.

**Inputs:**
- `pdf_bytes: bytes`
- `api_key: str`

**Output:**
- `analysis: str` — full markdown ARA report

**Internal steps:**
1. Upload PDF to Gemini Files API
2. Call Gemini with `ARA_PROMPT` (ara.py)
3. Return response text

---

### 3. `generate_credit_one_pager`
**What it does:** Runs the credit one-pager analysis prompt against an annual report — focused on debt serviceability, leverage, liquidity, and governance risks.

**Agent use case:** User wants a quick credit risk view of a company from its annual report.

**Inputs:**
- `pdf_bytes: bytes`
- `api_key: str`

**Output:**
- `one_pager: str` — structured credit analysis in markdown

**Internal steps:**
1. Upload PDF to Gemini Files API
2. Call Gemini with `CREDIT_ONE_PAGER_PROMPT` (credit_one_pager.py)
3. Return response text

---

### 4. `generate_credit_note`
**What it does:** Produces a full multi-section credit note (10 sections) from an annual report + one or more rating rationale PDFs. Sections: Company Profile, Credit Rating, ESG, Business Profile, Key Risks & Mitigants, Capital, Asset Quality, Earnings, Management, Liquidity.

**Agent use case:** User has a portfolio company and wants a complete internal credit note.

**Inputs:**
- `annual_report_bytes: bytes`
- `rationale_bytes_list: list[bytes]` — one or more rating rationale PDFs
- `api_key: str`

**Output:**
- `credit_note: dict[str, str]` — section name → generated text, or a single assembled string

**Internal steps:**
1. Upload annual report to Gemini Files API
2. Upload each rationale to Gemini Files API
3. Run each section prompt sequentially against the appropriate files (credit_note_eval.py)
4. Return assembled output

**Sections and their source:**
| Section | Source files used |
|---|---|
| Company Profile | Annual Report only |
| Credit Rating | Rationales only |
| ESG Profile | Rationales only |
| Business Profile | Rationales only |
| Key Risks & Mitigants | Rationales only |
| Capital | Rationales only |
| Asset Quality | Rationales only |
| Earnings | Rationales only |
| Management | Rationales only |
| Liquidity | Annual Report only |

---

### 5. `run_news_pipeline`
**What it does:** Runs the full news brief pipeline — fetches RSS articles from Google News for a given category, classifies relevance, clusters similar stories, and generates a formatted HTML brief.

**Agent use case:** User wants a morning market brief for a specific sector.

**Inputs:**
- `category: str` — e.g. `"Real Estate"` (must match a key in `QUERY_GROUPS`)
- `api_key: str`

**Output:**
- `html_brief: str` — rendered HTML with bullets and clickable source chips

**Internal steps:**
1. `fetch_news(queries)` → raw article list (market_brief.py)
2. Decode Google News URLs
3. Deduplicate by title
4. `classify_news(news_list)` → relevance labels (market_brief.py)
5. Filter to relevant articles
6. Cluster similar stories via Gemini
7. Generate one-sentence summaries per cluster via Gemini
8. `generate_html(final_output)` → HTML string (market_brief.py)

---

### 6. `generate_image`
**What it does:** Generates an image from a text prompt using Gemini's image generation model. Optionally applies an ICICI Prudential brand template, accepts a reference image for editing, or ingests data (Excel/CSV) for chart generation.

**Agent use case:** User wants a branded bar chart, infographic, or custom visual.

**Inputs:**
- `prompt: str`
- `template: str | None` — optional ICICI brand template name (e.g. `"📊 Bar Chart — ICICI Brand"`)
- `ref_image_bytes: bytes | None` — optional reference image to edit
- `model: str` — defaults to `"gemini-3.1-flash-image-preview"`
- `aspect_ratio: str` — e.g. `"16:9"`
- `resolution: str` — e.g. `"1K"`

**Output:**
- `image_bytes: bytes` — PNG image
- `caption_text: str | None` — any text the model returned alongside the image

**Internal steps:**
1. Build prompt string (prepend template text if selected) (image_gen.py)
2. Call `generate_image()` via Gemini multimodal API
3. Extract image bytes from response parts

---

### 7. `search_youtube`
**What it does:** Searches YouTube for videos matching a query and returns metadata for the top results.

**Agent use case:** User wants to find investment-relevant videos on a topic before summarizing one.

**Inputs:**
- `query: str`

**Output:**
- `videos: list[dict]` — each with `title`, `url`, `channel`, `view_count`, `duration`, `thumbnail`

**Internal steps:**
1. Uses `yt_dlp` to run `ytsearch40:{query}` (youtube_intelligence.py)
2. Returns structured metadata

---

### 8. `summarize_youtube_video`
**What it does:** Fetches the transcript from a YouTube URL and generates an investment-analyst-style summary.

**Agent use case:** User found a video (via `search_youtube`) and wants a structured summary before watching.

**Inputs:**
- `url: str` — YouTube video URL
- `api_key: str`

**Output:**
- `summary: str` — structured markdown summary

**Internal steps:**
1. Fetch captions via `pytubefix` (youtube_intelligence.py inline logic)
2. Clean transcript text
3. Call Gemini with equity-analyst summary prompt
4. Return response text

> **Note:** This logic is currently inline in `youtube_intelligence.py` and needs to be extracted into a named function.

---

### 9. `process_meeting_audio`
**What it does:** Uploads an audio recording, transcribes it, and produces an institutional-grade discussion summary grounded strictly in what was said.

**Agent use case:** User recorded a management call or internal meeting and wants a faithful summary.

**Inputs:**
- `audio_bytes: bytes` — WAV or MP3
- `api_key: str`

**Output:**
- `summary: str` — structured meeting summary
- `context: str` — the same summary, kept for follow-up Q&A

**Internal steps:**
1. Upload audio to Gemini Files API, wait for ACTIVE state (meeting_recorder.py)
2. Call Gemini with strict grounding prompt
3. Return response text

> **Optional companion tool:** `chat_with_meeting(context: str, history: list[dict], question: str) → str` — for follow-up Q&A after the summary is generated.

---

## What Is NOT a Tool

These are internal helpers that live inside tools — the agent never calls them directly:

| Function | Lives in | Used by |
|---|---|---|
| `parse_json_response` | extractor.py | `process_lease_deed` internals |
| `_parse_clause_response` | clause_analyzer.py | `process_lease_deed` internals |
| `enrich_contract` | extractor.py | `build_excel` internals |
| `_remaining_yrs` | extractor.py | `enrich_contract` internals |
| `_sanitize`, `_hr` | clause_doc_builder.py | `build_clause_report` internals |
| `decode_url`, `extract_source` | market_brief.py | `run_news_pipeline` internals |
| `get_client`, `b64_to_pil`, `pil_to_b64`, `now_ts` | image_gen.py | `generate_image` internals |
| `add_msg`, `active_b64`, `push_gallery` | image_gen.py | Streamlit UI only — not relevant in agent context |
| `_reset` | lease_deed.py | Streamlit UI only |

---

## Architecture Overview

```
                        ┌─────────────────────────────────┐
                        │           ORCHESTRATOR           │
                        │    (LLM with tool definitions)   │
                        └──────────────┬──────────────────┘
                                       │
          ┌────────────────────────────┼───────────────────────────┐
          │                            │                           │
          ▼                            ▼                           ▼
  ┌───────────────┐          ┌─────────────────┐         ┌──────────────────┐
  │ DOCUMENT      │          │ MARKET          │         │ MEDIA            │
  │ TOOLS         │          │ TOOLS           │         │ TOOLS            │
  │               │          │                 │         │                  │
  │ process_      │          │ run_news_       │         │ search_youtube   │
  │ lease_deed    │          │ pipeline        │         │                  │
  │               │          │                 │         │ summarize_       │
  │ analyze_      │          │ generate_image  │         │ youtube_video    │
  │ annual_report │          │                 │         │                  │
  │               │          │                 │         │ process_         │
  │ generate_     │          │                 │         │ meeting_audio    │
  │ credit_note   │          │                 │         │                  │
  │               │          │                 │         │ chat_with_       │
  │ generate_     │          │                 │         │ meeting          │
  │ credit_one_   │          │                 │         │                  │
  │ pager         │          │                 │         │                  │
  └───────────────┘          └─────────────────┘         └──────────────────┘
```

---

## Consolidation Opportunities

**1. Shared `upload_pdf_to_gemini` utility**  
`analyze_annual_report`, `generate_credit_note`, `generate_credit_one_pager`, and `process_lease_deed` all upload PDFs to the Gemini Files API. Extract this into one shared function in a `backend_utils.py` module.

**2. Unified JSON parser**  
`parse_json_response` (extractor.py) and `_parse_clause_response` (clause_analyzer.py) are nearly identical. One shared `parse_llm_json(raw: str) -> list[dict]` in `backend_utils.py` covers both.

**3. `generate_credit_note` section prompts**  
The 10 section prompts in `credit_note_eval.py` should be a `SECTION_PROMPTS: dict[str, str]` constant so the tool loops over them rather than having 10 separate `generate_content` calls duplicated in UI code.

---

## Summary Count

| Category | Tools |
|---|---|
| Document / Credit analysis | 4 |
| Market / Image | 2 |
| Media / Audio / Video | 3 |
| **Total** | **9** |

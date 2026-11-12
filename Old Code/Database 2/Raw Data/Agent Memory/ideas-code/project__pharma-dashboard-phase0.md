---
name: Pharma Dashboard Phase 0
description: Steps 1-3 of 31-company Indian pharma analyst dashboard built at ICICI Prudential
type: project
---

Repo: /Users/aryamanchandak/Documents/ICICI Prudential/Code/Agents/Pharma Dashboard
Ideas file: ideas.md (the execution guide — always read in full before acting)
Venv: .venv (Python 3.11.15, use absolute path .venv/bin/python)
Package manager: uv (at /opt/homebrew/bin/uv)

## Status (as of June 13 2026)
Steps 1–3 complete. Step 4 (extraction) blocked pending user providing a PDF and setting GEMINI_API_KEY.

## What was built
- pharma_dashboard/config.py — all constants (model ids, pricing, paths, canonical taxonomies)
- pharma_dashboard/llm/usage.py — @log_tokens(stage=...) decorator, JSONL ledger
- pharma_dashboard/db/schema.py — SQLite DDL for all 9 tables; init_db() function
- pharma_dashboard/db/models.py — Pydantic v2 models for extraction output + canonicalise helpers
- tools/usage_report.py — JSONL → roll-up print + api_usage SQLite loader
- tools/verify_gate.py — real Gemini call → assert non-zero input_tokens → PASS/FAIL
- .env with GEMINI_API_KEY= placeholder
- data/pharma.db already initialised with all tables

## Verification gate (Step 1)
NOT yet passed. User must:
1. Add real API key: edit .env → GEMINI_API_KEY=<key>
2. Run: python tools/verify_gate.py
3. Gate passes when output shows PASS and input_tokens > 0.

## Key design decisions
- Extraction model: gemini-3.1-pro (config.EXTRACTION_MODEL) — 2M context, fits whole AR PDF
- Fast model: gemini-3.5-flash (config.FAST_MODEL)
- All paths driven from config.py (TOKEN_LEDGER, DB_PATH, PDF_DIR)
- Extractor and API are separate processes sharing only data/pharma.db
- No multi-agent framework, no vector DB, no MCP — SQLite + FastAPI + JS only
- Every Gemini call MUST go through @log_tokens. No exceptions.
- Store reported label AND canonical mapping everywhere.
- source_ref required on every fact row (Pydantic validator enforces this).
- unmapped_labels table for labels that can't be canonicalised (never silently bucket).

## SDK surface (google-genai 2.8.0)
- response.usage_metadata (snake_case), response.model_version
- usage_metadata fields: prompt_token_count, candidates_token_count, cached_content_token_count, thoughts_token_count
- client.caches.create(model=..., config=CreateCachedContentConfig(...))
- client.files.upload(file=path_or_io, config=UploadFileConfig(...))

## Pricing in config (verified June 2026, confirm before production run)
- gemini-3.5-flash: input $1.50/1M, cached $0.375/1M, output $9.00/1M
- gemini-3.1-pro:   input $2.00/1M (≤200K ctx), cached $0.50/1M, output $12.00/1M
  (doubles to $4/$18 for >200K context; confirm at ai.google.dev/gemini-api/docs/pricing)

## Next step (Step 4)
One company end-to-end extraction. Needs: PDF in data/pdfs/, GEMINI_API_KEY set, gate passed.
Build: pharma_dashboard/extractor.py — upload PDF, create cache, run 3 calls (ownership/geo/segment), write to DB, delete cache.

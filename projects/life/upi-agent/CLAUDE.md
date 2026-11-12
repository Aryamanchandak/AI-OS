# UPI Agent — Codebase Guide

Local agent that reads UPI payment SMS from your Mac, enriches with calendar context,
stores to SQLite, and serves a dashboard at `http://127.0.0.1:7070`.

## Layout

```
upi-agent/
├── agent.py          ← ingestion: reads chat.db, calls parser, upserts to data.db
├── dashboard.py      ← FastAPI server; mount at 127.0.0.1:7070; serves /feed /triage /tax
├── requirements.txt  ← fastapi, uvicorn, pydantic, pytest
├── README.md
│
├── core/             ← unified agentic + tax layer (package: `from core.X import Y`)
│   ├── config.py     ← ALL thresholds + category list + merchant patterns (tune here)
│   ├── schema/
│   │   ├── db.py     ← connection helper; runs migrations lazily on first connect
│   │   └── migrate.py ← merged idempotent schema migrations (brain + tax tables)
│   ├── parsers/
│   │   ├── sms.py    ← stateless UPI SMS regex parser
│   │   └── sbi_excel.py ← SBI TSV-disguised-as-xls statement parser
│   ├── ingest/
│   │   └── excel.py  ← parse → dedup on ref_no → upsert → reactor hook
│   ├── classify/
│   │   ├── rules.py  ← shared upsert_rule() writer into category_rules
│   │   ├── auto.py   ← auto-categorisation ensemble (VPA history + merchant patterns)
│   │   └── manual.py ← Classifier protocol: RuleBased + LocalLLM implementations
│   ├── detect/
│   │   ├── anomaly.py   ← four detectors: new_counterparty, zscore, odd_hour, velocity
│   │   ├── goals.py     ← avoid_merchant / budget_cap / frequency_cap tracking
│   │   └── recurring.py ← mines history for weekly/fortnightly/monthly clusters
│   ├── orchestration/
│   │   └── reactor.py   ← orchestrates classifier + anomaly + goals on new payments
│   ├── output/
│   │   ├── narrator.py  ← weekly spend story: markdown + optional OpenAI rephrase
│   │   └── excel_export.py ← annotated .xlsx with formula-driven Summary sheet
│   ├── notify/
│   │   └── macos.py     ← macOS osascript notifications for severity ≥ 2 events
│   ├── web/
│   │   ├── routes.py    ← FastAPI router mounted at /tax/*
│   │   └── templates.py ← inline HTML for /tax and /tax/settings
│   ├── cli/
│   │   ├── main.py      ← CLI subcommands implementation
│   │   └── __main__.py  ← enables `python -m core.cli`
│   ├── utils/
│   │   ├── money.py     ← canonical _money() formatter (handles negatives)
│   │   └── tokens.py    ← name_tokens() + NAME_STOP_TOKENS
│   └── deep-dive/    ← per-module documentation
│       ├── brain/    ← docs for classify, detect, orchestration, output, notify
│       └── tax/      ← docs for parsers, ingest, web
│
├── tests/            ← pytest suite (74 tests total)
│   ├── conftest.py   ← shared seeded_db fixture (~60 synthetic payments)
│   ├── test_parser.py
│   ├── test_classifier.py
│   ├── test_anomaly.py
│   ├── test_goals.py
│   ├── test_narrator.py
│   ├── test_reactor.py
│   ├── test_tax.py
│   └── fixtures/
│       └── SBI_Transactions_2.xls  ← required for test_tax.py
│
└── launchd/          ← macOS launchd plists for automated scheduling
    └── com.you.upi-agent-story.plist  ← weekly story every Sunday 20:00
```

## Where new files go

| What you're building | Where it lives |
|---|---|
| New SMS bank format | `core/parsers/sms.py` — add pattern to `BANK_SENDER_MAP` |
| New anomaly detector | `core/detect/anomaly.py` — implement `AnomalyDetector` protocol |
| New goal kind | `core/detect/goals.py` + `core/cli/main.py` |
| New category / merchant pattern | `core/config.py` — `CATEGORIES` / `MERCHANT_PATTERNS` |
| Excel parser for a new bank | `core/parsers/<bank>_excel.py`, dispatch in `core/ingest/excel.py` |
| New dashboard route | `dashboard.py` (base routes) or `core/web/routes.py` (tax routes) |
| New test | `tests/test_<module>.py` using `seeded_db` fixture from conftest |
| launchd automation | `launchd/<plist>` + instructions in README |

## How to run

```bash
# One-time setup
uv venv && uv pip install -r requirements.txt

# Daily ingestion
python3 agent.py

# Dashboard
python3 dashboard.py   # → http://127.0.0.1:7070

# Core CLI
python -m core.cli react          # process unprocessed payments
python -m core.cli story weekly   # generate this week's markdown story
python -m core.cli stats          # event counts, active goals, queue size

# Tests (run from project root)
pytest tests/ -v
```

## Key constraints

- `agent.py` opens `chat.db` **read-only** — never modifies Messages.
- Dashboard binds to `127.0.0.1` only — never `0.0.0.0`.
- No external API calls anywhere except the optional OpenAI narrator rephrase
  pass (`USE_LLM_NARRATOR = True` in `core/config.py`).
- All thresholds (z-score cutoff, anomaly amounts, confidence threshold, etc.)
  live in `core/config.py` — never bury magic numbers in module code.
- Dedup is enforced at SQL level via `INSERT OR IGNORE` on `dedup_key` —
  repeat runs are always safe.
- Tax dedup is on `ref_no` — re-uploading the same SBI file is idempotent.
- All DB access goes through `core.schema.db.connect()` — never call
  `sqlite3.connect()` directly in new code.

## Data files (not in repo)

```
~/.upi-agent/
├── data.db        ← your ledger + brain events (SQLite)
├── state.json     ← last-seen message ROWID (delete to re-ingest all)
└── stories/
    └── 2026-Www.md
```

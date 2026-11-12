# UPI Agent

A local agent that reads UPI payment SMS forwarded to your Mac, enriches each
payment with calendar context, and serves a personal ledger dashboard. Entirely
offline — no data leaves your machine.

## Architecture

```
 iPhone SMS ──(Text Message Forwarding)──▶ Mac Messages app
                                                  │
                                                  ▼
                                       ~/Library/Messages/chat.db  (SQLite)
                                                  │
                            ┌────── agent.py ─────┤
                            │                     ▼
                            │        core/parsers/sms.py  (regex)
                            │                     │
                            │         macOS Calendar (via osascript)
                            │                     │
                            ▼                     ▼
                  ~/.upi-agent/data.db  (your ledger, local SQLite)
                            │
                            ▼
                      dashboard.py  →  http://127.0.0.1:7070
```

- **`core/parsers/sms.py`** — stateless UPI SMS parser. Handles HDFC/SBI/ICICI/Axis/Kotak/
  Paytm etc. Pre-filters non-UPI messages (OTPs, promos, balance alerts).
- **`agent.py`** — reads new messages from `chat.db` (read-only), parses them,
  queries Calendar.app for overlapping events, upserts into local SQLite.
  Idempotent: re-running doesn't duplicate rows.
- **`dashboard.py`** — FastAPI server bound to `127.0.0.1` only. Renders the
  ledger HTML, exposes JSON API for queries and category edits.

## Setup (one-time)

### 1. Enable SMS forwarding iPhone → Mac

On iPhone: **Settings → Messages → Text Message Forwarding** → toggle on your
Mac. You'll need to enter a code shown on the Mac. After this, every SMS your
iPhone receives also lands in Messages.app on the Mac, which writes to
`~/Library/Messages/chat.db`.

### 2. Grant Full Disk Access to your Terminal / Python

`chat.db` is protected. Open **System Settings → Privacy & Security → Full
Disk Access** and add Terminal (or iTerm, whatever you use to run Python).
Restart the terminal after granting.

### 3. Install deps

```bash
cd upi-agent
uv venv
uv pip install -r requirements.txt
```

### 4. First run

```bash
python3 agent.py
```

The first time it runs, macOS will prompt for Calendar access (used for
enrichment via `osascript`). Allow it. If you skip this, payments are still
stored — just without calendar context.

### 5. Open the dashboard

```bash
python3 dashboard.py
# then open http://127.0.0.1:7070
```

## Daily trigger

To run the ingestion once a day automatically, use launchd. Create
`~/Library/LaunchAgents/com.you.upi-agent.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.you.upi-agent</string>
  <key>ProgramArguments</key>
  <array>
    <string>/absolute/path/to/upi-agent/.venv/bin/python3</string>
    <string>/absolute/path/to/upi-agent/agent.py</string>
  </array>
  <key>WorkingDirectory</key>
  <string>/absolute/path/to/upi-agent</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>23</integer>
    <key>Minute</key><integer>30</integer>
  </dict>
  <key>StandardOutPath</key><string>/tmp/upi-agent.log</string>
  <key>StandardErrorPath</key><string>/tmp/upi-agent.err</string>
</dict>
</plist>
```

Then:

```bash
launchctl load ~/Library/LaunchAgents/com.you.upi-agent.plist
```

Runs every day at 23:30 local time. Logs go to `/tmp/upi-agent.log`.

## Security notes

- **`chat.db` is opened read-only** — agent cannot modify your messages.
- **Local SQLite only** — your ledger sits at `~/.upi-agent/data.db`. Back it
  up yourself if you care.
- **Dashboard binds to `127.0.0.1`** — not reachable from the network. If you
  want to view from another device, use an SSH tunnel, not `0.0.0.0`.
- **No external API calls** — nothing is sent to any cloud service. If you
  later want LLM-powered enrichment for edge cases, point at a local Ollama.

## Agentic capabilities (core/)

On top of the base ingest + dashboard, the `core/` package adds agentic
capabilities. All run locally; everything writes to a single `agent_events`
table that surfaces in the dashboard's `/feed` view.

### Capabilities

**Auto-categorization.** Every new payment runs through an ensemble of
classifiers — VPA history, calendar event keywords, hand-curated merchant
patterns (`swiggy`, `irctc`, `netflix`, etc.), and amount/time heuristics.
When confidence clears the threshold, the payment is tagged. When you
correct a category in the `/triage` view, the correction is recorded as
a learned rule for that VPA + name tokens. Future payments to the same
counterparty inherit your decision.

**Anomaly detection.** Four detectors run on every new payment:
- *new_counterparty* — first payment to a never-seen VPA above ₹3,000.
- *zscore* — payment ≥ 2.5σ above your typical spend in its category.
- *odd_hour* — payment outside your usual active hours (5–95 percentile).
- *velocity* — 5+ debits in 10 minutes, possible compromise.

Each finding includes a structured explanation; the `/feed` shows the
unified timeline.

**Goals.** Three kinds, declared via CLI:
```bash
python -m core.cli goal add --kind avoid_merchant --pattern swiggy \
    --scope month --description "No Swiggy this month"
python -m core.cli goal add --kind budget_cap --category Food \
    --amount 15000 --scope month
python -m core.cli goal add --kind frequency_cap --pattern zomato \
    --max-per-period 2 --scope week
```
Warnings fire at 80% of a budget cap; violations at 100%. Each fires
exactly once per (goal, period) thanks to dedup keys.

**Recurring detection.** Mines payment history for stable weekly,
fortnightly, and monthly clusters (consistent amount, consistent cadence).
Surfaces them as `recurring_detected` events — useful for subscription hygiene.

**Weekly narrator.** Sunday 20:00, a markdown story is written to
`~/.upi-agent/stories/YYYY-Www.md`. Includes weekly totals, category
breakdown with deltas vs prior week, top merchants, calendar correlations,
goal status, and an attention queue. An optional OpenAI rephrase pass can
soften the opening paragraph if you set `USE_LLM_NARRATOR = True` in
`core/config.py`.

**Excel ingestion (SBI).** Upload SBI statement exports via the `/tax` route.
Dedupes on `ref_no` — re-uploading the same file is idempotent. Exports an
annotated `.xlsx` with a formula-driven Summary sheet for your CA.

### CLI

```bash
python -m core.cli migrate              # apply schema (auto-runs on first use)
python -m core.cli react                # process all unprocessed payments
python -m core.cli react --payment-id N
python -m core.cli goal add ...
python -m core.cli goal list
python -m core.cli goal pause <id>
python -m core.cli goal end <id>
python -m core.cli goal check           # refresh all goal status caches
python -m core.cli story weekly         # generate this week's story
python -m core.cli story weekly --week 2026-W17
python -m core.cli notify               # show macOS notifs for severe events
python -m core.cli stats                # event counts, active goals, etc.
```

### Dashboard additions

- `/` — the existing ledger
- `/feed` — unified scrolling timeline of events, filterable by kind
- `/triage` — uncategorized + low-confidence payments queued for review
- `/tax` — upload SBI Excel, classify, export for CA

New API endpoints: `/api/events`, `/api/events/{id}/ack`, `/api/goals`
(GET/POST/DELETE), `/api/story/weekly`, `/api/triage`, `/api/recurring`.

### Scheduling the weekly story

A launchd plist (`launchd/com.you.upi-agent-story.plist`) fires every Sunday
at 20:00. The reactor itself runs as part of every ingestion in `agent.py`,
so events stay fresh without a separate cron.

```bash
cp launchd/com.you.upi-agent-story.plist ~/Library/LaunchAgents/
# edit absolute paths inside the plist
launchctl load ~/Library/LaunchAgents/com.you.upi-agent-story.plist
```

### Tuning

All thresholds live in `core/config.py`: confidence threshold, z-score
cutoffs, anomaly amounts, goal warning percentage, recurring cadence
tolerance, etc. Each constant has a comment explaining what it does.

### Optional: OpenAI narrator

```bash
uv pip install openai
export OPENAI_API_KEY=sk-...
# In core/config.py:
USE_LLM_NARRATOR = True
```

The rephrase only touches the opening paragraph — numbers and goal status are
computed deterministically. Failures fall back silently to deterministic text.

### Tests

```bash
pytest tests/ -v
```

74 tests covering the parser, classifier ensemble, all four anomaly detectors,
recurring detection, all three goal kinds with state transitions and dedup,
the reactor's idempotency guarantees, the narrator, and Excel ingestion.
The SBI Excel tests require `tests/fixtures/SBI_Transactions_2.xls` to be present.

## Files in your home after setup

```
~/.upi-agent/
├── data.db        # your ledger + agent events (SQLite)
├── state.json     # "last seen message ROWID" — safe to delete to re-ingest
└── stories/
    └── 2026-Www.md   # weekly markdown stories
```

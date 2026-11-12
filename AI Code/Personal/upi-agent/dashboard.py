"""
Local dashboard for the UPI agent.

Run:
    python3 dashboard.py
    # then open http://127.0.0.1:7070 in your browser

Binds only to 127.0.0.1 — not accessible from the network. All data stays
on your Mac. Reads from ~/.upi-agent/data.db (populated by agent.py).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
import uvicorn


DB_PATH = Path.home() / ".upi-agent" / "data.db"

app = FastAPI(title="UPI Agent")


def db() -> sqlite3.Connection:
    if not DB_PATH.exists():
        raise HTTPException(500, f"No data yet. Run `python3 agent.py` first. ({DB_PATH})")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# --- API ---------------------------------------------------------------------

@app.get("/api/summary")
def summary(days: int = 30) -> dict:
    """Top-line numbers for the current window."""
    since = (datetime.now() - timedelta(days=days)).isoformat()
    with db() as conn:
        rows = conn.execute(
            """
            SELECT
              SUM(CASE WHEN direction='debit'  THEN amount ELSE 0 END) AS spent,
              SUM(CASE WHEN direction='credit' THEN amount ELSE 0 END) AS received,
              COUNT(*) AS txns,
              COUNT(DISTINCT COALESCE(counterparty_vpa, counterparty_name)) AS uniques
            FROM payments
            WHERE occurred_at >= ?
            """,
            (since,),
        ).fetchone()
    return {
        "spent": rows["spent"] or 0,
        "received": rows["received"] or 0,
        "net": (rows["received"] or 0) - (rows["spent"] or 0),
        "txns": rows["txns"] or 0,
        "uniques": rows["uniques"] or 0,
        "window_days": days,
    }


@app.get("/api/payments")
def payments(days: int = 30, limit: int = 500) -> list[dict]:
    """All payments in the window, newest first."""
    since = (datetime.now() - timedelta(days=days)).isoformat()
    with db() as conn:
        rows = conn.execute(
            """
            SELECT id, occurred_at, amount, direction, bank,
                   counterparty_vpa, counterparty_name, category, note,
                   calendar_events, confidence
            FROM payments
            WHERE occurred_at >= ?
            ORDER BY occurred_at DESC
            LIMIT ?
            """,
            (since, limit),
        ).fetchall()
    result = []
    for r in rows:
        row = dict(r)
        if row["calendar_events"]:
            row["calendar_events"] = json.loads(row["calendar_events"])
        else:
            row["calendar_events"] = []
        result.append(row)
    return result


@app.get("/api/daily_spend")
def daily_spend(days: int = 30) -> list[dict]:
    """Aggregated daily debit total for charting."""
    since = (datetime.now() - timedelta(days=days)).isoformat()
    with db() as conn:
        rows = conn.execute(
            """
            SELECT substr(occurred_at, 1, 10) AS day,
                   SUM(amount) AS total
            FROM payments
            WHERE direction='debit' AND occurred_at >= ?
            GROUP BY day
            ORDER BY day ASC
            """,
            (since,),
        ).fetchall()
    return [{"day": r["day"], "total": r["total"] or 0} for r in rows]


@app.get("/api/top_recipients")
def top_recipients(days: int = 30, limit: int = 10) -> list[dict]:
    since = (datetime.now() - timedelta(days=days)).isoformat()
    with db() as conn:
        rows = conn.execute(
            """
            SELECT COALESCE(counterparty_vpa, counterparty_name, '?') AS who,
                   COUNT(*) AS txns,
                   SUM(amount) AS total
            FROM payments
            WHERE direction='debit' AND occurred_at >= ?
            GROUP BY who
            ORDER BY total DESC
            LIMIT ?
            """,
            (since, limit),
        ).fetchall()
    return [dict(r) for r in rows]


class CategoryUpdate(BaseModel):
    category: Optional[str] = None
    note: Optional[str] = None


@app.post("/api/payments/{payment_id}")
def update_payment(payment_id: int, update: CategoryUpdate) -> dict:
    """Set a category and/or note on a payment.

    When the user sets a category here, we route through the brain's
    learning loop so future payments to the same VPA / name tokens
    benefit from the correction. The brain marks category_source = 'user'
    so the agent never overwrites it.
    """
    with db() as conn:
        if update.category is not None:
            try:
                from core.classify.auto import record_user_categorization
                record_user_categorization(payment_id, update.category, conn)
            except Exception:
                # If brain isn't available, fall back to plain set so the
                # dashboard still works.
                conn.execute(
                    "UPDATE payments SET category = ? WHERE id = ?",
                    (update.category, payment_id),
                )
        if update.note is not None:
            conn.execute(
                "UPDATE payments SET note = ? WHERE id = ?",
                (update.note, payment_id),
            )
        conn.commit()
    return {"ok": True}


# --- Brain layer endpoints ---------------------------------------------------
#
# These read from the brain-owned tables (agent_events, goals,
# category_rules, recurring_payments). Brain modules are imported lazily
# inside each handler so the dashboard still serves the base ledger views
# even if the brain package is missing or broken.

@app.get("/api/events")
def list_events(
    days: int = 30,
    kinds: Optional[str] = None,        # comma-separated list
    unack: bool = False,
    limit: int = 200,
) -> list[dict]:
    """Unified brain-event feed."""
    since = (datetime.now() - timedelta(days=days)).isoformat()
    clauses = ["created_at >= ?"]
    args: list = [since]
    if kinds:
        kind_list = [k.strip() for k in kinds.split(",") if k.strip()]
        if kind_list:
            placeholders = ",".join("?" * len(kind_list))
            clauses.append(f"kind IN ({placeholders})")
            args.extend(kind_list)
    if unack:
        clauses.append("acknowledged = 0")
    where = " AND ".join(clauses)

    with db() as conn:
        rows = conn.execute(
            f"""
            SELECT id, created_at, kind, payment_id, severity, title,
                   explanation, payload_json, acknowledged
            FROM agent_events
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            tuple(args) + (limit,),
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        if d["payload_json"]:
            try:
                d["payload"] = json.loads(d["payload_json"])
            except (json.JSONDecodeError, TypeError):
                d["payload"] = None
        else:
            d["payload"] = None
        d.pop("payload_json", None)
        out.append(d)
    return out


@app.post("/api/events/{event_id}/ack")
def ack_event(event_id: int) -> dict:
    with db() as conn:
        conn.execute(
            "UPDATE agent_events SET acknowledged = 1 WHERE id = ?",
            (event_id,),
        )
        conn.commit()
    return {"ok": True}


class GoalCreate(BaseModel):
    description: str
    kind: str                          # 'avoid_merchant' | 'budget_cap' | 'frequency_cap'
    spec: dict
    scope: str                         # 'week' | 'month' | 'custom'


@app.get("/api/goals")
def list_goals_endpoint() -> list[dict]:
    with db() as conn:
        rows = conn.execute(
            """
            SELECT g.*, c.state, c.progress, c.message AS status_message,
                   c.updated_at AS status_updated_at
            FROM goals g
            LEFT JOIN goal_status_cache c ON c.goal_id = g.id
            ORDER BY g.created_at DESC
            """
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["spec"] = json.loads(d["spec_json"])
        except (json.JSONDecodeError, TypeError):
            d["spec"] = None
        d.pop("spec_json", None)
        out.append(d)
    return out


@app.post("/api/goals")
def create_goal_endpoint(goal: GoalCreate) -> dict:
    try:
        from core.detect.goals import create_goal
        with db() as conn:
            gid = create_goal(
                conn,
                description=goal.description, kind=goal.kind,
                spec=goal.spec, scope=goal.scope,
            )
            conn.commit()
        return {"id": gid}
    except (ValueError, ImportError) as e:
        raise HTTPException(400, str(e))


@app.delete("/api/goals/{goal_id}")
def delete_goal_endpoint(goal_id: int) -> dict:
    """Soft-delete: mark the goal as ended, preserve history."""
    with db() as conn:
        conn.execute("UPDATE goals SET status = 'ended' WHERE id = ?", (goal_id,))
        conn.commit()
    return {"ok": True}


@app.get("/api/story/weekly")
def get_weekly_story(week: Optional[str] = None) -> dict:
    """Return the most recent weekly story, or one for a specific week.
    Format: 'YYYY-Www' (e.g. '2026-W17')."""
    with db() as conn:
        if week:
            row = conn.execute(
                """
                SELECT * FROM agent_events
                WHERE kind = 'weekly_story' AND dedup_key = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (f"weekly_story:{week}",),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT * FROM agent_events
                WHERE kind = 'weekly_story'
                ORDER BY created_at DESC LIMIT 1
                """
            ).fetchone()
    if not row:
        raise HTTPException(404, "No weekly story available yet.")
    d = dict(row)
    if d["payload_json"]:
        try:
            d["payload"] = json.loads(d["payload_json"])
        except (json.JSONDecodeError, TypeError):
            d["payload"] = None
    d.pop("payload_json", None)
    return d


@app.get("/api/triage")
def triage_queue(limit: int = 100) -> list[dict]:
    """
    Triage queue: payments that need user attention.

    Surfaces payments that are uncategorized OR low-confidence (parser
    confidence below TRIAGE_CONFIDENCE_THRESHOLD). Newest first.
    """
    try:
        from core.config import TRIAGE_CONFIDENCE_THRESHOLD
    except ImportError:
        TRIAGE_CONFIDENCE_THRESHOLD = 0.7

    with db() as conn:
        rows = conn.execute(
            """
            SELECT id, occurred_at, amount, direction, bank,
                   counterparty_vpa, counterparty_name,
                   category, category_source, confidence, raw_text
            FROM payments
            WHERE direction = 'debit'
              AND (category IS NULL OR confidence < ?)
            ORDER BY occurred_at DESC
            LIMIT ?
            """,
            (TRIAGE_CONFIDENCE_THRESHOLD, limit),
        ).fetchall()
    return [dict(r) for r in rows]


@app.get("/api/recurring")
def list_recurring() -> list[dict]:
    """Detected recurring payment patterns."""
    with db() as conn:
        rows = conn.execute(
            """SELECT * FROM recurring_payments
               ORDER BY occurrences DESC, last_seen DESC"""
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["payment_ids"] = json.loads(d["payment_ids"])
        except (json.JSONDecodeError, TypeError):
            d["payment_ids"] = []
        out.append(d)
    return out


# --- HTML --------------------------------------------------------------------
#
# Aesthetic direction: personal financial journal. Warm cream paper, serif
# display type, monospace for numbers — like reading your own ledger. Restraint
# over decoration. One warm accent (rust) for debits, muted sage for credits.

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Ledger</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,500;0,9..144,700;1,9..144,400&family=JetBrains+Mono:wght@400;500&family=Newsreader:ital,opsz,wght@0,6..72,300;0,6..72,400;0,6..72,600;1,6..72,400&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root {
    --paper: #f5f0e6;
    --paper-dark: #ece5d6;
    --ink: #1f1a15;
    --ink-soft: #5a4f43;
    --ink-faint: #8a7f71;
    --rule: #c4b89f;
    --rust: #a8442a;
    --sage: #4f6848;
    --gold: #8a6a1f;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--paper);
    color: var(--ink);
    font-family: 'Newsreader', Georgia, serif;
    font-size: 16px;
    line-height: 1.5;
    min-height: 100vh;
    background-image:
      radial-gradient(ellipse at 20% 0%, rgba(168,68,42,0.04), transparent 50%),
      radial-gradient(ellipse at 80% 100%, rgba(79,104,72,0.04), transparent 50%);
  }
  .container {
    max-width: 1180px;
    margin: 0 auto;
    padding: 48px 40px 80px;
  }

  /* Masthead */
  header {
    border-bottom: 2px solid var(--ink);
    padding-bottom: 18px;
    margin-bottom: 42px;
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 16px;
  }
  h1 {
    font-family: 'Fraunces', Georgia, serif;
    font-weight: 700;
    font-size: 48px;
    letter-spacing: -0.02em;
    margin: 0;
    font-variation-settings: "opsz" 144;
  }
  h1 .sub {
    font-style: italic;
    font-weight: 300;
    color: var(--ink-soft);
    font-size: 0.55em;
    margin-left: 14px;
  }
  .window-picker {
    display: flex;
    gap: 2px;
    background: var(--paper-dark);
    border: 1px solid var(--rule);
    padding: 2px;
  }
  .window-picker button {
    background: transparent;
    border: none;
    padding: 6px 14px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    letter-spacing: 0.05em;
    color: var(--ink-soft);
    cursor: pointer;
    transition: all 0.15s;
  }
  .window-picker button:hover { color: var(--ink); }
  .window-picker button.active {
    background: var(--ink);
    color: var(--paper);
  }

  /* Summary strip */
  .summary {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 0;
    border: 1px solid var(--rule);
    background: var(--paper-dark);
    margin-bottom: 42px;
  }
  .summary > div {
    padding: 22px 24px;
    border-right: 1px solid var(--rule);
  }
  .summary > div:last-child { border-right: none; }
  .summary .label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--ink-faint);
    margin-bottom: 8px;
  }
  .summary .value {
    font-family: 'Fraunces', serif;
    font-size: 32px;
    font-weight: 500;
    font-variation-settings: "opsz" 72;
    line-height: 1;
  }
  .summary .value.rust  { color: var(--rust); }
  .summary .value.sage  { color: var(--sage); }

  /* Two-column grid */
  .grid {
    display: grid;
    grid-template-columns: 2fr 1fr;
    gap: 42px;
    margin-bottom: 42px;
  }
  .section {
    background: transparent;
  }
  .section h2 {
    font-family: 'Fraunces', serif;
    font-weight: 500;
    font-size: 22px;
    letter-spacing: -0.01em;
    margin: 0 0 16px 0;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--rule);
    font-style: italic;
  }

  /* Chart */
  .chart-wrap {
    background: var(--paper-dark);
    border: 1px solid var(--rule);
    padding: 20px;
    height: 280px;
  }

  /* Top recipients list */
  .recipients { list-style: none; padding: 0; margin: 0; }
  .recipients li {
    display: flex;
    justify-content: space-between;
    align-items: baseline;
    padding: 10px 0;
    border-bottom: 1px dotted var(--rule);
    gap: 12px;
  }
  .recipients li:last-child { border-bottom: none; }
  .recipients .who {
    font-size: 15px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    flex: 1;
  }
  .recipients .amt {
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    color: var(--rust);
    font-weight: 500;
  }
  .recipients .count {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--ink-faint);
    min-width: 50px;
    text-align: right;
  }

  /* Ledger */
  .ledger { width: 100%; border-collapse: collapse; }
  .ledger thead th {
    text-align: left;
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--ink-faint);
    font-weight: 400;
    padding: 10px 12px;
    border-bottom: 1px solid var(--ink);
  }
  .ledger tbody tr {
    border-bottom: 1px solid var(--rule);
    transition: background 0.1s;
  }
  .ledger tbody tr:hover { background: var(--paper-dark); }
  .ledger td {
    padding: 14px 12px;
    vertical-align: top;
  }
  .ledger .date {
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    color: var(--ink-soft);
    white-space: nowrap;
  }
  .ledger .who { font-weight: 500; }
  .ledger .who .vpa {
    display: block;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--ink-faint);
    font-weight: 400;
    margin-top: 2px;
  }
  .ledger .context {
    font-style: italic;
    color: var(--ink-soft);
    font-size: 14px;
    margin-top: 4px;
  }
  .ledger .context::before { content: "— "; color: var(--gold); }
  .ledger .amt {
    font-family: 'JetBrains Mono', monospace;
    font-weight: 500;
    text-align: right;
    white-space: nowrap;
  }
  .ledger .amt.debit  { color: var(--rust); }
  .ledger .amt.credit { color: var(--sage); }
  .ledger .cat-input {
    background: transparent;
    border: none;
    border-bottom: 1px dotted var(--rule);
    padding: 2px 4px;
    font-family: inherit;
    font-size: 13px;
    color: var(--ink);
    width: 100%;
    font-style: italic;
  }
  .ledger .cat-input:focus {
    outline: none;
    border-bottom-color: var(--rust);
  }
  .ledger .cat-input::placeholder { color: var(--ink-faint); }
  .ledger .conf-dot {
    display: inline-block;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    vertical-align: middle;
    margin-right: 6px;
  }
  .ledger .conf-high { background: var(--sage); }
  .ledger .conf-mid  { background: var(--gold); }
  .ledger .conf-low  { background: var(--rust); }

  .empty {
    padding: 40px;
    text-align: center;
    color: var(--ink-faint);
    font-style: italic;
    border: 1px dashed var(--rule);
  }

  @media (max-width: 900px) {
    .grid { grid-template-columns: 1fr; }
    .summary { grid-template-columns: repeat(2, 1fr); }
    .summary > div { border-right: none; border-bottom: 1px solid var(--rule); }
    h1 { font-size: 36px; }
  }
</style>
</head>
<body>
<div class="container">

  <header>
    <h1>Ledger <span class="sub" id="dateRange"></span></h1>
    <div style="display:flex; gap:18px; align-items:center;">
      <nav style="display:flex; gap:18px;">
        <a href="/" style="font-family:'JetBrains Mono',monospace; font-size:12px; color:var(--ink); text-decoration:none; text-transform:uppercase; letter-spacing:0.08em; padding:4px 0; border-bottom:1px solid var(--ink);">Ledger</a>
        <a href="/feed" style="font-family:'JetBrains Mono',monospace; font-size:12px; color:var(--ink-soft); text-decoration:none; text-transform:uppercase; letter-spacing:0.08em; padding:4px 0; border-bottom:1px solid transparent;">Feed</a>
        <a href="/triage" style="font-family:'JetBrains Mono',monospace; font-size:12px; color:var(--ink-soft); text-decoration:none; text-transform:uppercase; letter-spacing:0.08em; padding:4px 0; border-bottom:1px solid transparent;">Triage</a>
      </nav>
      <div class="window-picker" id="windowPicker">
        <button data-days="7">7D</button>
        <button data-days="30" class="active">30D</button>
        <button data-days="90">90D</button>
        <button data-days="365">1Y</button>
      </div>
    </div>
  </header>

  <section class="summary">
    <div>
      <div class="label">Spent</div>
      <div class="value rust" id="sumSpent">—</div>
    </div>
    <div>
      <div class="label">Received</div>
      <div class="value sage" id="sumReceived">—</div>
    </div>
    <div>
      <div class="label">Transactions</div>
      <div class="value" id="sumTxns">—</div>
    </div>
    <div>
      <div class="label">Distinct Payees</div>
      <div class="value" id="sumUniques">—</div>
    </div>
  </section>

  <div class="grid">
    <div class="section">
      <h2>Daily outflow</h2>
      <div class="chart-wrap">
        <canvas id="dailyChart"></canvas>
      </div>
    </div>
    <div class="section">
      <h2>Where it goes</h2>
      <ul class="recipients" id="recipientsList"></ul>
    </div>
  </div>

  <div class="section">
    <h2>The record</h2>
    <table class="ledger">
      <thead>
        <tr>
          <th style="width: 110px;">Date</th>
          <th>To / From</th>
          <th>Category</th>
          <th style="text-align: right; width: 120px;">Amount</th>
        </tr>
      </thead>
      <tbody id="ledgerBody"></tbody>
    </table>
    <div id="emptyState" class="empty" style="display:none;">
      No payments in this window. Run <code>python3 agent.py</code> to ingest.
    </div>
  </div>

</div>

<script>
const money = (n) => {
  if (!n) return '₹0';
  return '₹' + Number(n).toLocaleString('en-IN', {maximumFractionDigits: 0});
};
const money2 = (n) => {
  if (!n) return '₹0';
  return '₹' + Number(n).toLocaleString('en-IN', {minimumFractionDigits: 2, maximumFractionDigits: 2});
};
const fmtDate = (iso) => {
  const d = new Date(iso);
  const m = d.toLocaleString('en', {month: 'short'});
  return `${d.getDate()} ${m}\n${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`;
};

let chart = null;
let currentDays = 30;

async function load(days) {
  currentDays = days;
  const [summary, payments, daily, recipients] = await Promise.all([
    fetch(`/api/summary?days=${days}`).then(r => r.json()),
    fetch(`/api/payments?days=${days}`).then(r => r.json()),
    fetch(`/api/daily_spend?days=${days}`).then(r => r.json()),
    fetch(`/api/top_recipients?days=${days}`).then(r => r.json()),
  ]);

  renderSummary(summary);
  renderChart(daily);
  renderRecipients(recipients);
  renderLedger(payments);
  renderDateRange(days);
}

function renderDateRange(days) {
  const end = new Date();
  const start = new Date(end - days * 86400000);
  const fmt = (d) => d.toLocaleString('en', {day:'numeric', month:'long'});
  document.getElementById('dateRange').textContent = `${fmt(start)} – ${fmt(end)}`;
}

function renderSummary(s) {
  document.getElementById('sumSpent').textContent = money(s.spent);
  document.getElementById('sumReceived').textContent = money(s.received);
  document.getElementById('sumTxns').textContent = s.txns.toLocaleString();
  document.getElementById('sumUniques').textContent = s.uniques.toLocaleString();
}

function renderChart(daily) {
  const ctx = document.getElementById('dailyChart').getContext('2d');
  if (chart) chart.destroy();
  chart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: daily.map(d => d.day.slice(5)),
      datasets: [{
        data: daily.map(d => d.total),
        backgroundColor: '#a8442a',
        borderRadius: 0,
        barThickness: 'flex',
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {display: false},
        tooltip: {
          backgroundColor: '#1f1a15',
          titleFont: {family: 'JetBrains Mono', size: 11},
          bodyFont: {family: 'JetBrains Mono', size: 12},
          padding: 10,
          callbacks: {
            label: (ctx) => money2(ctx.raw),
          }
        }
      },
      scales: {
        x: {
          grid: {display: false},
          ticks: {
            font: {family: 'JetBrains Mono', size: 10},
            color: '#8a7f71',
            maxRotation: 0,
          },
          border: {color: '#c4b89f'},
        },
        y: {
          grid: {color: '#ece5d6'},
          ticks: {
            font: {family: 'JetBrains Mono', size: 10},
            color: '#8a7f71',
            callback: (v) => '₹' + (v >= 1000 ? (v/1000).toFixed(0) + 'k' : v),
          },
          border: {display: false},
        }
      }
    }
  });
}

function renderRecipients(rows) {
  const ul = document.getElementById('recipientsList');
  if (!rows.length) {
    ul.innerHTML = '<li><span class="who">No payments yet</span></li>';
    return;
  }
  ul.innerHTML = rows.map(r => `
    <li>
      <span class="who" title="${escapeHtml(r.who)}">${escapeHtml(truncate(r.who, 28))}</span>
      <span class="count">${r.txns}×</span>
      <span class="amt">${money(r.total)}</span>
    </li>
  `).join('');
}

function renderLedger(payments) {
  const tbody = document.getElementById('ledgerBody');
  const empty = document.getElementById('emptyState');
  if (!payments.length) {
    tbody.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';

  tbody.innerHTML = payments.map(p => {
    const who = p.counterparty_name || p.counterparty_vpa || '?';
    const vpaBadge = (p.counterparty_name && p.counterparty_vpa)
      ? `<span class="vpa">${escapeHtml(p.counterparty_vpa)}</span>` : '';
    const ctx = p.calendar_events && p.calendar_events.length
      ? `<div class="context">${escapeHtml(p.calendar_events[0].title)}</div>` : '';
    const confClass = p.confidence >= 0.85 ? 'conf-high'
                    : p.confidence >= 0.6 ? 'conf-mid' : 'conf-low';
    const amt = `${p.direction === 'debit' ? '−' : '+'}${money2(p.amount)}`;
    const date = new Date(p.occurred_at);
    const dateStr = `${date.getDate().toString().padStart(2,'0')} ${date.toLocaleString('en',{month:'short'})}<br>${date.getHours().toString().padStart(2,'0')}:${date.getMinutes().toString().padStart(2,'0')}`;

    return `
      <tr>
        <td class="date">${dateStr}</td>
        <td>
          <div class="who"><span class="conf-dot ${confClass}"></span>${escapeHtml(who)}</div>
          ${vpaBadge}
          ${ctx}
        </td>
        <td>
          <input class="cat-input" data-id="${p.id}" value="${escapeHtml(p.category || '')}" placeholder="Categorize…">
        </td>
        <td class="amt ${p.direction}">${amt}</td>
      </tr>
    `;
  }).join('');

  // Wire up category saves (on blur)
  tbody.querySelectorAll('.cat-input').forEach(input => {
    input.addEventListener('blur', async (e) => {
      const id = e.target.dataset.id;
      await fetch(`/api/payments/${id}`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({category: e.target.value || null}),
      });
    });
  });
}

function escapeHtml(s) {
  if (s == null) return '';
  return String(s).replace(/[&<>"']/g, m => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  })[m]);
}
function truncate(s, n) { return s.length > n ? s.slice(0, n-1) + '…' : s; }

// Window picker
document.getElementById('windowPicker').addEventListener('click', (e) => {
  const btn = e.target.closest('button');
  if (!btn) return;
  document.querySelectorAll('#windowPicker button').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  load(parseInt(btn.dataset.days));
});

load(30);
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def index():
    return INDEX_HTML


# --- Feed view: unified scrolling event timeline -----------------------------
#
# Same editorial-ledger aesthetic as index. Renders agent_events grouped
# by day, with severity dots and inline acknowledge actions. Reads
# /api/events at load time. Vanilla JS + minimal CSS, no framework.

FEED_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Feed · Ledger</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,500;0,9..144,700;1,9..144,400&family=JetBrains+Mono:wght@400;500&family=Newsreader:ital,opsz,wght@0,6..72,300;0,6..72,400;0,6..72,600;1,6..72,400&display=swap" rel="stylesheet">
<style>
  :root {
    --paper: #f5f0e6;
    --paper-dark: #ece5d6;
    --ink: #1f1a15;
    --ink-soft: #5a4f43;
    --ink-faint: #8a7f71;
    --rule: #c4b89f;
    --rust: #a8442a;
    --sage: #4f6848;
    --gold: #8a6a1f;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    background: var(--paper);
    color: var(--ink);
    font-family: 'Newsreader', Georgia, serif;
    font-size: 16px;
    line-height: 1.5;
    min-height: 100vh;
  }
  .container { max-width: 820px; margin: 0 auto; padding: 48px 32px 80px; }
  header {
    border-bottom: 2px solid var(--ink);
    padding-bottom: 18px;
    margin-bottom: 36px;
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 16px;
  }
  h1 {
    font-family: 'Fraunces', serif;
    font-weight: 700;
    font-size: 44px;
    letter-spacing: -0.02em;
    margin: 0;
    font-variation-settings: "opsz" 144;
  }
  nav { display: flex; gap: 18px; }
  nav a {
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    color: var(--ink-soft);
    text-decoration: none;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    padding: 4px 0;
    border-bottom: 1px solid transparent;
  }
  nav a:hover { color: var(--ink); border-bottom-color: var(--rust); }
  nav a.active { color: var(--ink); border-bottom-color: var(--ink); }

  .filters {
    display: flex; gap: 6px; margin-bottom: 28px; flex-wrap: wrap;
  }
  .filters button {
    background: transparent; border: 1px solid var(--rule);
    padding: 5px 12px; font-family: 'JetBrains Mono', monospace;
    font-size: 11px; color: var(--ink-soft); cursor: pointer;
    letter-spacing: 0.05em;
  }
  .filters button.active { background: var(--ink); color: var(--paper); border-color: var(--ink); }

  .day-group { margin-bottom: 36px; }
  .day-label {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--ink-faint);
    letter-spacing: 0.1em;
    text-transform: uppercase;
    margin-bottom: 10px;
    padding-bottom: 6px;
    border-bottom: 1px dotted var(--rule);
  }
  .event {
    display: flex;
    gap: 14px;
    padding: 16px 0;
    border-bottom: 1px solid var(--rule);
    align-items: flex-start;
  }
  .event:last-child { border-bottom: none; }
  .event.acked { opacity: 0.45; }
  .sev {
    width: 8px; height: 8px; border-radius: 50%;
    margin-top: 8px; flex-shrink: 0;
  }
  .sev-0 { background: var(--ink-faint); }
  .sev-1 { background: var(--gold); }
  .sev-2 { background: var(--rust); }
  .sev-3 { background: var(--rust); box-shadow: 0 0 0 3px rgba(168,68,42,0.2); }

  .event-body { flex: 1; min-width: 0; }
  .event-title {
    font-weight: 500;
    margin-bottom: 4px;
    font-size: 17px;
  }
  .event-meta {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--ink-faint);
    margin-bottom: 6px;
    letter-spacing: 0.04em;
  }
  .event-explanation {
    color: var(--ink-soft);
    font-size: 15px;
    line-height: 1.55;
  }
  .event-actions { margin-top: 8px; }
  .ack-btn {
    background: transparent;
    border: none;
    padding: 0;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: var(--rust);
    cursor: pointer;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    border-bottom: 1px dotted var(--rust);
  }
  .ack-btn:hover { color: var(--ink); border-bottom-color: var(--ink); }
  .empty { color: var(--ink-faint); font-style: italic; padding: 40px 0; text-align: center; }
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>Feed</h1>
    <nav>
      <a href="/">Ledger</a>
      <a href="/feed" class="active">Feed</a>
      <a href="/triage">Triage</a>
    </nav>
  </header>

  <div class="filters" id="filters">
    <button data-kinds="" class="active">All</button>
    <button data-kinds="anomaly">Anomalies</button>
    <button data-kinds="goal_warning,goal_violation">Goals</button>
    <button data-kinds="recurring_detected">Recurring</button>
    <button data-kinds="weekly_story">Stories</button>
    <button data-kinds="categorized">Categorizations</button>
  </div>

  <div id="events"></div>
</div>

<script>
const KIND_LABELS = {
  categorized: "Categorized",
  anomaly: "Anomaly",
  goal_warning: "Goal warning",
  goal_violation: "Goal violation",
  weekly_story: "Weekly story",
  recurring_detected: "Recurring",
  nudge: "Nudge",
};

let currentKinds = "";

async function load() {
  const params = new URLSearchParams({ days: "60", limit: "300" });
  if (currentKinds) params.set("kinds", currentKinds);
  const events = await fetch(`/api/events?${params}`).then(r => r.json());
  render(events);
}

function render(events) {
  const root = document.getElementById("events");
  if (!events.length) {
    root.innerHTML = '<div class="empty">No events match this filter.</div>';
    return;
  }
  // Group by day (YYYY-MM-DD prefix of created_at)
  const byDay = {};
  for (const e of events) {
    const day = e.created_at.slice(0, 10);
    (byDay[day] ||= []).push(e);
  }
  const days = Object.keys(byDay).sort().reverse();
  const today = new Date().toISOString().slice(0, 10);

  root.innerHTML = days.map(day => `
    <div class="day-group">
      <div class="day-label">${formatDayLabel(day, today)}</div>
      ${byDay[day].map(renderEvent).join("")}
    </div>
  `).join("");

  // Wire up ack buttons
  root.querySelectorAll(".ack-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.id;
      await fetch(`/api/events/${id}/ack`, { method: "POST" });
      load();
    });
  });
}

function renderEvent(e) {
  const time = e.created_at.slice(11, 16);
  const ackedClass = e.acknowledged ? " acked" : "";
  const ackBtn = e.acknowledged
    ? ""
    : `<div class="event-actions"><button class="ack-btn" data-id="${e.id}">Acknowledge</button></div>`;
  return `
    <div class="event${ackedClass}">
      <div class="sev sev-${e.severity}"></div>
      <div class="event-body">
        <div class="event-meta">${time} · ${KIND_LABELS[e.kind] || e.kind}</div>
        <div class="event-title">${escapeHtml(e.title)}</div>
        <div class="event-explanation">${escapeHtml(e.explanation)}</div>
        ${ackBtn}
      </div>
    </div>
  `;
}

function formatDayLabel(day, today) {
  if (day === today) return "Today";
  const yesterday = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
  if (day === yesterday) return "Yesterday";
  const d = new Date(day);
  return d.toLocaleString("en", { weekday: "long", month: "long", day: "numeric" });
}

function escapeHtml(s) {
  if (s == null) return "";
  return String(s).replace(/[&<>"']/g, m => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[m]);
}

document.getElementById("filters").addEventListener("click", e => {
  const btn = e.target.closest("button");
  if (!btn) return;
  document.querySelectorAll("#filters button").forEach(b => b.classList.remove("active"));
  btn.classList.add("active");
  currentKinds = btn.dataset.kinds;
  load();
});

load();
</script>
</body>
</html>
"""


@app.get("/feed", response_class=HTMLResponse)
def feed_view():
    return FEED_HTML


# --- Triage view: payments needing attention ---------------------------------

TRIAGE_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Triage · Ledger</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,opsz,wght@0,9..144,300;0,9..144,500;0,9..144,700;1,9..144,400&family=JetBrains+Mono:wght@400;500&family=Newsreader:ital,opsz,wght@0,6..72,300;0,6..72,400;0,6..72,600;1,6..72,400&display=swap" rel="stylesheet">
<style>
  :root {
    --paper: #f5f0e6;
    --paper-dark: #ece5d6;
    --ink: #1f1a15;
    --ink-soft: #5a4f43;
    --ink-faint: #8a7f71;
    --rule: #c4b89f;
    --rust: #a8442a;
    --sage: #4f6848;
    --gold: #8a6a1f;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--paper); color: var(--ink);
    font-family: 'Newsreader', Georgia, serif;
    font-size: 16px; line-height: 1.5; min-height: 100vh;
  }
  .container { max-width: 920px; margin: 0 auto; padding: 48px 32px 80px; }
  header {
    border-bottom: 2px solid var(--ink);
    padding-bottom: 18px;
    margin-bottom: 36px;
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 16px;
  }
  h1 {
    font-family: 'Fraunces', serif;
    font-weight: 700;
    font-size: 44px;
    letter-spacing: -0.02em;
    margin: 0;
    font-variation-settings: "opsz" 144;
  }
  h1 .sub {
    font-style: italic; font-weight: 300;
    color: var(--ink-soft);
    font-size: 0.45em; margin-left: 14px;
  }
  nav { display: flex; gap: 18px; }
  nav a {
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    color: var(--ink-soft);
    text-decoration: none;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    padding: 4px 0;
    border-bottom: 1px solid transparent;
  }
  nav a:hover { color: var(--ink); border-bottom-color: var(--rust); }
  nav a.active { color: var(--ink); border-bottom-color: var(--ink); }

  .blurb {
    color: var(--ink-soft); font-size: 16px;
    margin-bottom: 28px; max-width: 620px;
    font-style: italic;
  }

  .row {
    display: grid;
    grid-template-columns: 110px 1fr 220px 110px;
    gap: 16px;
    padding: 18px 0;
    border-bottom: 1px solid var(--rule);
    align-items: start;
  }
  .row:last-child { border-bottom: none; }
  .row:hover { background: var(--paper-dark); }
  .row .when {
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px; color: var(--ink-soft);
  }
  .row .who { font-weight: 500; }
  .row .who .vpa {
    display: block;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px; color: var(--ink-faint);
    font-weight: 400; margin-top: 3px;
  }
  .row .raw {
    color: var(--ink-faint);
    font-size: 13px; font-style: italic;
    margin-top: 6px;
    line-height: 1.45;
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
  }
  .row .amt {
    font-family: 'JetBrains Mono', monospace;
    font-weight: 500; color: var(--rust);
    text-align: right; white-space: nowrap;
  }
  .row select {
    width: 100%;
    background: transparent;
    border: 1px solid var(--rule);
    padding: 6px 8px;
    font-family: inherit;
    font-size: 14px;
    color: var(--ink);
  }
  .empty {
    padding: 60px 20px; text-align: center;
    color: var(--ink-faint); font-style: italic;
    border: 1px dashed var(--rule);
  }
  .saved {
    color: var(--sage);
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    margin-top: 4px;
  }
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>Triage <span class="sub" id="count"></span></h1>
    <nav>
      <a href="/">Ledger</a>
      <a href="/feed">Feed</a>
      <a href="/triage" class="active">Triage</a>
    </nav>
  </header>

  <p class="blurb">
    Payments that need a human. Either uncategorized, or parsed with low
    confidence. Set a category to teach the agent — your correction is
    learned and applied to future payments to the same payee.
  </p>

  <div id="rows"></div>
</div>

<script>
const CATEGORIES = ["Food","Groceries","Travel","Transport","Shopping","Bills","Rent","Entertainment","Health","Personal","Transfer","Other"];

async function load() {
  const rows = await fetch("/api/triage?limit=200").then(r => r.json());
  document.getElementById("count").textContent = `${rows.length} pending`;
  const root = document.getElementById("rows");
  if (!rows.length) {
    root.innerHTML = '<div class="empty">All caught up. Nothing to triage.</div>';
    return;
  }
  root.innerHTML = rows.map(p => {
    const date = new Date(p.occurred_at);
    const when = `${date.getDate().toString().padStart(2,"0")} ${date.toLocaleString("en",{month:"short"})}<br>${date.getHours().toString().padStart(2,"0")}:${date.getMinutes().toString().padStart(2,"0")}`;
    const who = p.counterparty_name || p.counterparty_vpa || "?";
    const vpaBadge = (p.counterparty_name && p.counterparty_vpa)
      ? `<span class="vpa">${escapeHtml(p.counterparty_vpa)}</span>` : "";
    const opts = CATEGORIES.map(c =>
      `<option value="${c}"${p.category === c ? " selected" : ""}>${c}</option>`
    ).join("");
    return `
      <div class="row" data-id="${p.id}">
        <div class="when">${when}</div>
        <div>
          <div class="who">${escapeHtml(who)}</div>
          ${vpaBadge}
          <div class="raw">${escapeHtml(p.raw_text || "")}</div>
        </div>
        <div>
          <select data-id="${p.id}">
            <option value="">Categorize…</option>
            ${opts}
          </select>
          <div class="saved" data-saved-for="${p.id}" style="display:none;">Saved · learning applied</div>
        </div>
        <div class="amt">${money(p.amount)}</div>
      </div>
    `;
  }).join("");
  root.querySelectorAll("select").forEach(sel => {
    sel.addEventListener("change", async e => {
      const id = e.target.dataset.id;
      if (!e.target.value) return;
      await fetch(`/api/payments/${id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category: e.target.value }),
      });
      const note = document.querySelector(`[data-saved-for="${id}"]`);
      if (note) {
        note.style.display = "block";
        setTimeout(() => { load(); }, 600);
      }
    });
  });
}

function money(n) {
  if (!n) return "₹0";
  return "₹" + Number(n).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
function escapeHtml(s) {
  if (s == null) return "";
  return String(s).replace(/[&<>"']/g, m => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[m]);
}

load();
</script>
</body>
</html>
"""


@app.get("/triage", response_class=HTMLResponse)
def triage_view():
    return TRIAGE_HTML


def main():
    # 127.0.0.1 only — never bind to 0.0.0.0. Data stays on this machine.
    uvicorn.run(app, host="127.0.0.1", port=7070, log_level="warning")


if __name__ == "__main__":
    main()

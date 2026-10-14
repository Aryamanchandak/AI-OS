"""
Weekly spend narrator.

Produces a structured WeeklyStory (counts, deltas, calendar correlations,
goal status) and renders it to markdown. The structured part is fully
deterministic — no LLM involved. An optional OpenAI rephrase pass can
soften the opening paragraph if USE_LLM_NARRATOR is enabled.
"""

from __future__ import annotations

import json
import os
import re as _re
import sqlite3
import statistics
from collections import defaultdict
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Any

from core import config
from core.detect import goals
from core.schema.db import connect
from core.utils.money import _money


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------

@dataclass
class CategorySummary:
    amount: float
    txns: int
    delta_vs_prior_week_pct: float | None


@dataclass
class CalendarCorrelation:
    keyword: str
    category: str
    amount_with: float
    amount_without: float
    days_with: int
    days_without: int
    description: str


@dataclass
class GoalStatusSnapshot:
    description: str
    kind: str
    state: str
    progress: float
    message: str


@dataclass
class WeeklyStory:
    period_start: date
    period_end: date
    total_spent: float
    total_received: float
    txn_count: int
    by_category: dict[str, CategorySummary]
    top_merchants: list[dict[str, Any]]
    calendar_correlations: list[CalendarCorrelation]
    goals_status: list[GoalStatusSnapshot]
    anomalies: list[dict[str, Any]]
    uncategorized_count: int

    def to_dict(self) -> dict:
        d = asdict(self)
        d["period_start"] = self.period_start.isoformat()
        d["period_end"] = self.period_end.isoformat()
        return d


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _week_bounds(end_date: datetime) -> tuple[datetime, datetime]:
    """Mon 00:00 → next Mon 00:00 for the ISO week containing end_date."""
    d = end_date.date()
    monday = d - timedelta(days=d.weekday())
    start = datetime.combine(monday, datetime.min.time())
    return start, start + timedelta(days=7)


def _resolve_end_date(end_date: datetime | None) -> datetime:
    if end_date is None:
        end_date = datetime.now()
    if end_date.weekday() == 6 and end_date.hour >= 18:
        return end_date
    if end_date.weekday() == 0 and end_date.hour < 12:
        return end_date - timedelta(days=1)
    return end_date


# ---------------------------------------------------------------------------
# Story computation
# ---------------------------------------------------------------------------

def _compute_category_summary(
    conn: sqlite3.Connection, start: datetime, end: datetime,
) -> dict[str, CategorySummary]:
    rows = conn.execute(
        """
        SELECT COALESCE(category, '(uncategorized)') AS cat,
               SUM(amount) AS amt,
               COUNT(*) AS n
        FROM payments
        WHERE direction='debit' AND occurred_at >= ? AND occurred_at < ?
        GROUP BY cat
        """,
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    this_week = {r["cat"]: (r["amt"] or 0, r["n"]) for r in rows}

    prior_start = start - timedelta(days=7)
    prior_end = start
    prior_rows = conn.execute(
        """
        SELECT COALESCE(category, '(uncategorized)') AS cat, SUM(amount) AS amt
        FROM payments
        WHERE direction='debit' AND occurred_at >= ? AND occurred_at < ?
        GROUP BY cat
        """,
        (prior_start.isoformat(), prior_end.isoformat()),
    ).fetchall()
    prior = {r["cat"]: (r["amt"] or 0) for r in prior_rows}

    out: dict[str, CategorySummary] = {}
    for cat, (amt, n) in this_week.items():
        prior_amt = prior.get(cat, 0)
        if prior_amt > 0:
            delta = (amt - prior_amt) / prior_amt * 100
        elif amt > 0:
            delta = None
        else:
            delta = 0
        out[cat] = CategorySummary(amount=amt, txns=n, delta_vs_prior_week_pct=delta)
    return out


def _compute_top_merchants(
    conn: sqlite3.Connection, start: datetime, end: datetime, limit: int = 5,
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT COALESCE(counterparty_name, counterparty_vpa, '?') AS name,
               SUM(amount) AS amt, COUNT(*) AS n
        FROM payments
        WHERE direction='debit' AND occurred_at >= ? AND occurred_at < ?
        GROUP BY name
        ORDER BY amt DESC
        LIMIT ?
        """,
        (start.isoformat(), end.isoformat(), limit),
    ).fetchall()
    return [{"name": r["name"], "amount": r["amt"] or 0, "txns": r["n"]}
            for r in rows]


def _compute_calendar_correlations(
    conn: sqlite3.Connection, start: datetime, end: datetime,
) -> list[CalendarCorrelation]:
    rows = conn.execute(
        """
        SELECT occurred_at, amount, category, calendar_events
        FROM payments
        WHERE direction='debit' AND occurred_at >= ? AND occurred_at < ?
        """,
        (start.isoformat(), end.isoformat()),
    ).fetchall()

    day_events: dict[date, list[str]] = defaultdict(list)
    day_cat_amounts: dict[date, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for r in rows:
        d = datetime.fromisoformat(r["occurred_at"]).date()
        if r["calendar_events"]:
            try:
                evs = json.loads(r["calendar_events"]) or []
                for ev in evs:
                    title = (ev.get("title") or "").lower()
                    if title:
                        day_events[d].append(title)
            except (json.JSONDecodeError, TypeError):
                pass
        cat = r["category"] or "(uncategorized)"
        day_cat_amounts[d][cat] += r["amount"] or 0

    correlations: list[CalendarCorrelation] = []
    for pattern, category in config.CALENDAR_KEYWORDS:
        days_with: list[float] = []
        days_without: list[float] = []
        for d in day_cat_amounts:
            spend = day_cat_amounts[d].get(category, 0)
            day_titles = " ".join(day_events.get(d, []))
            if _re.search(pattern, day_titles):
                days_with.append(spend)
            else:
                days_without.append(spend)
        if len(days_with) < 3 or len(days_without) < 3:
            continue
        avg_with = statistics.mean(days_with)
        avg_without = statistics.mean(days_without)
        if avg_without == 0 and avg_with == 0:
            continue
        baseline = max(avg_without, 1)
        rel_gap = (avg_with - avg_without) / baseline
        if abs(rel_gap) < config.NARRATOR_CALENDAR_CORRELATION_GAP:
            continue
        keyword_label = pattern.split("|")[0]
        direction = "more" if rel_gap > 0 else "less"
        correlations.append(CalendarCorrelation(
            keyword=keyword_label,
            category=category,
            amount_with=avg_with,
            amount_without=avg_without,
            days_with=len(days_with),
            days_without=len(days_without),
            description=(
                f"On days with '{keyword_label}'-related events, you spent "
                f"{_money(avg_with)} on average in {category} — "
                f"{abs(rel_gap)*100:.0f}% {direction} than other days "
                f"({_money(avg_without)})."
            ),
        ))
    return correlations


def _compute_goal_snapshots(conn: sqlite3.Connection) -> list[GoalStatusSnapshot]:
    rows = conn.execute(
        """
        SELECT g.description, g.kind, c.state, c.progress, c.message
        FROM goals g
        LEFT JOIN goal_status_cache c ON c.goal_id = g.id
        WHERE g.status = 'active'
        ORDER BY g.id
        """
    ).fetchall()
    out = []
    for r in rows:
        if r["state"] is None:
            goal = conn.execute("SELECT * FROM goals WHERE description = ?", (r["description"],)).fetchone()
            status = goals.evaluate(goal, conn)
            out.append(GoalStatusSnapshot(
                description=r["description"], kind=r["kind"],
                state=status.state, progress=status.progress, message=status.message,
            ))
        else:
            out.append(GoalStatusSnapshot(
                description=r["description"], kind=r["kind"],
                state=r["state"], progress=r["progress"] or 0,
                message=r["message"] or "",
            ))
    return out


def weekly_story(
    end_date: datetime | None = None, *,
    db_path: Path | str | None = None,
) -> WeeklyStory:
    """Compute the structured story for the week containing/ending on end_date."""
    end_date = _resolve_end_date(end_date)
    start, end = _week_bounds(end_date)

    with connect(db_path) as conn:
        totals = conn.execute(
            """
            SELECT
              SUM(CASE WHEN direction='debit'  THEN amount ELSE 0 END) AS spent,
              SUM(CASE WHEN direction='credit' THEN amount ELSE 0 END) AS received,
              COUNT(*) AS n
            FROM payments
            WHERE occurred_at >= ? AND occurred_at < ?
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchone()

        by_cat = _compute_category_summary(conn, start, end)
        top = _compute_top_merchants(conn, start, end)
        correlations = _compute_calendar_correlations(conn, start, end)
        goal_snaps = _compute_goal_snapshots(conn)

        anom_rows = conn.execute(
            """
            SELECT title, severity FROM agent_events
            WHERE kind = 'anomaly' AND created_at >= ? AND created_at < ?
            ORDER BY severity DESC, created_at ASC
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchall()
        anomalies = [{"title": r["title"], "severity": r["severity"]} for r in anom_rows]

        uncat = conn.execute(
            """
            SELECT COUNT(*) FROM payments
            WHERE direction='debit'
              AND category IS NULL
              AND occurred_at >= ? AND occurred_at < ?
            """,
            (start.isoformat(), end.isoformat()),
        ).fetchone()[0]

    return WeeklyStory(
        period_start=start.date(),
        period_end=(end - timedelta(days=1)).date(),
        total_spent=totals["spent"] or 0,
        total_received=totals["received"] or 0,
        txn_count=totals["n"] or 0,
        by_category=by_cat,
        top_merchants=top,
        calendar_correlations=correlations,
        goals_status=goal_snaps,
        anomalies=anomalies,
        uncategorized_count=uncat,
    )


# ---------------------------------------------------------------------------
# Markdown rendering
# ---------------------------------------------------------------------------

def _delta_arrow(pct: float | None) -> str:
    if pct is None:
        return " (new)"
    if abs(pct) < 5:
        return " (≈)"
    return f" ({'↑' if pct > 0 else '↓'}{abs(pct):.0f}%)"


def render_markdown(story: WeeklyStory) -> str:
    """Convert WeeklyStory to a markdown document."""
    lines: list[str] = []

    lines.append(f"# Week of {story.period_start.isoformat()} – {story.period_end.isoformat()}")
    lines.append("")

    headline_bits = []
    headline_bits.append(
        f"You spent {_money(story.total_spent)} across {story.txn_count} "
        f"transaction{'s' if story.txn_count != 1 else ''}"
    )
    if story.total_received > 0:
        headline_bits.append(f"and received {_money(story.total_received)}")
    biggest_violation = next(
        (g for g in story.goals_status if g.state == "violated"),
        None,
    )
    if biggest_violation:
        msg = biggest_violation.message.rstrip(".")
        headline_bits.append(
            f"Goal in trouble — '{biggest_violation.description}': {msg}"
        )
    opener = "; ".join(headline_bits) + "."
    lines.append(opener)
    lines.append("")

    lines.append("## By category")
    lines.append("")
    if story.by_category:
        sorted_cats = sorted(
            story.by_category.items(), key=lambda kv: kv[1].amount, reverse=True,
        )
        for cat, summary in sorted_cats:
            arrow = _delta_arrow(summary.delta_vs_prior_week_pct)
            lines.append(
                f"- **{cat}**: {_money(summary.amount)}{arrow} "
                f"across {summary.txns} txn{'s' if summary.txns != 1 else ''}"
            )
    else:
        lines.append("_No spending this week._")
    lines.append("")

    lines.append("## Top merchants")
    lines.append("")
    if story.top_merchants:
        for m in story.top_merchants:
            lines.append(
                f"- {m['name']}: {_money(m['amount'])} ({m['txns']} txn"
                f"{'s' if m['txns'] != 1 else ''})"
            )
    else:
        lines.append("_None._")
    lines.append("")

    if story.calendar_correlations:
        lines.append("## Patterns")
        lines.append("")
        for c in story.calendar_correlations:
            lines.append(f"- {c.description}")
        lines.append("")

    lines.append("## Goals")
    lines.append("")
    if story.goals_status:
        emoji = {"ok": "✓", "warning": "⚠", "violated": "✗"}
        for g in story.goals_status:
            lines.append(f"- {emoji.get(g.state, '?')} **{g.description}** — {g.message}")
    else:
        lines.append("_No active goals. Set one with `python -m core.cli goal add ...`_")
    lines.append("")

    needs_attention = []
    if story.uncategorized_count > 0:
        needs_attention.append(
            f"{story.uncategorized_count} payment(s) need categorization"
        )
    if story.anomalies:
        crit = sum(1 for a in story.anomalies if a["severity"] >= 2)
        if crit:
            needs_attention.append(f"{crit} flagged anomal{'ies' if crit != 1 else 'y'}")
    if needs_attention:
        lines.append("## Needs your attention")
        lines.append("")
        for n in needs_attention:
            lines.append(f"- {n}")
        if story.anomalies:
            lines.append("")
            lines.append("### Anomalies")
            for a in story.anomalies[:5]:
                lines.append(f"- {a['title']}")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Optional LLM rephrase (OpenAI SDK)
# ---------------------------------------------------------------------------

def maybe_rephrase_opener(story: WeeklyStory, markdown: str) -> str:
    if not config.USE_LLM_NARRATOR:
        return markdown
    if not os.environ.get("OPENAI_API_KEY"):
        return markdown

    try:
        from openai import OpenAI
    except ImportError:
        return markdown

    lines = markdown.split("\n")
    if len(lines) < 3 or not lines[0].startswith("#"):
        return markdown
    title_line, blank1, opener = lines[0], lines[1], lines[2]
    rest = lines[3:]

    structured = json.dumps(story.to_dict(), default=str, indent=2)
    system_msg = (
        "You rephrase a one-sentence financial summary in a friendly, "
        "concise tone. STRICT RULES: only rephrase, do not invent numbers, "
        "names, or claims not present in the source. Keep it to 1–2 "
        "sentences. No emojis. No salutations. Output the prose only."
    )
    user_msg = (
        f"Original opener:\n{opener}\n\n"
        f"Source data (do not introduce numbers not in here):\n{structured}\n\n"
        "Rewrite the opener:"
    )

    try:
        client = OpenAI()
        resp = client.chat.completions.create(
            model=config.OPENAI_MODEL,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=200,
            temperature=0.4,
        )
        new_opener = (resp.choices[0].message.content or "").strip()
        if not new_opener:
            return markdown
        return "\n".join([title_line, blank1, new_opener] + rest)
    except Exception:
        return markdown


# ---------------------------------------------------------------------------
# Public entry: generate, render, save, emit event
# ---------------------------------------------------------------------------

def generate_and_save_weekly(
    end_date: datetime | None = None, *,
    db_path: Path | str | None = None,
) -> Path:
    """Compute story, render markdown, optionally rephrase, save to disk +
    agent_events. Returns the file path."""
    story = weekly_story(end_date, db_path=db_path)
    markdown = render_markdown(story)
    markdown = maybe_rephrase_opener(story, markdown)

    iso = story.period_end.isocalendar()
    label = f"{iso.year}-W{iso.week:02d}"
    config.STORIES_DIR.mkdir(parents=True, exist_ok=True)
    out_path = config.STORIES_DIR / f"{label}.md"
    out_path.write_text(markdown)

    with connect(db_path) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO agent_events
              (created_at, kind, payment_id, severity, title, explanation,
               payload_json, dedup_key)
            VALUES (?, 'weekly_story', NULL, 1, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                f"Weekly story: {label}",
                markdown,
                json.dumps(story.to_dict(), default=str),
                f"weekly_story:{label}",
            ),
        )
    return out_path

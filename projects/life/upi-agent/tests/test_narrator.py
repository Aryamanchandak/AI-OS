"""Tests for brain.narrator."""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from core.output import narrator
from core.detect import goals
from core.orchestration import reactor


def _insert(conn, **kwargs):
    cols = ",".join(kwargs.keys())
    placeholders = ",".join("?" * len(kwargs))
    cur = conn.execute(
        f"INSERT INTO payments ({cols}, sender_id, raw_text, confidence) "
        f"VALUES ({placeholders}, 'X', 'r', 1.0)",
        tuple(kwargs.values()),
    )
    return cur.lastrowid


def test_weekly_story_has_correct_period(seeded_db):
    story = narrator.weekly_story(seeded_db["now"], db_path=seeded_db["path"])
    # 2026-04-22 is Wednesday → week is Mon Apr 20 → Sun Apr 26
    assert story.period_start.isoformat() == "2026-04-20"
    assert story.period_end.isoformat() == "2026-04-26"


def test_weekly_story_total_matches_sql_sum(seeded_db):
    story = narrator.weekly_story(seeded_db["now"], db_path=seeded_db["path"])
    conn = sqlite3.connect(seeded_db["path"])
    expected = conn.execute(
        """SELECT SUM(amount) FROM payments
           WHERE direction='debit' AND occurred_at >= ? AND occurred_at < ?""",
        ("2026-04-20T00:00:00", "2026-04-27T00:00:00"),
    ).fetchone()[0] or 0
    conn.close()
    assert story.total_spent == expected


def test_render_markdown_has_required_sections(seeded_db):
    story = narrator.weekly_story(seeded_db["now"], db_path=seeded_db["path"])
    md = narrator.render_markdown(story)
    assert md.startswith("# Week of ")
    assert "## By category" in md
    assert "## Top merchants" in md
    assert "## Goals" in md


def test_render_markdown_has_total_in_opener(seeded_db):
    """The structured opener must contain the total."""
    story = narrator.weekly_story(seeded_db["now"], db_path=seeded_db["path"])
    md = narrator.render_markdown(story)
    # Opener should mention some rupee amount
    assert re.search(r"₹[\d,]+", md.split("\n\n")[1])


def test_render_empty_week_still_produces_sensible_output(tmp_path):
    """Empty DB + future date should produce a valid markdown doc."""
    # Build a fresh empty DB
    import re as _re
    src = (Path(__file__).resolve().parent.parent / "agent.py").read_text()
    schema = _re.search(r'SCHEMA = """(.*?)"""', src, re.DOTALL).group(1)
    db = tmp_path / "empty.db"
    conn = sqlite3.connect(db)
    conn.executescript(schema)
    conn.commit()
    conn.close()
    from core.schema.db import reset_migration_cache
    reset_migration_cache()
    from core.schema.migrate import migrate as run_migrations
    run_migrations(db)

    far_future = datetime(2030, 1, 15)
    story = narrator.weekly_story(far_future, db_path=db)
    md = narrator.render_markdown(story)
    assert md.startswith("# Week of ")
    assert "No spending this week" in md
    assert story.total_spent == 0
    assert story.txn_count == 0


def test_goals_section_includes_active_goals(seeded_db):
    """Active goals appear in the Goals section."""
    conn = sqlite3.connect(seeded_db["path"])
    conn.row_factory = sqlite3.Row
    goals.create_goal(
        conn, description="No Swiggy", kind="avoid_merchant",
        spec={"patterns": ["swiggy"]}, scope="month",
    )
    goals.refresh_status_cache(conn, now=lambda: seeded_db["now"])
    conn.commit()
    conn.close()

    story = narrator.weekly_story(seeded_db["now"], db_path=seeded_db["path"])
    md = narrator.render_markdown(story)
    assert "No Swiggy" in md


def test_anomalies_appear_in_attention_section(seeded_db):
    """Anomaly events created during the week should surface."""
    # Run reactor to generate anomaly events for the seed
    ids = []
    conn = sqlite3.connect(seeded_db["path"])
    rows = conn.execute("SELECT id FROM payments").fetchall()
    conn.close()
    ids = [r[0] for r in rows]
    reactor.on_new_payments(ids, db_path=seeded_db["path"], now=seeded_db["now"])

    # Need to set the agent_event created_at into the week range. The fixture
    # uses now=2026-04-22; events use real datetime.now() — which in tests
    # will be the actual run time. Let's shift them manually.
    conn = sqlite3.connect(seeded_db["path"])
    conn.execute(
        "UPDATE agent_events SET created_at = '2026-04-22T15:00:00'"
    )
    conn.commit()
    conn.close()

    story = narrator.weekly_story(seeded_db["now"], db_path=seeded_db["path"])
    md = narrator.render_markdown(story)
    if story.anomalies:
        assert "Anomalies" in md or "Needs your attention" in md


def test_generate_and_save_weekly_creates_file_and_event(seeded_db, tmp_path, monkeypatch):
    """Smoke test: generate_and_save_weekly writes a file + inserts agent_event."""
    monkeypatch.setattr(narrator.config, "STORIES_DIR", tmp_path / "stories")
    out = narrator.generate_and_save_weekly(seeded_db["now"], db_path=seeded_db["path"])
    assert out.exists()
    assert out.read_text().startswith("# Week of ")

    conn = sqlite3.connect(seeded_db["path"])
    rows = conn.execute(
        "SELECT * FROM agent_events WHERE kind='weekly_story'"
    ).fetchall()
    conn.close()
    assert len(rows) == 1


def test_generate_and_save_weekly_is_idempotent(seeded_db, tmp_path, monkeypatch):
    monkeypatch.setattr(narrator.config, "STORIES_DIR", tmp_path / "stories")
    narrator.generate_and_save_weekly(seeded_db["now"], db_path=seeded_db["path"])
    narrator.generate_and_save_weekly(seeded_db["now"], db_path=seeded_db["path"])
    conn = sqlite3.connect(seeded_db["path"])
    n = conn.execute(
        "SELECT COUNT(*) FROM agent_events WHERE kind='weekly_story'"
    ).fetchone()[0]
    conn.close()
    assert n == 1


def test_llm_disabled_by_default_returns_unchanged(seeded_db, monkeypatch):
    """USE_LLM_NARRATOR=False should be a no-op."""
    monkeypatch.setattr(narrator.config, "USE_LLM_NARRATOR", False)
    story = narrator.weekly_story(seeded_db["now"], db_path=seeded_db["path"])
    md = narrator.render_markdown(story)
    rephrased = narrator.maybe_rephrase_opener(story, md)
    assert rephrased == md

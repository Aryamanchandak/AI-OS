import subprocess
from datetime import datetime, timedelta, timezone
from .config import TERMINAL_STAGE
from .ledger import _conn, pending


def record_run_start(target: str) -> int:
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as conn:
        cur = conn.execute("INSERT INTO runs(target,started_at,status) VALUES(?,?,'running')", (target, now))
        return int(cur.lastrowid)


def record_run_end(run_id: int, seen: int, done: int, failed: int, status: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    with _conn() as conn:
        conn.execute(
            "UPDATE runs SET finished_at=?,items_seen=?,items_done=?,items_failed=?,status=? WHERE run_id=?",
            (now, seen, done, failed, status, run_id),
        )


def staleness_report(max_age_days: int = 3) -> dict:
    """Report items still outstanding for any target they are routed to.

    P7: staleness = unprocessed bronze older than the threshold, NOT "did the
    button fire recently." An item is outstanding if, for any target in its
    ROUTING, it has not reached that target's TERMINAL_STAGE with status='done'.
    This deliberately catches never-attempted items (zero processing rows) — the
    exact silent-failure case P7 exists to surface — which the old
    "has a non-done row" query missed.
    """
    now = datetime.now(timezone.utc)
    threshold = (now - timedelta(days=max_age_days)).isoformat()

    # content_hash -> captured_at, deduped across targets (an item routed to
    # both kg and vector must be counted once).
    outstanding: dict[str, str] = {}
    for target, stage in TERMINAL_STAGE.items():
        for item in pending(target, stage):
            if item.captured_at < threshold:
                outstanding[item.content_hash] = item.captured_at

    count = len(outstanding)
    oldest = min(outstanding.values()) if outstanding else None
    days = None
    if oldest:
        days = (now - datetime.fromisoformat(oldest)).days
    return {
        "count": count,
        "oldest_captured_at": oldest,
        "days": days,
    }


def check_staleness(max_age_days: int = 3) -> None:
    report = staleness_report(max_age_days=max_age_days)
    if report["count"] and report["days"] is not None:
        msg = f'{report["count"]} items uningested for {report["days"]}d'
        subprocess.run(["osascript", "-e", f'display notification "{msg}" with title "Raw Data"'], check=False)

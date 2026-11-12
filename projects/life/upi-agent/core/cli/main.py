"""
Core CLI: `python -m core.cli <subcommand>`.

Subcommands:
  migrate           explicit migration (auto-runs lazily; this is for ops)
  react             run reactor on all unprocessed payments
  react --payment-id N
  goal add ...
  goal list
  goal pause <id>
  goal end <id>
  goal check        re-evaluate active goals, refresh status cache
  story weekly [--week YYYY-Www]
  notify            show macOS notifications for severe unacked events
  stats             print event counts, active goals, uncategorized counts
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

from core import config
from core.detect import goals
from core.orchestration import reactor
from core.output import narrator
from core.notify import macos as notifier
from core.schema.db import connect
from core.schema.migrate import migrate as run_migrations


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_migrate(args: argparse.Namespace) -> int:
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    run_migrations(config.DB_PATH)
    print(f"Migrations applied to {config.DB_PATH}")
    return 0


def cmd_react(args: argparse.Namespace) -> int:
    if args.payment_id is not None:
        report = reactor.on_new_payments([args.payment_id])
    else:
        report = reactor.react_to_all_unprocessed()
    print(report.summary())
    if report.errors:
        print(f"  errors: {len(report.errors)}", file=sys.stderr)
        for e in report.errors[:5]:
            print(f"   - {e}", file=sys.stderr)
    return 0 if not report.errors else 1


def cmd_goal_add(args: argparse.Namespace) -> int:
    if args.kind == "avoid_merchant":
        if not args.pattern:
            print("ERROR: --pattern required for avoid_merchant", file=sys.stderr)
            return 2
        spec = {"patterns": list(args.pattern)}
    elif args.kind == "budget_cap":
        if not (args.category and args.amount):
            print("ERROR: --category and --amount required for budget_cap", file=sys.stderr)
            return 2
        spec = {
            "category": args.category, "amount": args.amount,
            "warn_at_pct": args.warn_at_pct or config.DEFAULT_BUDGET_WARN_PCT,
        }
    elif args.kind == "frequency_cap":
        if not (args.pattern and args.max_per_period):
            print("ERROR: --pattern and --max-per-period required for frequency_cap", file=sys.stderr)
            return 2
        spec = {"patterns": list(args.pattern), "max_per_period": args.max_per_period}
    else:
        print(f"ERROR: unknown kind {args.kind}", file=sys.stderr)
        return 2

    description = args.description or f"{args.kind}: {json.dumps(spec)}"
    with connect() as conn:
        gid = goals.create_goal(
            conn, description=description, kind=args.kind,
            spec=spec, scope=args.scope,
        )
    print(f"Created goal #{gid}: {description}")
    return 0


def cmd_goal_list(args: argparse.Namespace) -> int:
    with connect() as conn:
        rows = goals.list_goals(conn)
    if not rows:
        print("No goals.")
        return 0
    for g in rows:
        print(f"#{g['id']:>3}  [{g['status']:<7}]  {g['kind']:<15}  "
              f"{g['scope']:<6}  {g['description']}")
    return 0


def cmd_goal_pause(args: argparse.Namespace) -> int:
    with connect() as conn:
        goals.set_status(conn, args.goal_id, "paused")
    print(f"Goal #{args.goal_id} paused")
    return 0


def cmd_goal_end(args: argparse.Namespace) -> int:
    with connect() as conn:
        goals.set_status(conn, args.goal_id, "ended")
    print(f"Goal #{args.goal_id} ended")
    return 0


def cmd_goal_check(args: argparse.Namespace) -> int:
    with connect() as conn:
        goals.refresh_status_cache(conn)
        rows = conn.execute(
            """SELECT g.description, c.state, c.progress, c.message
               FROM goal_status_cache c
               JOIN goals g ON g.id = c.goal_id
               WHERE g.status = 'active'"""
        ).fetchall()
    for r in rows:
        print(f"  [{r['state']:<8}]  {r['description']}: {r['message']}")
    print(f"Refreshed {len(rows)} goal status entries.")
    return 0


def cmd_story_weekly(args: argparse.Namespace) -> int:
    end_date = None
    if args.week:
        try:
            year_str, w_str = args.week.split("-W")
            year = int(year_str)
            week = int(w_str)
            monday = datetime.fromisocalendar(year, week, 1)
            end_date = monday + timedelta(days=6, hours=20)
        except ValueError:
            print(f"ERROR: bad --week format {args.week!r}; expected YYYY-Www",
                  file=sys.stderr)
            return 2
    out_path = narrator.generate_and_save_weekly(end_date)
    print(f"Story written to {out_path}")
    return 0


def cmd_notify(args: argparse.Namespace) -> int:
    n = notifier.notify_severe()
    print(f"Showed {n} notifications.")
    return 0


def cmd_stats(args: argparse.Namespace) -> int:
    with connect() as conn:
        events_by_kind = dict(conn.execute(
            "SELECT kind, COUNT(*) FROM agent_events GROUP BY kind"
        ).fetchall())
        active_goals = conn.execute(
            "SELECT COUNT(*) FROM goals WHERE status='active'"
        ).fetchone()[0]
        uncat = conn.execute(
            "SELECT COUNT(*) FROM payments "
            "WHERE direction='debit' AND category IS NULL"
        ).fetchone()[0]
        rec = conn.execute(
            "SELECT COUNT(*) FROM recurring_payments"
        ).fetchone()[0]
        total_payments = conn.execute(
            "SELECT COUNT(*) FROM payments"
        ).fetchone()[0]

    print(f"Total payments         : {total_payments}")
    print(f"Active goals           : {active_goals}")
    print(f"Recurring patterns     : {rec}")
    print(f"Uncategorized debits   : {uncat}")
    print(f"Events by kind:")
    for k, n in sorted(events_by_kind.items()):
        print(f"  {k:<22} {n}")
    return 0


# ---------------------------------------------------------------------------
# Argparse wiring
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="core.cli", description="UPI agent core CLI.")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("migrate", help="run schema migrations").set_defaults(fn=cmd_migrate)

    react = sub.add_parser("react", help="run reactor on payments")
    react.add_argument("--payment-id", type=int, default=None,
                       help="run reactor for a single payment id")
    react.set_defaults(fn=cmd_react)

    goal = sub.add_parser("goal", help="goal management")
    gsub = goal.add_subparsers(dest="goal_cmd", required=True)

    gadd = gsub.add_parser("add", help="add a goal")
    gadd.add_argument("--kind", required=True,
                      choices=["avoid_merchant", "budget_cap", "frequency_cap"])
    gadd.add_argument("--scope", required=True, choices=["week", "month", "custom"])
    gadd.add_argument("--description", default=None)
    gadd.add_argument("--pattern", action="append", default=None,
                      help="(repeatable) merchant pattern, lowercased substring")
    gadd.add_argument("--category", default=None, help="for budget_cap")
    gadd.add_argument("--amount", type=float, default=None, help="for budget_cap")
    gadd.add_argument("--warn-at-pct", type=int, default=None,
                      help="for budget_cap, default 80")
    gadd.add_argument("--max-per-period", type=int, default=None,
                      help="for frequency_cap")
    gadd.set_defaults(fn=cmd_goal_add)

    glist = gsub.add_parser("list", help="list all goals")
    glist.set_defaults(fn=cmd_goal_list)

    gpause = gsub.add_parser("pause", help="pause a goal")
    gpause.add_argument("goal_id", type=int)
    gpause.set_defaults(fn=cmd_goal_pause)

    gend = gsub.add_parser("end", help="end a goal")
    gend.add_argument("goal_id", type=int)
    gend.set_defaults(fn=cmd_goal_end)

    gcheck = gsub.add_parser("check", help="re-evaluate active goals")
    gcheck.set_defaults(fn=cmd_goal_check)

    story = sub.add_parser("story", help="generate stories")
    ssub = story.add_subparsers(dest="story_kind", required=True)
    sweek = ssub.add_parser("weekly", help="generate weekly story")
    sweek.add_argument("--week", default=None,
                       help="YYYY-Www format, e.g. 2026-W17")
    sweek.set_defaults(fn=cmd_story_weekly)

    sub.add_parser("notify", help="show notifications for severe events").set_defaults(fn=cmd_notify)
    sub.add_parser("stats", help="print agent statistics").set_defaults(fn=cmd_stats)

    return p


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())

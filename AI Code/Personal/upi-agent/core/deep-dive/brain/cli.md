# cli.py — Technical Documentation

**Last updated:** 2026-05-03
**Lines of code:** 252
**Language:** Python

---

## What This File Does (Plain English)

This file is the command-line interface for the brain layer. It exposes every brain capability as a subcommand under `python -m brain.cli`. It wires together `argparse`, calls the appropriate module function, and returns an exit code. It is the primary way to manually trigger ingestion processing, manage goals, generate weekly stories, and inspect system state.

---

## How It Actually Works

### Entry Points

- `python -m brain.cli <subcommand>` — executed via the module `__main__` path (the `if __name__ == "__main__": sys.exit(main())` block).
- `main()` — called by the `__main__` block. Parses args, dispatches to the right `cmd_*` function.

### Data Flow

```
main()
  → _build_parser()    # creates the full argparse tree
  → parser.parse_args()
  → args.fn(args)      # dispatch to cmd_* function
  → sys.exit(return_code)

Each cmd_* function:
  → validates args
  → calls one brain module function
  → prints result to stdout
  → returns 0 (success) or 1-2 (error)
```

### Subcommands

| Subcommand | Handler | What it does |
|---|---|---|
| `migrate` | `cmd_migrate` | Runs `migrate.migrate(DB_PATH)` explicitly — useful for ops/setup |
| `react` | `cmd_react` | Calls `reactor.on_new_payments([id])` or `reactor.react_to_all_unprocessed()` |
| `react --payment-id N` | `cmd_react` | Same, scoped to one payment ID |
| `goal add --kind K --scope S ...` | `cmd_goal_add` | Calls `goals.create_goal()` with assembled spec |
| `goal list` | `cmd_goal_list` | Prints all goals with status, kind, scope, description |
| `goal pause <id>` | `cmd_goal_pause` | Calls `goals.set_status(id, 'paused')` |
| `goal end <id>` | `cmd_goal_end` | Calls `goals.set_status(id, 'ended')` |
| `goal check` | `cmd_goal_check` | Calls `goals.refresh_status_cache()`, prints current states |
| `story weekly` | `cmd_story_weekly` | Calls `narrator.generate_and_save_weekly()` |
| `story weekly --week YYYY-Www` | `cmd_story_weekly` | Parses week label → Sunday datetime, calls narrator |
| `notify` | `cmd_notify` | Calls `notifier.notify_severe()` |
| `stats` | `cmd_stats` | Queries counts from all brain tables, prints summary |

### Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Reactor ran with errors (some payments failed) |
| 2 | Invalid arguments |

### Key Functions / Classes

| Name | What it actually does |
|---|---|
| `cmd_migrate(args)` | Creates DB path, runs migrations, prints confirmation |
| `cmd_react(args)` | Runs reactor; prints summary; exits 1 if any errors |
| `cmd_goal_add(args)` | Validates required args per kind, assembles spec dict, creates goal |
| `cmd_goal_list(args)` | Prints all goals (all statuses) in a tabular format |
| `cmd_goal_pause(args)` | Sets one goal to 'paused' |
| `cmd_goal_end(args)` | Sets one goal to 'ended' |
| `cmd_goal_check(args)` | Refreshes status cache, prints current evaluation for all active goals |
| `cmd_story_weekly(args)` | Generates weekly story; handles `--week` date parsing |
| `cmd_notify(args)` | Triggers macOS notifications for unacknowledged severe events |
| `cmd_stats(args)` | Prints counts of payments, goals, recurring patterns, uncategorized debits, events by kind |
| `_build_parser()` | Constructs the full argparse tree; all subcommands and their arguments |
| `main()` | Parses args, dispatches, returns exit code |

### External Dependencies

- `argparse`, `json`, `sys`, `datetime`, `pathlib` (stdlib)
- `brain.config`, `brain.goals`, `brain.reactor`, `brain.narrator`, `brain.notifier`
- `brain.db.connect`
- `brain.migrate.migrate` (imported as `run_migrations`)

### Error Handling

- `cmd_react()` returns exit code 1 if `report.errors` is non-empty; up to 5 errors are printed to stderr.
- `cmd_goal_add()` returns exit code 2 with an error message on missing required args (validation is manual, not via argparse `required=True` on conflicting combinations).
- `cmd_story_weekly()` returns exit code 2 if `--week` format is invalid.
- All other commands let exceptions propagate — a crash in `goals.create_goal()` or `narrator.generate_and_save_weekly()` would produce a Python traceback and exit code 1 (Python default).

---

## Non-Technical Decisions Embedded in the Code

- `--pattern` for goal add is `action="append"` — it can be specified multiple times (e.g., `--pattern swiggy --pattern zomato`). This results in a list that is stored directly as `spec["patterns"]`.
- The `--week` argument for `story weekly` is parsed manually (splitting on `"-W"`) rather than using a date parsing library. If the format is wrong, `ValueError` is caught and a 2 exit code is returned with a descriptive message.
- `cmd_story_weekly()` constructs the Sunday of the given ISO week by adding 6 days to Monday and setting the hour to 20:00, which passes the `_resolve_end_date()` check in the narrator (Sunday after 18:00).
- `cmd_stats()` uses `dict(conn.execute(...).fetchall())` to build the events-by-kind dict. This works because `fetchall()` returns tuples `(kind, count)` which `dict()` can consume directly.
- `cmd_goal_list()` shows all goals regardless of status — including paused and ended goals. There is no filtering option.

---

## Honest Gaps and Risks

- **Argument validation for `goal add` is manual and partial.** `argparse` does not enforce cross-argument dependencies (e.g., `--category` is required for `budget_cap` but not checked by argparse). The validation is done in `cmd_goal_add()` with if-checks, but `--warn-at-pct` for `budget_cap` is silently defaulted to `config.DEFAULT_BUDGET_WARN_PCT` if omitted — this is correct but could surprise a user who forgets to set it.
- **`cmd_goal_add()` does not validate that `--category` is a known category.** Passing `--kind budget_cap --category "Junk Food"` creates a goal with a category that the classifier will never assign. The goal will always show 0% progress.
- **`cmd_goal_list()` has no `--status` filter flag.** A user with many ended goals cannot show only active ones from the CLI.
- **`cmd_react()` does not call `notifier.notify_severe()` after processing.** The user must manually run `python -m brain.cli notify` after `react` to see macOS notifications for newly generated events.
- **`cmd_stats()` is a read-only inspection command with no structured output (JSON/CSV).** It prints to stdout in human-readable format only, making it difficult to use in scripts or monitoring.

---

## Developer Notes

- Each `cmd_*` function is bound to its subcommand via `set_defaults(fn=cmd_*)`. The `args.fn(args)` dispatch in `main()` relies on this pattern. Every new subcommand must call `set_defaults(fn=...)` or `main()` will raise `AttributeError`.
- `_build_parser()` is separated from `main()` for testability — tests can call `_build_parser().parse_args(["react", "--payment-id", "1"])` without running `sys.exit`.
- The `goal` subcommand uses a nested `add_subparsers()` call. The `dest="goal_cmd"` is set but the dispatch still goes through `args.fn` — `goal_cmd` is present in `args` but unused in dispatch.
- When adding a new subcommand: (1) write a `cmd_<name>(args)` handler, (2) add a `sub.add_parser("name", ...)` block in `_build_parser()`, (3) call `.set_defaults(fn=cmd_<name>)` on the new parser.

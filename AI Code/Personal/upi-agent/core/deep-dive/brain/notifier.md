# notifier.py — Technical Documentation

**Last updated:** 2026-05-03
**Lines of code:** 88
**Language:** Python

---

## What This File Does (Plain English)

This file shows macOS Notification Center alerts for high-severity brain events. It queries `agent_events` for unacknowledged events with severity >= 2, then calls `osascript` to display a notification for each one (up to 5 at a time). It silently does nothing on non-Mac systems or if `osascript` fails. It is a best-effort decoration layer — the `agent_events` table is always the authoritative record.

---

## How It Actually Works

### Entry Points

- `notify_severe(db_path=None)` — called by `cli.py notify`. Returns count of notifications shown.

### Data Flow

```
notify_severe(db_path)
  → connect(db_path)
  → SELECT id, kind, title, explanation, severity FROM agent_events
    WHERE severity >= 2 AND acknowledged = 0
    ORDER BY created_at DESC LIMIT 5
  → close connection
  → for each row:
      _osascript(title="UPI Agent", subtitle=kind, body=row["title"])
          → if sys.platform != 'darwin': return False
          → escape backslashes and double-quotes in all strings; truncate to 240 chars
          → subprocess.run(["osascript", "-e", script], timeout=5)
          → return True if returncode == 0
      if ok: shown += 1
  → return shown
```

### State Management

No mutation. The function reads events but does not mark them as acknowledged or update any DB state. The comment in the code explicitly acknowledges this: "we don't ack on the user's behalf; we just won't repeat within the same run."

### Key Functions / Classes

| Name | What it actually does |
|---|---|
| `notify_severe(db_path)` | Fetches up to 5 high-severity unacked events and shows macOS notifications |
| `_osascript(title, subtitle, body)` | Constructs and runs an AppleScript `display notification` command; returns True on success |

### External Dependencies

- `subprocess`, `sys`, `shlex` (stdlib — `shlex` is imported but not used)
- `brain.db.connect`
- macOS `osascript` binary — must be present at `/usr/bin/osascript`

### Error Handling

- `sys.platform != 'darwin'` check: silently returns `False` on Linux/Windows.
- `subprocess.TimeoutExpired` and `FileNotFoundError` are caught; return `False`.
- `check=False` on `subprocess.run()` — non-zero exit codes from osascript are not raised, just returned as `returncode`.
- No error handling around the DB query — if `agent_events` doesn't exist yet (fresh install before migrations), this would raise an `OperationalError`.

---

## Non-Technical Decisions Embedded in the Code

- Notifications are capped at 5 per call. If there are 20 unacknowledged severe events, only the 5 most recent are shown. There is no way to page through the rest except running `notify_severe()` again (which would show the same 5 until they are acknowledged).
- The body of the notification uses `row["title"]` (the short one-liner), not `row["explanation"]` (the longer paragraph). This is intentional — notification bodies have limited display space.
- `shlex` is imported but never used. It was likely included in anticipation of shell-escaping the osascript command, but the implementation uses subprocess list form (`["osascript", "-e", script]`) which doesn't need shell escaping.
- Notifications may repeat across agent runs because `acknowledged` is never set by this module. The comment says this is acceptable because the launchd cadence is daily. If the agent is run more than once a day without the user acknowledging events in the dashboard, the same events will be notified again.
- The 240-character truncation on each field (`[:240]`) is hardcoded, not in `config.py`.

---

## Honest Gaps and Risks

- **No acknowledgment tracking.** Events are not marked as notified. On a daily launchd schedule, each event with severity >= 2 will appear in every daily notification batch until the user acknowledges it in the dashboard. For a user who never uses the dashboard, this could mean the same anomaly notification appears every day indefinitely.
- **`shlex` is imported but unused.** Dead import — minor cleanliness issue.
- **The `notify_severe()` function opens and closes the DB connection before iterating rows.** The rows are fetched, connection closed, then osascript is called. This is correct — no DB writes are needed during notification. But it means the "at most 5" cap is based on the DB state at the moment of the query, which could be stale by the time notifications are shown if another process inserts events concurrently (unlikely in practice).
- **No filtering by event recency.** `notify_severe()` will surface an unacknowledged severity-2 event from six months ago if the user has never acknowledged it. The `ORDER BY created_at DESC LIMIT 5` means the 5 newest are shown, but old unacknowledged events remain queryable.
- **osascript timeout is 5 seconds.** If macOS is slow to process the notification (e.g., Do Not Disturb is on and queuing), the subprocess may time out and return `False`, logging no notification even though one may appear later.

---

## Developer Notes

- The only write path for `acknowledged` is in the dashboard (`dashboard.py` presumably has an acknowledge endpoint). Until `acknowledged` is set to 1, `notify_severe()` will keep picking up the same events.
- To extend notifications to other platforms, add a branch in `_osascript()` for `sys.platform == 'linux'` using `notify-send` or similar.
- If you want to track which events have been notified (to avoid repeats without requiring user acknowledgment), add a separate `notified` boolean column to `agent_events`, or use a separate table. The current design deliberately avoids this to keep the module simple.
- The `notify_severe()` signature accepts `db_path` for testability — in tests you can pass an in-memory or temp DB path. But since it reads from `agent_events`, the DB must have migrations applied first.

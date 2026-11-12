# 09 — Scheduling and Recovery

[Back to macro](00-macro.md) · Status: exploration draft

## Scheduled execution

Define start time, timezone, allowed execution window, and behavior when a scheduled start is missed. A system scheduler can launch the controller. The controller then processes the queue until there is no eligible work or a configured limit is reached.

The host must remain awake and connected. Choose a local always-awake setup or an always-on runner. Remote execution also requires repository, dependencies, authentication, and permission configuration.

### v1: your laptop (Oct 10, D-41, D-42)

- **Run window per plan**, set in the UI ([16](16-plan-ui.md)). Times in IST; you will confirm which time is best for usage. Examples: overnight from 00:00 (to 09:00 is 9 hours), or 9 AM–3 PM when you can keep an eye on it (best for browser verification).
- **Start:** you press start before bed with a delayed start time; the controller waits. No scheduled wake-up and no system settings changed.
- **Keep awake only for the run:** `caffeinate -i -w <controller PID>`. It ends when the controller exits. With the lid shut the Mac sleeps whatever the time (heat, battery); the run freezes and continues when the lid opens.
- **Pause / Resume** buttons, any time. Pause stops the agent process (its session is kept); Resume reopens the same session with “continue”.
- **Visible:** each node runs in script mode in a visible Terminal window you can toggle to (D-39).
- **Later:** a Mac mini or server removes the laptop constraints ([17](17-later.md) L19).

## Readiness and human-gated work

Plans are hardened during the day ([14](14-plan-refinement-and-local-backlog.md)); the night run revalidates baseline and setup at start. Dispatch only authorized queued items whose automated/human dependency gates are met. Revised Oct 9 (D-29): a product decision discovered at night does not pause anything; the agent interprets, proceeds, and records it for the report. Provisional continuation is recorded explicitly. Before human edits to a candidate, pause its writer or use a separate correction worktree; reconcile revised checkpoints before resuming.

## Usage limits: wait and continue (D-25, replaces most of C7)

The rule is deliberately simple: **when Claude or Codex hits its usage limit, wait for the reset, then tell it to continue.** No complex recovery state.

1. **Detect.** The agent CLI exits or reports a usage-limit message. The controller recognises the message per vendor (check the exact wording and exit codes for each CLI when implementing).
2. **Save.** The controller commits whatever is in the workspace as a work-in-progress commit, so nothing is lost while waiting.
3. **Find the reset time.** Read it from the limit message when the vendor states it. If not, check every 15 minutes (configurable) whether the agent works again.
4. **Wait.** The plan's status becomes `paused` with reason `usage reset` (C10), shown in the UI with the expected reset time.
5. **Continue.** After the reset, the controller resumes the **same session** and sends “continue”. This is the automated version of typing continue yourself; headless CLIs support resuming a session by ID (verify exact flags: Claude Code `--resume`, Codex `exec resume`).
6. **Fallback.** If the session cannot be resumed, start a fresh session with the plan, the WIP commit, and a short note of what the stage was doing.

It counts against neither repair rounds nor retries. The plan waits for the reset; the end-of-window policy below decides only whether a fixed stop time overrides the wait.

**Why waiting is enough for now:** the night pipeline is mostly sequential (Claude implements, then Codex reviews), so when one agent is blocked the pipeline is waiting on it anyway. Spreading work roughly evenly across the two vendors means both limits are used at a similar rate.

**Deferred ([17](17-later.md) L10):** actively managing remaining usage, for example giving a big task to whichever agent has more usage left, or letting the other vendor continue where a blocked one stopped.

### Weekly limits (Oct 10, D-43)

After each plan, the controller checks weekly usage for both vendors, from the same source as your existing tracking system (to point us to). At **95% or more** it stops, **unless the weekly reset is tomorrow**, in which case it uses up what's left. The next run continues from where it was cut off. A short-window limit never stops the run and never triggers a write-up-and-stop: it is always wait and continue.

**Still required:** before relying on subscription logins for unattended runs, check each vendor's terms on automated use and record the result in [11](11-decisions-and-exploration.md). Your view (Oct 10): the agents run in your own terminal on your laptop under your account, visible if you toggle to them, which is no different from setting it up by hand, and Databricks builds around it. Still worth one check.

## Minimal state

For v1 the controller keeps one small status file per plan run: run date, plan ID and revision, current stage, the vendor session ID per agent (what makes “continue” work, D-40), last commit, repair count, and status (including `paused: usage reset` and the reset time, `paused: you` from the Pause button or window end, `paused: permission denied`, and `stopped: weekly limit`). That is enough to wait, continue, and report. No SQL.

Deferred until the simple version proves insufficient (full original text in [17](17-later.md) L8–L9): transactional store (SQLite), append-only event log, full restart reconciliation, locking across concurrent controllers, and per-stage idempotency. If the controller itself crashes, restart the current stage from the last commit.

Keep two simple limits: a per-node timeout of **2 hours**, not counting time waiting for a reset or paused (D-52), and the repair limit (**2**, D-46). Each node runs in its own process group; the whole group is killed when the node ends, so dev servers and watchers don't pile up (D-52). A permission prompt or question from an agent must never hang the run. Revised Oct 9 (D-29): if an agent asks a question, the controller answers “interpret, proceed, and record your interpretation” and the stage continues. A permission prompt (the sandbox refusing an action) is not a question. Revised Oct 10 (D-50): a **permission reviewer** (Claude's auto mode or `--permission-prompt-tool`; for Codex an equivalent hook or a small reviewer of our own, using a cheap model) approves truly safe actions. If it denies one, the denial is logged and the **plan pauses and waits for you**, with a macOS notification. Only a stage timeout stops a stage; its work is committed and reported.

## End-of-window policy

Interaction with D-25: a plan waiting for a usage reset keeps waiting until the reset unless this policy says the run must stop by a set time; in that case it stops with the WIP commit preserved and reported.


**v1 (Oct 10, D-41):** at the end of the plan's run window the agents **pause** (process stopped, sessions kept, work committed); you press Resume when you want them to carry on, for example once you're at the office. A plan waiting for a usage reset at window end simply stays paused.

Choose whether to finish the current stage, checkpoint and stop, or terminate after a grace period. Report any partial work and keep it recoverable. A failed plan should hold its dependents while independent eligible plans may continue.

## Exploration

- What time and timezone should the initial schedule use? **→ Oct 10:** set per plan in the UI, IST; you will confirm the best time for usage (D-41).
- Local Mac or remote runner? **→ Oct 10:** your laptop for v1; Mac mini or server later (L19).
- What should happen after a missed schedule?
- Should the run stop at a fixed morning deadline? **→ Oct 10:** it pauses at window end; Resume continues (D-41).
- How should you receive a completion report? **→ Oct 10:** the morning summary file (D-53); no remote notifications for now (L19).
- Where does your existing usage tracker read weekly usage from? (D-43)

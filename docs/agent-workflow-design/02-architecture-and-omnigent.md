# 02 — Architecture and Omnigent

[Back to macro](00-macro.md) · Status: v1 direction settled (D-38 to D-56) · Rewritten Oct 10 with review comments built in

## Architecture (v1)

```text
UI: plans, run window, sandbox, working folder (16)
                    |
   Controller: a simple Python loop + one status file per run
      |               |                  |
  run_claude()     run_codex()      test runner (plain shell, no AI)
  (claude -p)      (codex exec)
      \               /
   Run clone: one per run, plans stack on each other, controller commits after each node
   Tests clone: Codex's independent tests, never visible to Claude → copied into a check folder only by the controller
```

Each agent node runs in **script mode** in a **visible Terminal window** on your laptop, so you can toggle to it and watch (D-39).

## Controller (D-38)

The v1 controller is a simple Python loop. It may grow into a simple agent loop later, but it stays a loop. It owns only these things:

| Responsibility | What it does |
| --- | --- |
| Scheduling | Starts each plan inside its **run window**, set per plan in the UI (D-41) |
| Feeding plans | Runs all queued plans **one after another**. Plan N+1 starts only after plan N is confirmed done, on top of its commits (D-44) |
| Running the tests | After the agent says done, runs the test command itself. This is a plain shell command with no AI usage, and the result is recorded (D-46) |
| Repair | Only if that run fails: round 1 Codex, round 2 Claude, then stop (D-46) |
| Usage limits | Short window: waits for the reset, then sends “continue”. Weekly: see below (D-43) |
| Pause / Resume | At window end or on your Pause button, stops the agent process and keeps its session. Resume reopens the same session with “continue” (D-41) |
| Keeping the Mac awake | Only for the run (D-42) |
| Committing | Commits after every node (D-44) |
| Morning summary | Writes one short file (D-53) |

**What it does not do in v1:**
- no stage state machine
- no per-stage prerequisites or completion gates
- no allowed-action lists
- no SQL or versioned state

Claude and Codex decide how to work inside the plan, and the plan defines its inputs and outputs. **“Done” is when the agent says done**; the controller's own test result is recorded beside it.

### Telling “ended” from “done” (D-51)

A script-mode run that ends has not necessarily finished. The controller classifies every ending:

| Ending | Action |
| --- | --- |
| Done | Commit, run tests, move to the next node |
| Usage limit hit | Commit work in progress, wait for the reset, resume the same session with “continue” |
| Stopped to ask a question | Reply “interpret, proceed, and record your interpretation”, up to N times (D-29) |
| Action denied by the permission reviewer | Log it, pause the plan, notify you, and wait (D-50) |
| Node runs past 2 hours | Stop, commit, record. Time waiting for a reset or paused doesn't count (D-52) |

### Run window, sleep, and Pause/Resume (D-41, D-42)

- **Run window:** set per plan in the UI, in IST. Examples: overnight from 00:00 to 09:00 (9 hours), or 9 AM–3 PM when you can keep an eye on it. You'll confirm which time is best for usage. At the end of the window the agents **pause**, and **Resume** carries on later, for example from the office. Pause and Resume work at any time.
- **Start:** press Start before bed with a delayed start time; the controller waits.
- **Sleep:**
  - The run is wrapped in `caffeinate -i -w <controller PID>`, so the Mac stays awake only while the controller runs.
  - With the lid shut the Mac sleeps, whatever the time, to avoid heat and battery drain.
  - No system power settings are changed, and there is no scheduled wake.
- **Later:** a Mac mini or server removes these laptop constraints ([17](17-later.md) L19).

### Usage limits (D-25, D-43)

- **Short-window limit:** never stops the run and never triggers a write-up-and-stop. The controller reads the reset time from the limit message, or polls if the message doesn't give one. It then waits and resumes the same session with “continue”.
- **Weekly limit:** after each plan, check both vendors' weekly usage from the same source your existing tracking system uses.
  - At **95% or more**, stop, **unless the weekly reset is tomorrow**; in that case use up what's left.
  - The next run continues from where it was cut off.
- Usage information is for the controller only. It isn't shown in your reports.

### Processes (D-52)

Each node runs in its own process group. When the node ends, the whole group is killed, so dev servers, test watchers and MCP servers that agents started don't pile up and use RAM. Script-mode CLIs exit by themselves, so there are no terminals to clean up.

### Status file (D-40)

There is one small file per run, and no SQL. It holds:

- run date
- plan ID and revision
- current node
- **vendor session ID** per agent (what makes “continue” work)
- last commit
- repair round
- status: `running`, `paused: usage reset` (with the reset time), `paused: you`, `paused: permission denied`, `stopped: weekly limit`, `done`, or `failed`

## Agent adapter (D-40)

There are **two plain functions, `run_claude()` and `run_codex()`**, and no shared abstraction.

**Inputs:**
- a predefined role
- the plan it executes (the allowed scope is the plan, nothing open-ended)
- the workspace it is given
- where to write its change receipt

Every node starts a **new session**.

**Invocation:**
- Claude: `claude -p … --output-format json`
- Codex: `codex exec … --json`

**Fields read from the result:**
- status
- vendor session ID
- whether a usage limit was hit, and the reset time if stated

**Resume:**
- Claude: `claude --resume <id>`
- Codex: `codex exec resume <id>`

These two commands are why the session ID is stored.

**Vendor-specific handling:** only what differs between the two vendors: the resume command, the wording of the limit message, and the JSON shape.

**Output:** Claude's **change receipt**, written where the prompt says. It records what was written where and leads with interpretations. The plan defines the rest of the output, and the next plan picks up from there. There are no artifact references and no extra structured results (L22).

**Standing prompt line** in every fix and missing-test prompt: “Do not edit, delete, or skip existing tests. If you believe a test is wrong, say so in your change receipt.” (D-47)

### Why script mode, not driving the interactive app (D-39)

| | Interactive app driven by the controller | Script mode in a visible window (chosen) |
| --- | --- | --- |
| You can watch | Yes | Yes, output streams live |
| You can type mid-run | Yes | No; use Pause/Resume |
| Controller knows done / limit / question | Has to read the screen; fragile | Clean JSON result |
| Documented for automation | No | Yes, by both vendors |

Both options run on your laptop, in your terminal, under your account, and you can watch them. Script mode is the vendors' documented automation route. Still to do once: check each vendor's terms on automated use of a subscription.

v1 is CLI only. An SDK or app-server integration becomes worth it later for live streaming into the UI, handling permissions in code, or running as a server service ([17](17-later.md) L16).

## Sandbox (v1)

The realistic risk is an accident, not malware: deleting the wrong folder, a force-push, editing another repository, touching `~/.ssh`. Agents can do whatever the plan needs inside these limits:

- **One separate clone per run** (D-44), apart from your own working folder. This matters most when a run happens in the daytime while you're editing. Plans stack inside it.
- **No push credentials.** You review, merge and push.
- **Hidden tests** (D-45):
  - Codex's tests live in a **separate clone**, not a worktree. A worktree shares `.git`, so `git log --all` would reveal the tests.
  - Claude's settings deny reads of that path.
  - The controller copies the tests into a check folder only.
- **Permission reviewer** (D-50), which approves actions that are truly safe so fewer things block a run:
  - Claude Code: its auto mode, or `--permission-prompt-tool`.
  - Codex: an equivalent hook if `codex exec` has one (to verify); otherwise a small reviewer of our own.
  - It uses a cheap model. When unsure it denies and logs the action, the plan pauses, and you're notified.
  - It also reduces blocked browser verification, such as Codex driving Chrome.
- **Not in v1:** the container and the controller's path check ([12](12-sandboxing-and-access.md), [17](17-later.md) L21). Every change is still visible because the controller commits after every node.

## Omnigent (D-55)

Omnigent provides programmatic session execution and lifecycle management through a CLI, a Python SDK, and REST interfaces. The project is too simple to need it as a platform, so v1 does **not** depend on it, run it, or fork it.

It stays on the to-do list as a **source to borrow from as and when required**, provided the license allows. Check the license, and keep the required notices on anything copied. Look at its session lifecycle code first (resume, limit handling, continue) before writing ours; borrowing may be more efficient ([17](17-later.md) L23).

| Option | Benefit | Tradeoff | v1 |
| --- | --- | --- | --- |
| Direct Codex and Claude adapters | Small dependency surface | Maintain two vendor integrations | **Chosen**, borrowing code from Omnigent where useful |
| Omnigent-backed adapter | Reuse session and harness infrastructure | Operate and track an additional platform | No |
| Fork Omnigent | Change internals where necessary | Maintain a fork and reconcile upstream | No |

## Language

**Python.** v1 needs `subprocess`, `json`, `time`, a status file, and `caffeinate`, and you know Python. TypeScript would only help if the UI became a web app, and Python can serve that too.

## Before building: daytime dry run (D-54)

Run one trivial plan end to end in the daytime before the first real run. Confirm:

- the exact flags and JSON fields
- the wording of each vendor's limit message and reset time
- the resume commands
- how permission denials are reported, and whether Codex has an approval hook
- where weekly usage is read from
- the `caffeinate` and lid-shut behaviour
- vendor terms

## Not in v1

- SDK or app-server integration (L16)
- point 3: stacking plans when verification is blocked or tests still fail (L17)
- remote monitoring, Mac mini, server (L19)
- container and path check (L21)
- richer structured results (L22)

All of these are in [17](17-later.md).

## Sources

Documentation consulted on October 8, 2026; re-check exact flags and fields during the dry run:

- [Codex non-interactive execution](https://learn.chatgpt.com/docs/non-interactive-mode)
- [Codex SDK](https://learn.chatgpt.com/docs/codex-sdk)
- [Claude Code programmatic execution](https://code.claude.com/docs/en/headless)
- [Omnigent programmatic usage](https://omnigent.ai/docs/programmatic)
- [Omnigent repository](https://github.com/omnigent-ai/omnigent)

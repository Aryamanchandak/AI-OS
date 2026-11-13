# Assignment 10 — status and handoff

Stopped at a clean point. Code is complete and wired in; one of three tasks
has been verified end-to-end. The rest is blocked on environment, not code.

## Where things are

Everything lives in `Assignment 10/code/`, which is a copy of the Session 9
catalogue (`Assignment 9/_extract/b/S9SharedCode/code/`) with the new skill
added, so it genuinely "drops into" the catalogue rather than sitting beside it.

```
code/computer/
  skill.py       the cascade — read this first, it owns layer ordering
  driver.py      Layer 2b (AX + text LLM) and Layer 3 (vision), shared loop
  ax.py          macOS accessibility tree (the OS analogue of browser/dom.py)
  cdp.py         the page tool — CDP over electron_debugging_port
  input.py       clicks, typing, hotkeys, AppleScript
  screen.py      screenshot + set-of-marks annotation
  recorder.py    start_recording + trajectory writing
  tasks.py       the three task definitions
  run.py         runner + per-task environment setup + preflight
  targets/canvas_game.html   self-contained canvas target for the vision task
```

Catalogue integration (mirrors how `browser` is wired):
- `schemas.py` — added `ComputerOutput`, plus `permission_denied` and
  `app_unavailable` error codes
- `agent_config.yaml` — added the `computer:` entry
- `skills.py` — added the `if skill.name == "computer"` dispatch branch
- `prompts/computer.md` — the skill's prompt/metadata contract

## The layer map

| Layer | Mechanism | Cost |
|---|---|---|
| 1 — extract | AX text read | no LLM |
| 2a — deterministic | hotkey sequence / AppleScript | no LLM |
| 2c — page | CDP over `electron_debugging_port` | no LLM |
| 2b — ax | AX tree + text LLM | text call per turn |
| 3 — vision | annotated screenshot + vision LLM | vision call per turn |

2c sits below 2b by number but is *tried before it*, because for an Electron
target a real DOM read beats walking a huge, largely unnamed Chromium AX tree.
The number reflects kinship with Layer 1 (structured, no model); the ordering
reflects cost. `_plan_layers()` in `skill.py` is the only place that ordering
is decided.

## Task status

| Task | Layer | Constraint | State |
|---|---|---|---|
| `vscode` | 2c page | Electron path | **PASSING**, verified end-to-end |
| `calculator` | 2a | zero vision | code done, never run — needs Accessibility |
| `canvas` | 3 | vision | code done, never run — needs both grants + gateway |

The passing run is at
`code/state/trajectories/vscode_20260720_003425/` — `manifest.json` reports
`resolved_at_layer: page`, `vision_calls: 0`, and the layer artifacts are in
`layer_2c_page/`.

## What you need to do to finish

### 1. Grant macOS permissions (blocks 2 of 3 tasks)

```
System Settings → Privacy & Security → Accessibility    → enable your terminal
System Settings → Privacy & Security → Screen Recording → enable your terminal
```

Grant to whichever app runs the script (Terminal / iTerm / Cursor), then
**restart that app** — macOS only re-reads the grant at process start.

Check with:
```bash
cd "Assignment 10/code" && ../.venv/bin/python -m computer.run --preflight
```

### 2. Start the V9 gateway (blocks layers 2b and 3)

Nothing is listening on `localhost:8109`. The `canvas` task cannot run without
it, because Layer 3 routes every vision call through the gateway. `calculator`
does **not** need it — Layer 2a never calls a model, which is the whole point
of that task.

### 3. Run the tasks

```bash
cd "Assignment 10/code"
../.venv/bin/python -m computer.run calculator
../.venv/bin/python -m computer.run canvas
../.venv/bin/python -m computer.run            # all three + constraint check
```

The runner prints a CONSTRAINTS block at the end that checks the assignment's
three requirements against what actually ran, not against what was intended.

## Known issues to fix

1. **`manifest.json` reports `turns: 0` on the passing run** even though the
   skill returned `turns=1`. `rec.finish()` is called without the `turns`
   argument in `skill.py`, so it falls back to the default. Cosmetic, but it
   is in the submitted evidence, so worth fixing.

2. **`layers_attempted` under-reports.** Layer 1 returns its "escalate" note
   *before* calling `rec.enter_layer()` when Accessibility is missing, so it
   never appears in the manifest. Once the grant is in place this resolves
   itself for real runs, but the ordering in `_layer_extract` is still wrong
   and should call `enter_layer` first.

3. **Only `vscode` has been run.** The other two paths are written but
   unexercised — expect to find something. The AX-dependent verification in
   `calculator` (reading `611` back off the display) is the most likely place
   for a surprise, since it depends on how Calculator exposes its display
   value via `AXStaticText`.

## Open question worth resolving

The brief says "five-layer architecture" and names `start_recording`, the
`page` tool, and `electron_debugging_port` — but none of those exist anywhere
on disk. `grep -r` across the whole course tree (including `.venv`) matches
them **only in `Assignment.md`**, and there is no Session 10 / Lecture 13
folder.

So the layer map above and the `start_recording` signature are **my design**,
built to the names the brief uses. They are reasonable and self-consistent,
but if the Session 10 spec turns up and defines these differently, the
adapting is mostly renaming: the cascade shape should survive, and
`_plan_layers()` plus `recorder.py` are the two files that would change.

## Deliberate design choices worth keeping

- **Verification is independent of the model.** A driver's `done(success=true)`
  is only a claim. `_verify()` in `skill.py` re-reads state out of the
  application (via AppleScript) and requires a match. The canvas game sets its
  window title on a real hit, so the check costs no vision call and a model
  cannot mark its own homework.
- **Per-layer trajectory subdirs make constraints self-evidencing.** "Zero
  vision calls" is provable by the *absence* of `layer_3_vision/` plus
  `vision_calls: 0`, rather than something a grader takes on trust.
  `vision_calls` moves in exactly one place (`Recorder.note_llm_call`).
- **The Electron task never touches your running editor.** It launches a
  separate instance with its own `--user-data-dir`, because the alternative —
  quitting the editor you are working in — is not an acceptable side effect
  of running a test.
- **No guessing at the deterministic layer.** Layer 2a only fires when the
  caller supplies `keys` or `applescript`, the same discipline the browser
  skill applies to selectors. Guessing there would recreate exactly the
  brittleness Layer 2b exists to absorb.

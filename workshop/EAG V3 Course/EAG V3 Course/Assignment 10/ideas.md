# Assignment 10 — Computer-Use Skill: Implementation Ideas

## Open dependency (blocks implementation, not design)

The brief names three APIs — `start_recording`, the `page` tool, and
`electron_debugging_port` — plus a "five-layer architecture". None of these
exist anywhere on disk:

- `grep -r` across the whole course tree (including `.venv/` site-packages)
  matches these three names **only in `Assignment.md` itself**.
- No Session 10 / Lecture 13 folder exists (we have Lectures 3, 4, 7, 11, 12).
- No computer-use library is installed in the venv.

So the Session 10 spec is missing. We need it to know whether we *wrap* a
provided library or *implement* the tools to its spec — either way the exact
API surface has to come from the spec, not from guesswork.

Everything below is framework-agnostic and holds regardless.

## The "five-layer" mapping — one label is unverified

The Session 9 browser skill (`browser/skill.py:6-9`) shows **four** labels:

| Layer | Browser skill | Proposed OS analogue |
|---|---|---|
| 1 | HTML extract, trafilatura, no LLM | Electron/CDP `page` — structured extract, no vision |
| 2a | Deterministic selectors | Deterministic hotkeys / AppleScript |
| 2b | A11yDriver — text LLM | macOS AX tree + cheap text LLM |
| 3 | SetOfMarks — vision | Screenshot + vision |

The fifth is plausibly the Electron `page` path as the OS analogue of Layer 1,
but this is a guess. Confirm against the Session 10 definition before writing
the layer labels into the code — the brief grades on "cascade discipline
visible in the code", so the labels matter.

## Task selection — 1:1 onto the three constraints

Three constraints (≥1 vision, ≥1 Electron-page, ≥1 zero-vision) map onto
exactly three tasks, no redundancy, each landing at a different layer:

1. **Calculator via deterministic hotkeys (2a)** → the **zero-vision** task.
   Arithmetic through keystrokes; verify by reading the result field. No LLM
   in the hot path at all, which makes the "zero vision calls" claim trivially
   auditable in the trajectory.

2. **Electron app via `page` + `electron_debugging_port`** → the
   **Electron-page** task. VS Code is the lowest-friction target (we already
   drive it). Something like: open a file, edit a known line, save.

3. **Small browser game / canvas (Layer 3)** → the **vision** task. Canvas has
   no ARIA, so the cascade genuinely exhausts 1 → 2a → 2b and *has* to escalate
   — which is the point. Far lower friction than Figma desktop.

Reasonable swap: replace (1) with a **spreadsheet/notes task via AX tree (2b)**
if you'd rather showcase the text-LLM layer. It's also zero-vision, so all
three constraints still hold.

Skip the multi-app workflow — highest execution risk, and it satisfies no
constraint we can't get more cheaply.

## macOS feasibility flags

These have to actually run on darwin, so:

- **Electron**: the target must be launched with `--remote-debugging-port=NNNN`.
  Expect to relaunch VS Code with the flag before the page tool can attach —
  worth scripting so runs are reproducible.
- **AX tree (2b)**: the controlling process needs Accessibility permission
  granted in System Settings. Grant it once, up front.
- **Vision**: budget for screenshot scaling; a small browser game keeps the
  viewport predictable.

## Integration — mirror `BrowserSkill` exactly

The browser skill is the template. Same shape:

- `computer/skill.py` — a `ComputerSkill` owning the cascade, with the same
  `_pack` / `_pack_driver` / `_pack_error` packers and the same escalation
  rule (a layer escalates when its output is empty or evidently insufficient;
  stop at the first layer that produces a useful answer).
- `ComputerOutput` in `schemas.py`, alongside `BrowserOutput`.
- Register in `agent_config.yaml`, and add a dispatch branch in `skills.py`
  next to `if skill.name == "browser"` (`skills.py:297`).
- Keep a `force_path` escape hatch like the browser skill's
  (`skill.py:154`) — it's how you prove vision escalation in a smoke test
  when the natural cascade would short-circuit earlier.

## Trajectories are part of the design, not an add-on

The trajectory directory *is* the submitted evidence. Wire `start_recording`
to write under `state/sessions/<id>/computer/`, mirroring how `artifacts_root`
is threaded in `skills.py:311`. Follow the browser skill's per-layer subdir
convention (`skill.py:249-255`) so turn artifacts from one layer don't
overwrite another's — with three tasks across different layers, that collision
is otherwise likely.

Per-layer subdirs also make the constraints self-evidencing: "zero vision
calls" is provable by the *absence* of a vision subdir in task 1's trajectory,
rather than something a grader has to take on trust.

## Suggested order

Electron (2) first — it has the most environmental setup and will surface
framework-API questions earliest. Then Calculator (1), which is nearly pure
determinism. Then vision (3), which is the least predictable and benefits from
the harness being settled by then.

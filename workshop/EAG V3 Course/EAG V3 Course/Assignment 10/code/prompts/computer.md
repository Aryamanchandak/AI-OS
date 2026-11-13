# Computer-Use skill

You drive macOS applications on behalf of the orchestrator.

The skill owns a five-layer cascade and picks the cheapest layer that can
actually resolve the goal:

| Layer | Mechanism | Cost |
|---|---|---|
| 1 — extract | Accessibility text read | no LLM |
| 2a — deterministic | hotkey sequence / AppleScript | no LLM |
| 2c — page | CDP over `electron_debugging_port` | no LLM |
| 2b — ax | Accessibility tree + text LLM | text call/turn |
| 3 — vision | Annotated screenshot + vision LLM | vision call/turn |

You do not choose the layer; the cascade does. What you choose is the
**metadata**, and that determines which layers are eligible:

- `app` (required) — the macOS application name, exactly as it appears in
  the menu bar.
- `goal` (required) — what to accomplish, in one sentence.
- `keys` — a list of keystrokes. Supplying this enables Layer 2a. Only
  supply it when the sequence is genuinely deterministic; a guessed
  sequence that half-works is worse than none, because it leaves the app in
  an unknown state before the later layers start.
- `applescript` — an AppleScript body, the other Layer 2a form.
- `electron_debugging_port` — the app's remote debugging port. Supplying
  this enables the page tool, which is both cheaper and sturdier than the
  accessibility tree for Electron targets.
- `expect` — a string that must appear on screen (or in the page DOM) after
  the action. This is the verification gate: without it, a layer can only
  report that it *ran*, not that it *worked*.
- `read_only` — the goal is a question about current state, not a change.
- `force_path` — pin a single layer. Use only for demonstrating a specific
  layer; it disables the cascade.

Always supply `expect` when the goal changes state. A task that cannot be
verified has not been completed, only attempted.

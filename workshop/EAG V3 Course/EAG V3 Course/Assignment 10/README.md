# Assignment 10 — macOS Computer-Use Skill

Status: code and offline checks are prepared. Current driver-backed live runs,
submission trajectories, and the YouTube demo are pending; historical runs are
not presented as evidence for the updated implementation.

The skill extends the Session 9 catalogue. Goal decomposition is the existing
Planner's job: it emits one computer node per app-level subgoal. Perception
interpretation uses the driver's accessibility tree or a labelled window image.
Action sequencing performs one action and re-scans. Error recovery uses fresh
observations and bounded turns; permission/app failures require human setup.
Vision fallback calls the bundled V9 gateway when structured controls cannot
locate the target. These are the lecture's five architectural responsibilities.

The cost cascade tries extraction, caller-supplied hotkeys, the Electron page
branch, text judgment over accessibility, then vision. Calculator must compute
47 × 13 = 611 using hotkeys and zero model calls. The Electron task reads the
active s10_marker.txt tab in a separate Cursor/VS Code profile through page.
The canvas task locates the orange square with vision and independently checks
the bound window title for CANVAS-GAME: HIT. No assignment task forces a path.

Prepare from this folder with Python 3.11.15:
```sh
uv sync --project code --frozen --python 3.11.15
uv sync --project llm_gatewayV9 --frozen --python 3.11.15
uv run --project code --frozen python scripts/prepare_driver.py
uv run --project code --frozen python -m pytest code/tests -q
uv --directory code run --frozen python -m computer.run --dry-run
```
Create a root .env using .env.example and a Gemini free-tier credential/model.
Never commit credentials. All model requests use V9; desktop actions use the
pinned driver behind computer/backend.py. The 0.5.2 release archive reports
binary version 0.5.1; preparation checks the release archive's SHA256.

When the computer is available, start the driver and grant its permissions:
```sh
open -n -g .tools/cua-driver-rs-0.5.2-darwin-universal/CuaDriver.app --args serve
.tools/cua-driver-rs-0.5.2-darwin-universal/CuaDriver.app/Contents/MacOS/cua-driver permissions grant
uv --directory llm_gatewayV9 run --frozen python main.py
```
Keep the gateway terminal open. In another terminal, run --preflight, then
calculator, vscode, and canvas individually with python -m computer.run from
code/. Finally run all three with no task argument. Each run displays an agent
cursor; record at least one live run for the YouTube demo (provided by Aryaman).

Evidence is written to evidence/trajectories, outside ignored runtime state.
From code/, run uv run --frozen python -m computer.evidence before submission.
It checks all three manifests, native trajectories, counters and postconditions.
Offline tests use a fake desktop and never count as submission evidence.
Fixed failure modes include stale action indices, unsupported multiplication
keys, false model success, mismatched counters, occupied debug ports, and silent
recording failures. Live OS behaviour and model availability remain unverified.

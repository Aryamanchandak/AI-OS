# AI OS

Connected agents behind one gateway. `plan/` is the source of truth for what gets built and in what order; this page only says where things go.

## Where things go

- `core/` — trunk. The shared code every agent uses: `llm.py` (model client, I1), `store.py` (database, I2), `registry.py` (tool list, I3). One file per job.
- `leaves/<name>/` — one folder per agent. Its code, prompts (`prompts/`), eval cases (`<file>.evals.yaml` beside the file they test) and nothing else. Deletable.
- `gateway/` — trunk. The service every model call goes through. Its own project, environment and tests.
- `ingestion/` — the capture pipeline. Its own project, environment and tests.
- `shell/` — the web UI.
- `tests/` — `contracts/` holds one test per interface in `plan/interfaces.md`; `fakes/` holds stand-ins for modules not built yet; `test_structure.py` enforces the rules below.
- `plan/` — stages, interfaces, node plans, `DECISIONS.md`.
- `workshop/` — every earlier project and idea, kept as raw material. Code is pulled from here into `core/` or a leaf; nothing live imports from it.
- `Database/` — data files. Not in git.

## Rules the tests enforce

- `core/` never imports from `leaves/`.
- A leaf never imports another leaf; it calls that leaf's tool through the registry.
- Only `core/llm.py` reaches a model, and only through the gateway.
- Every file in `core/` and `leaves/` starts with a one-line description.

## Run the tests

- Core and leaves: `uv run pytest` here.
- Gateway: `uv run pytest` in `gateway/`.
- Ingestion: `uv run pytest` in `ingestion/`.

Rebuild any environment with `uv sync --python 3.11.15`.

# Comparison DAG Agent

Compare 2–12 options on shared criteria using supplied evidence or live research.
Every result retains values, units, exact passages, sources, dates and limitations.
The Planner emits independent evidence branches. The Executor's new generic `context: true` mechanism lets tools receive upstream outputs; it has no comparison-specific dispatch.

## Try it

From this folder, run (requires uv; Python 3.11.15 is selected explicitly):

```bash
./compare --request examples/service-plans.yaml --prioritise cost --chart cost
./compare --request examples/architecture-notes.yaml
./compare --request examples/local-projects.yaml
```

The first two examples are labelled illustrative fixtures. The third reads actual local project files.
Results go into a private `sessions/<run-id>/` folder: `answer.md`, `comparison.json`, `run.json`, checkpoints and optional charts.

## Natural-language comparisons

Copy `.env.example` to `.env` and set `ANTHROPIC_API_KEY` for direct Claude API access.
The launcher loads `.env` before Python starts; it accepts trusted shell-style `KEY=value` assignments.
`ANTHROPIC_MODEL` selects the model. No gateway server, AI OS installation, shared configuration or shared database is required.

```bash
./compare "Compare these three service plans for a small team" --source first.md --source second.md --source third.md
./compare "Compare SQLite, PostgreSQL and DuckDB for a local analytics tool"
./compare --follow-up RUN_ID "Focus on deployment simplicity"
```

Live mode frames the question, asks for clarification when necessary, retrieves supplied/public sources, extracts exact passages and labels model interpretation as inference. Public search can be blocked; supply URLs or files if needed. Live model quality still requires a run with your provider key.

## Revise or resume

```bash
./compare --request examples/service-plans.yaml --reuse RUN_ID --weight cost=1
./compare --request examples/service-plans.yaml --pause-after 1 --session checkpoint-demo
./compare --resume checkpoint-demo
```

`--reuse` explicitly reuses evidence snapshots; omit it for fresh retrieval. Edit the request to add options/criteria, use `--exclude ID`, or change `--prioritise ID`. Unknown dates, conflicting values and incompatible scopes/units block best-value claims. Numerical weights are never chosen by the model. Hard constraints exclude failing options from weighted rankings.

## Checks and assignment evidence

Run `./compare test -q`. Existing portfolio tests and saved historical logs remain; the originals are under `../Previous Implementations/`. `./compare --portfolio --mock --degrade AMD "compare NVDA, AMD and INTC"` demonstrates Critic repair with scripted model responses. `--agent` exposes the general Planner path; `--state DIR` and `--resume DIR` save/resume it. Live generated Python requires human review; its subprocess is not a security sandbox.

Limits: text/Markdown/CSV/JSON/YAML/Python/TOML files and readable public HTML, up to 2 MB per source; no PDF/OCR or authenticated browsing. Only explicit conversions in `units.yaml` are applied; no inferred exchange rates. Passage matching verifies provenance, not source truth or analytical quality. Saved evidence is local and ignored by Git. Automated source/interpretation failures stop the run and preserve its checkpoint.

Assignment submission remains incomplete: live base-query runs and exact course bounds, patched starter compatibility, and the YouTube demo are not yet verified. Historical logs are not evidence of this version's live performance.

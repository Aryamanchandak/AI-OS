# Steelman Generator

Steelman Generator reconstructs the strongest coherent world in which a claim could be correct, then exposes the premises that world depends on and grades its empirical support. The artifact is a typed argument graph; prose is only a rendering of it.

This repository implements the full pipeline described in `Ideas.md`, with deterministic local equivalents wherever an external system is unavailable:

- canonical claim surgery and stable claim hashes;
- dual typed premise graphs for the claim and its negation;
- evidence-aware verification and mandatory downgrade warnings;
- named-proponent tracking with an explicit `CONSTRUCTED — no real proponent located` state;
- a generic, configurable forensic-accounting SA01–SA15 review pack;
- SQLite persistence with graph-shaped tables and JSON export;
- deterministic offline operation and an optional OpenAI construction provider;
- a local Streamlit interface and automated tests.
- six parallel argumentative frames across the claim and its negation;
- a Red/Blue hardening loop, retreat paths, enforced budget parity, and blinded ordering;
- crux extraction, dated threshold predictions, preregistration, resolution, and calibration scoring;
- rubric-gated bounded regeneration and a visible DAG execution log;
- rates/macro, credit, and forensic-accounting domain packs;
- a local second-order cascade adapter, configurable Neo4j export, and evaluation harnesses;
- desktop graph inspection and a responsive swipeable card-stack render.

## Quick start

Python 3.11 or newer is required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
streamlit run app.py
```

The default deterministic mode needs no credentials and no network access. It is deliberately conservative: empirical premises remain unsupported until the evidence supplied by the user matches them.

To use model-assisted premise construction:

```bash
export OPENAI_API_KEY='your-key'
streamlit run app.py
```

Choose `openai` in the sidebar. The model defaults to `gpt-4.1-mini` and can be changed there. Keys are read only from the environment and are never persisted.

Set a different local database path if desired:

```bash
export STEELMAN_DB='/path/to/steelman.db'
streamlit run app.py
```

## Product workflow

### Full deliberation

Use **Full deliberation** for the complete dual pipeline. Choose a domain pack and Red/Blue round count. The app fans six frames across both sides concurrently, enforces identical token/search reservations, randomizes the blinded judge order from a stable seed, extracts up to three cruxes, preregisters predictions, and runs the rubric gate. If the gate misses its threshold, one bounded regeneration/hardening pass runs automatically and the result remains honestly marked if evidence is still missing.

### Claim analysis

1. Enter a claim, scope, and time horizon.
2. Add zero to five sources. A source needs a title and relevant excerpt; advocate, URL, publisher, tier, and stance add provenance.
3. Run the reconstruction.
4. Review the claim card, graph, evidence grades, downgrade warnings, and JSON export.

Source excerpts are treated as user assertions, not independently fetched or authenticated. `primary` and `secondary` mean the user-selected evidence tier. Always open the original source before making a decision.

### Forensic review

1. Choose a generic SA01–SA15 flag.
2. Record the observed signal.
3. State the strongest benign management explanation.
4. Record management-supporting evidence and residual risk.
5. Request escalation if warranted.

The gate blocks escalation when the benign case is insubstantial, management-supporting evidence has not been considered, residual risk is absent, or the evidence grade is not selected. The generic flag catalog is a configurable review scaffold, not an accounting standard or investment recommendation.

To replace the placeholder catalog, copy `config/sa_flags.json`, edit the names and prompts while preserving exactly one definition for each code SA01 through SA15, and set:

```bash
export STEELMAN_FORENSIC_FLAGS='/path/to/your/sa_flags.json'
```

The application validates the entire custom catalog before showing the forensic workflow.

## Testing

```bash
pytest
```

Tests cover canonical hashes, claim splitting, verification, forensic gates, SQLite round trips, all six frames, dual budget parity, Red/Blue retreat paths, cruxes, predictions, rubric regeneration, tracker calibration, evaluation harnesses, local cascade analysis, and Neo4j query generation.

## Neo4j

SQLite remains the zero-configuration default. To mirror a graph into Neo4j:

```bash
pip install -e '.[neo4j]'
```

Instantiate `Neo4jGraphStore(uri, username, password)` and call `save_graph(graph)`. The adapter is dependency-optional and accepts an injected driver for offline tests.

## Project map

- `app.py` — Streamlit entry point.
- `src/steelman/claim.py` — canonical claim surgery.
- `src/steelman/models.py` — typed domain models.
- `src/steelman/graph.py` — deterministic premise graph construction.
- `src/steelman/providers.py` — deterministic and OpenAI construction providers.
- `src/steelman/verification.py` — evidence matching, grades, and downgrade rules.
- `src/steelman/forensics.py` — generic SA01–SA15 definitions and escalation gate.
- `config/sa_flags.json` — editable default SA01–SA15 catalog.
- `src/steelman/storage.py` — SQLite graph-shaped persistence.
- `src/steelman/pipeline.py` — end-to-end orchestration and prose rendering.
- `src/steelman/deliberation.py` — full DAG, frame fan-out, dual parity, hardening, cruxes, predictions, and rubric.
- `src/steelman/domains.py` — general, rates/macro, credit, and forensic lenses.
- `src/steelman/integrations.py` — local mirfish-equivalent cascade analysis and Neo4j adapter.
- `src/steelman/evaluation.py` — ideological-voice and held-out resolved-dispute harnesses.
- `ARCHITECTURE_DECISIONS.md` — choices, rationale, tradeoffs, assumptions, and full-scope implementation details.

## Important boundaries

The complete pipeline has a working local path, but the app does not pretend local heuristics are external facts. It does not authenticate supplied source excerpts or make accounting/investment judgments. Live model and Neo4j adapters require their respective credentials/services. Local mirfish and decision-tracker contracts are implemented in-process because no external contracts were present.

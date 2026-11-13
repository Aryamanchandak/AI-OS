# Project Integration Plan

## Goal

Combine the two projects into one maintainable repository while preserving them as separate components:

- The DAG agent remains the general orchestration system.
- The causal scenario engine remains a deterministic, fixed pipeline.
- The agent accesses causal analysis through one high-level tool.
- Both applications continue to work independently.

## Phase 1 — Preserve the current state

- [ ] Make a backup or create a Git repository before moving files.
- [ ] Confirm the existing test baselines:
  - DAG agent: `58 passed`
  - Causal engine: `8/8 passed`
- [ ] Record example outputs from both applications.
- [ ] Do not include generated files in the restructuring:
  - `.venv/`
  - `__pycache__/`
  - `.pytest_cache/`
  - machine-specific `.claude/settings.local.json`
- [ ] Preserve existing assignment logs and artifacts.

## Phase 2 — Create the target structure

Use a structure similar to:

```text
assignment-8/
├── pyproject.toml
├── README.md
├── .gitignore
│
├── apps/
│   ├── agent_cli/
│   │   └── main.py
│   └── causal_streamlit/
│       └── main.py
│
├── packages/
│   ├── dag_agent/
│   │   ├── executor.py
│   │   ├── planner.py
│   │   ├── execution_graph.py
│   │   ├── recovery.py
│   │   ├── sandbox.py
│   │   ├── skills.py
│   │   ├── tools.py
│   │   └── llm/
│   │
│   └── causal_engine/
│       ├── causal_graph.py
│       ├── extract.py
│       ├── propagate.py
│       ├── synthesize.py
│       └── service.py
│
├── config/
│   └── agent_config.yaml
│
├── prompts/
│   ├── agent/
│   └── causal/
│
├── tests/
│   ├── dag_agent/
│   ├── causal_engine/
│   └── integration/
│
├── artifacts/
├── logs/
└── docs/
```

## Phase 3 — Move the projects without changing behaviour

### DAG agent

- [ ] Move the CLI entry point into `apps/agent_cli/`.
- [ ] Move the `agent/` package into `packages/dag_agent/`.
- [ ] Move its prompts and configuration into their new locations.
- [ ] Update imports and prompt paths.
- [ ] Rename ambiguous models:
  - `Graph` → `ExecutionGraph`
  - `Node` → `ExecutionNode`
- [ ] Run all 58 tests.

### Causal engine

- [ ] Rename `What If Analyser ?` to a shell-safe name.
- [ ] Move the Streamlit entry point into `apps/causal_streamlit/`.
- [ ] Move the reusable logic into `packages/causal_engine/`.
- [ ] Rename ambiguous models:
  - `Graph` → `CausalGraph`
  - `Node` → `CausalNode`
  - `Edge` → `CausalEdge`
- [ ] Keep `propagate()` pure and free from LLM or UI dependencies.
- [ ] Run all eight propagation checks.

Do not integrate the projects during this phase. First prove that moving them did not change their behaviour.

## Phase 4 — Unify dependency management

- [ ] Add a root `pyproject.toml`.
- [ ] Declare all direct dependencies, including:
  - `anthropic`
  - `google-genai`
  - `networkx`
  - `streamlit`
  - `pandas`
  - `pydantic`
  - `python-dotenv`
  - `PyYAML`
  - `matplotlib`
  - `pytest`
- [ ] Separate development dependencies from runtime dependencies.
- [ ] Create one root `.gitignore`.
- [ ] Remove the committed or copied virtual environment.
- [ ] Confirm both applications can run from a clean environment.

## Phase 5 — Define the causal engine’s public interface

Create one stable entry point in `causal_engine/service.py`, for example:

```python
def analyse_situation(
    situation: str,
    *,
    include_narratives: bool = True,
) -> CausalAnalysisResult:
    ...
```

The returned result should contain structured data:

```text
CausalAnalysisResult
├── source_situation
├── causal_graph
├── scenarios
│   ├── name
│   ├── uncertainty_assignment
│   ├── outcomes
│   └── narrative
└── sensitivity
```

- [ ] Keep Streamlit-specific objects out of this interface.
- [ ] Do not return preformatted tables or UI components.
- [ ] Make results JSON-serializable.
- [ ] Preserve outcome traces and contested flags.
- [ ] Add tests for this public interface.

## Phase 6 — Decide the LLM-provider boundary

The two projects currently use different providers.

### Recommended initially: keep both providers

- [ ] Keep Claude behind the DAG agent’s existing LLM adapter.
- [ ] Keep Gemini internal to causal extraction and synthesis.
- [ ] Pass provider clients into functions where practical.
- [ ] Avoid global API-client construction.
- [ ] Document both required environment variables.

This creates less migration risk.

### Optional later: introduce a common provider protocol

```python
class StructuredLLM:
    def generate_text(...): ...
    def generate_structured(...): ...
```

Only do this if there is a real need to swap providers. Avoid forcing provider-specific structured-output behaviour into an overly generic abstraction.

## Phase 7 — Expose causal analysis as an agent tool

Add a `causal_analysis` tool to the DAG agent.

The tool should:

1. Receive the situation text.
2. Call `causal_engine.service.analyse_situation()`.
3. Return structured JSON.
4. Allow the formatter to create the final user-facing answer.

The agent should treat the entire causal pipeline as one task:

```text
Planner
   │
   ▼
causal_analysis tool
   │
   ├── extract graph
   ├── propagate four scenarios
   ├── synthesize narratives
   └── calculate sensitivity
   │
   ▼
Formatter
```

- [ ] Register the tool in the existing tool registry.
- [ ] Add it to `agent_config.yaml`.
- [ ] Add a focused prompt if the skill system requires one.
- [ ] Do not copy causal propagation into the executor.
- [ ] Do not make each causal node an execution-graph node.
- [ ] Do not modify the generic executor unless a genuinely new runtime mechanism is required.

## Phase 8 — Add integration tests

Create tests for:

- [ ] The planner selecting the causal-analysis skill.
- [ ] A situation reaching the causal service unchanged.
- [ ] The tool returning valid JSON.
- [ ] Exactly four scenarios being returned.
- [ ] Every outcome retaining its trace.
- [ ] The formatter receiving the structured result.
- [ ] Causal failures being reported cleanly.
- [ ] Parallel scenario synthesis remaining concurrent.
- [ ] Existing portfolio-comparison behaviour remaining unchanged.
- [ ] Both standalone applications continuing to work.

Use a fake causal extractor and fake narrative generator so integration tests do not require live API calls.

## Phase 9 — Improve the Streamlit application

After the backend integration is stable:

- [ ] Make Streamlit call the causal service rather than individual modules.
- [ ] Optionally add an “Agent-assisted analysis” mode.
- [ ] Preserve the direct causal-analysis mode for predictable results.
- [ ] Keep the scenario table as the primary result.
- [ ] Continue exposing graph details, traces, and sensitivity information.
- [ ] Display provider or API errors without losing the user’s input.

## Phase 10 — Documentation

Create a root README explaining:

- [ ] What each component does.
- [ ] Why execution graphs and causal graphs remain separate.
- [ ] How to install dependencies.
- [ ] How to configure Claude and Gemini credentials.
- [ ] How to run the CLI agent.
- [ ] How to run the Streamlit application.
- [ ] How to run all tests.
- [ ] Where logs and artifacts are stored.
- [ ] Which parts satisfy the original assignment.

Keep the original assignment evidence available under `docs/assignment/` or an equivalent location.

## Recommended order of execution

1. Back up and establish the test baseline.
2. Create the repository structure.
3. Move the DAG agent.
4. Run its tests.
5. Move the causal engine.
6. Run its tests.
7. Add unified dependency management.
8. Create the causal service interface.
9. Add the agent tool.
10. Add integration tests.
11. Update Streamlit.
12. Update documentation.
13. Run the complete regression suite.

## Definition of done

The integration is complete when:

- Both original test suites pass.
- New integration tests pass.
- The CLI agent still handles the existing portfolio demonstrations.
- The Streamlit causal analyser still works independently.
- The agent can invoke causal analysis through one tool.
- `ExecutionGraph` and `CausalGraph` remain separate models.
- `propagate()` remains deterministic and LLM-free.
- No virtual environments, caches, secrets, or machine-specific settings are tracked.
- A clean checkout can be installed and run using the root project configuration.

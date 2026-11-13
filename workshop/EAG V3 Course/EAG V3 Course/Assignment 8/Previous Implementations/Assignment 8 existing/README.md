# DAG Agent — Portfolio Comparison

A planner/executor/critic agent for equity-comparison queries. The Planner
emits a DAG, the Executor runs independent nodes concurrently, and the Critic
gates flagged producers before any successor may run.

```text
Planner ──emits──▶ Graph ──▶ Executor ──▶ concurrent DAG layers
                                │
                                ├─ flagged producer ──▶ Critic ──pass──▶ successor
                                │                          │
                                │                         fail
                                │                          ▼
                                └── recovery classifier ──▶ Planner recovery plan
                                                              │
                                                    splice into running graph
```

## Submission status

| Part | Requirement | Status | Evidence |
|---|---|---|---|
| 1 | Five supplied base queries (`hello`, `A`, `I`, `J`, `K`) verbatim and within their named bounds | **External input required** | Exact queries and bounds were not included in the assignment file; see the checklist below |
| 2 | Three-way parallel fan-out; layer wall-clock tracks max rather than sum | **Done** | [parallel run log](logs/part2_parallel.json), [controlled timing tests](tests/test_parallel.py) |
| 3 | Critic pass and fail; failed run splices recovery and returns a corrected answer | **Done** | [pass log](logs/part3_critic_pass.json), [fail-and-recover log](logs/part3_critic_fail.json), [integration test](tests/test_assignment_evidence.py) |
| 4 | Working Coder prompt and computation the Formatter cannot reliably perform | **Done** | [Coder run log](logs/part4_coder.json), [Coder prompt](prompts/coder.md) |
| 5 | New YAML-plus-prompt skill exercised without an Executor change | **Done** | [Charter run log](logs/part5_charter.json), [generated chart](artifacts/comparison.png), [skill config](agent_config.yaml), [prompt](prompts/charter.md) |
| Demo | YouTube demonstration of Parts 1–5 | **External input required** | **TODO: add YouTube URL after recording** |

## Setup

```bash
python3 -m pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
```

Run with the configured model:

```bash
python3 main.py "compare NVDA, AMD and INTC over the last year"
```

Every architecture demonstration also works without an API key through
`--mock`. Mock mode uses the scripted roles in `agent/mock_llm.py`; it proves
the scheduling, Critic gate, recovery splice, sandbox execution, and artifact
flow, but is never represented as model output.

## Architecture

| File | Responsibility |
|---|---|
| `agent_config.yaml` | Skill catalogue: one YAML entry plus one prompt file per skill |
| `prompts/*.md` | Planner, Critic, Coder, Formatter, Retriever, and Charter contracts |
| `agent/planner.py` | Emits the initial graph and Planner-authored recovery subgraphs |
| `agent/graph.py` | Validates the DAG, computes Kahn layers, and splices recovery nodes |
| `agent/executor.py` | Runs layers concurrently and places the Critic gate before successors |
| `agent/recovery.py` | Pure Critic-reason-to-strategy classifier |
| `agent/sandbox.py` | Executes Coder and Charter Python in a subprocess |
| `agent/tools.py` | Implementations for `runtime: tool` skills |

The Executor knows only three generic runtimes:

- `llm`: render prompt, call the model, return text
- `sandbox`: ask the model for Python, execute it, return stdout and artifacts
- `tool`: dispatch to a registered deterministic function

It contains no `coder`, `charter`, `retriever`, or other skill-specific branch.

## Part 1 — Base queries

The brief refers to five queries from an external session by label only. Their
exact text, maximum iterations, and maximum wall-clock are absent from
`Assignment.md`; inventing them would violate the “verbatim” requirement.

Before submission, paste the supplied values here and generate the five logs:

| Label | Exact query | Iteration bound | Wall-clock bound | Log |
|---|---|---:|---:|---|
| hello | **TODO** | **TODO** | **TODO** | `logs/part1_hello.json` |
| A | **TODO** | **TODO** | **TODO** | `logs/part1_A.json` |
| I | **TODO** | **TODO** | **TODO** | `logs/part1_I.json` |
| J | **TODO** | **TODO** | **TODO** | `logs/part1_J.json` |
| K | **TODO** | **TODO** | **TODO** | `logs/part1_K.json` |

This is the only implementation-evidence item still waiting on information
that is not present in the repository.

## Part 2 — Parallel fan-out

Query:

> compare NVDA, AMD and INTC over the last year

The Planner emits three sibling retrieval nodes with no dependencies:

```text
layer 0: fetch_AMD | fetch_INTC | fetch_NVDA
layer 1: metrics
layer 2: answer
```

The stored run records:

| Measurement | Seconds |
|---|---:|
| Layer wall-clock | 0.0136 |
| Longest branch | 0.013 |
| Sum of branches | 0.038 |

Thus wall-clock tracks the maximum branch rather than their sum. The stored
run is backed by `test_three_branch_layer_is_max_not_sum`, which uses three
controlled 0.4-second branches and does not depend on network timing.

Evidence: [logs/part2_parallel.json](logs/part2_parallel.json).

## Part 3 — Critic pass, fail, and corrected recovery

The checkable property is:

> Every top-level ticker object in the producer output, excluding
> underscore-prefixed metadata, has an integer `points` value of at least 200
> and a numeric `cagr_pct` value.

The Critic receives the complete producer JSON and checks each ticker object,
so every part of this property is decidable with the data available to it.

The normal run passes: [logs/part3_critic_pass.json](logs/part3_critic_pass.json).

The failure run deliberately returns five AMD prices on the first fetch:

```text
critic on metrics: FAIL — AMD has fewer than 200 close prices (5)
recovery strategy: refetch_upstream
spliced: r1_refetch_AMD -> r1_recompute
rewired: answer -> r1_recompute
iterations: 2
```

Recovery refetches AMD and recomputes the **complete aggregate** using healthy
NVDA and INTC inputs plus repaired AMD. The final logged answer contains 252
points and computed metrics for all three tickers, proving that a corrected
answer—not merely a recovery node—reached the user.

Evidence: [logs/part3_critic_fail.json](logs/part3_critic_fail.json) and
`test_critic_fail_splices_complete_corrected_answer` in
[tests/test_assignment_evidence.py](tests/test_assignment_evidence.py).

The recovery classifier remains a pure function. Its complete unit suite is in
[tests/test_recovery.py](tests/test_recovery.py).

## Part 4 — Coder

`prompts/coder.md` defines the SandboxExecutor contract:

- `argv[1]`: JSON mapping upstream node IDs to output strings
- `argv[2]`: writable artifacts directory
- stdout: one stable JSON result
- non-zero exit: node failure
- no network, randomness, or hardcoded computed values

Demonstration query:

> compute CAGR, annualised volatility, Sharpe ratio and max drawdown for NVDA,
> AMD and INTC

CAGR, annualised volatility, Sharpe, and maximum drawdown require compounding,
standard deviation, and path-dependent calculations over 252 values. The
Formatter is explicitly prohibited from calculating them. The Coder result is
visible in the final answer in [logs/part4_coder.json](logs/part4_coder.json).

## Part 5 — New skill: Charter

The original catalogue retrieved data, computed metrics, checked properties,
and formatted text. It did not produce a visual artifact. `charter` adds that
missing capability:

- YAML entry: [agent_config.yaml](agent_config.yaml)
- Prompt: [prompts/charter.md](prompts/charter.md)
- Exercising query: “compare NVDA, AMD and INTC over the last year with a chart”
- Run evidence: [logs/part5_charter.json](logs/part5_charter.json)
- Output: [artifacts/comparison.png](artifacts/comparison.png)

The plan places `chart` and `metrics` together in layer 1. Charter declares the
existing `sandbox` runtime, so adding it required no change to
`agent/executor.py`.

## Tests

```text
$ MPLCONFIGDIR=/tmp/mpl-a8 python3 -m pytest tests/ -q
..............................................................           [100%]
62 passed
```

Coverage includes DAG validation and splicing, max-not-sum concurrency,
recovery classification, Critic field verification, complete corrected
recovery, Coder output reaching the final answer, and Charter PNG creation.

## Data disclosure

Stooq currently rejects the keyless request in this environment, so the stored
demonstrations use deterministic synthetic fallback series. Every payload
records its source, the Coder preserves that provenance in `_sources`, and the
Formatter prints it. Mock or synthetic results are never presented as live
market data.

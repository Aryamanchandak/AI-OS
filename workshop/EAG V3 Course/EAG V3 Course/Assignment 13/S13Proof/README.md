# S13Proof

`S13Proof` is the verification harness for the separate `S13Code` service. It does not contain another agent runtime. Its local dependency points to `../S13Code-2`, so keep both directories side-by-side.

## Install and run deterministic proofs

```bash
uv sync
uv run ruff check .
uv run pytest -q
```

These tests prove live graph growth, scoped memory and semantic chunking invariants, and an official A2A gRPC task without spending provider quota.

## Run the non-browser benchmark

Start Ollama, `glc_v3` on port `8111`, and `S13Code` on port `8113`. Then run:

```bash
uv run python run_benchmark.py \
  --base-url http://127.0.0.1:8113 \
  --output benchmark.md
```

This executes the prompts in `benchmark_cases.json`. It writes:

- `benchmark.json`: complete raw responses
- `benchmark.md`: readable prompt → graph → agents/providers → event trace → final result

Generated benchmark output is deliberately excluded from the student ZIP and Git. Inspect it locally before sharing it.

## Run the A2A proof

```bash
uv run python run_a2a_proof.py --output a2a-proof.json
```

The script starts an official generated gRPC server, advertises an Agent Card, delegates a bounded task into a waiting graph node, receives the remote artifact, resumes the graph, and saves the complete event trace.

## Relationship to student pull requests

Students change `S13Code` and open one pull request against the official `S13Code` repository. Use this harness beside the checkout to prove the change. `S13Proof` and `glc_v3` should change only when the assignment explicitly requires a new proof case or gateway capability.

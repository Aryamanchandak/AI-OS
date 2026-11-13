# S13Code

`S13Code` is the standalone Session 13 agent runtime. It implements a live task graph, scoped and provenance-bearing memory, Rohan's semantic chunking V2, and Agent2Agent interoperability. It asks `glc_v3` for model completions over HTTP and never owns provider credentials.

## What runs where

| Service | Default address | Responsibility |
|---|---|---|
| `glc_v3` | `http://127.0.0.1:8111` | Models, keys, routing and channels |
| `S13Code` HTTP | `http://127.0.0.1:8113` | Graph, memory, documents and JSON-RPC A2A |
| `S13Code` gRPC | `127.0.0.1:8114` | Official A2A gRPC service |
| Ollama | `http://127.0.0.1:11434` | Phi-4 segmentation and Nomic embeddings |

## Requirements

- Python 3.11 or newer
- [`uv`](https://docs.astral.sh/uv/)
- A running `glc_v3`
- A running Ollama with `phi4` and `nomic-embed-text`

```bash
ollama pull phi4
ollama pull nomic-embed-text
ollama serve
```

## Install and run

Keep `glc_v3`, `S13Code-2`, and `S13Proof` beside one another. Start `glc_v3` first. Then, from this directory:

```bash
uv sync

export GLC_BASE_URL=http://127.0.0.1:8111
export S13_GATEWAY_PROVIDER=gemini
export S13_SANDBOX_ROOT="$PWD/sandbox"
export S13_CHUNK_MODEL=phi4:latest
export S13_LIVE_SEMANTIC_CHUNKING=1

uv run s13code serve
```

State is written under `~/.s13code` by default. Set `S13_DATA_DIR` to use another directory.

Check both services:

```bash
curl http://127.0.0.1:8111/healthz
curl http://127.0.0.1:8113/healthz
curl http://127.0.0.1:8113/readyz
curl http://127.0.0.1:8113/.well-known/agent-card.json
```

## Run a prompt

```bash
curl -s http://127.0.0.1:8113/v1/agent/runs \
  -H 'Content-Type: application/json' \
  -d '{
    "tenant_id": "course",
    "project_id": "s13",
    "user_id": "student-01",
    "agent_id": "assistant",
    "prompt": "Say hello."
  }'
```

The response contains the final answer, graph nodes and edges, ordered graph events, and provider/agent assignments. Inspect a persisted run with:

```bash
curl http://127.0.0.1:8113/v1/agent/runs/<run-id>
```

## Index the sample corpus

The five files under `sandbox/papers/` are fixed `.txt` fixtures for semantic chunking and retrieval proofs.

```bash
curl -s http://127.0.0.1:8113/v1/agent/runs \
  -H 'Content-Type: application/json' \
  -d '{
    "tenant_id": "course",
    "project_id": "papers",
    "user_id": "student-01",
    "prompt": "Index every .txt file under papers/. Confirm how many chunks were indexed in total."
  }'
```

Document ingestion is versioned and atomic: source preparation, semantic boundaries, exact spans, Nomic embeddings, and visibility succeed together or roll back together.

## Architecture

- `s13code/core/live_graph/`: durable graph state, patches, event replay and bounded parallel execution
- `s13code/core/memory/`: scope checks, provenance, contradiction history, semantic chunking and FAISS retrieval
- `s13code/core/a2a_adapter/`: Agent Cards, JSON-RPC, SSE/push, official gRPC and trust checks
- `s13code/gateway.py`: the only `S13Code → glc_v3` seam
- `s13code/runtime.py`: joins graph, memory, tools and model calls into an inspectable run
- `tests/`: executable invariants and regression cases

## Test before opening a pull request

```bash
uv run ruff check .
uv run pytest -q

cd ../S13Proof
uv sync
uv run pytest -q
```

## Student contribution

Fork the official `S13Code` repository linked from Axiom, create a branch, implement one meaningful extension, and open one pull request against that repository. Do not open the Session 13 pull request against `glc_v3`.

Add one subsection to this README in the same pull request. It must contain:

1. the user-visible capability,
2. the exact prompt or API request,
3. the graph and ordered event trace,
4. the actual final result,
5. evidence and provider/agent assignments,
6. the adversarial failure and its fix,
7. commands that reproduce the result from a fresh checkout.

Do not commit `.env`, credentials, personal memory, generated databases, unrestricted local paths, benchmark output containing private data, or provider responses containing secrets. Use synthetic identities in every proof.

## License

MIT. See `LICENSE`.

## Research advisor: evidence before a worker finalizes a claim

A worker can call `POST /v1/agent/advisor` with its question, draft, and up to four explicit claims. The advisor retrieves current documents in the supplied scope, assesses every claim, and can request one follow-up search after observing a gap. Code derives `accept`, `revise`, or `insufficient_evidence` from the assessments. Citations must quote retrieved text exactly and retain document version and character offsets into the prepared document. The advisor returns advice; the calling worker owns revisions and actions. This prototype uses the existing graph executor and gateway, adds no dependency, and does not create a second temporal memory store.

The exact synthetic proof request is:

```json
{"tenant_id":"synthetic-proof","project_id":"research","user_id":"student","question":"What do these abstracts establish about ReAct versus chain-of-thought?","draft":"ReAct interleaves reasoning and actions. ReAct always outperforms chain-of-thought on every task.","claims":["ReAct interleaves reasoning and actions.","ReAct always outperforms chain-of-thought on every task."]}
```

The HTTP proof indexes the five bundled abstracts, then runs this consultation. Its graph is `retrieve_1 → review_1 → retrieve_2 → review_2 → advice`; the follow-up node is absent until the first review reports an unclear claim. The ordered journal from a fresh proof is:

```text
37 run_started; 38 graph_patched add retrieve_1
39 task_started retrieve_1; 40 task_succeeded retrieve_1; 41 graph_patched add review_1
42 task_started review_1; 43 task_succeeded review_1; 44 graph_patched add retrieve_2
45 task_started retrieve_2; 46 task_succeeded retrieve_2; 47 graph_patched add review_2
48 task_started review_2; 49 task_succeeded review_2; 50 graph_patched add advice
51 task_started advice; 52 task_succeeded advice; 53 graph_patched finish
```

Actual scripted result: `recommendation=revise`, `followups_used=1`. The first claim is supported; universal superiority remains unclear. The scripted worker consumes those assessments and returns: “ReAct interleaves reasoning and actions. The supplied abstracts do not establish universal superiority over chain-of-thought. [source: fixture://papers/react.txt]”. The citation quotes “generate both reasoning traces and task-specific actions in an interleaved manner”, document version 1, prepared-document characters `[1135,1216)`. Both review nodes report provider `scripted-advisor`, model `fixture-v1`; retrieval and advice are local code. The floor cases report `scripted-worker/fixture-v1`; the separate A2A proof uses a deterministic remote specialist over real gRPC.

The adversarial test replaces a document while the model is reviewing it. Before the fix, the unchanged test failed with `assert 'completed' == 'failed'`: the stale citation was accepted. The fix checks current scope, lifecycle, and exact text after the model returns, then rechecks citations before advice leaves the graph. The same test now passes and the attack returns `status=failed`, `recommendation=insufficient_evidence`, with no approved assessments. Tests also reject invented record IDs, invented quotes, omitted or changed claims, extra action fields, uncited conclusions, and evidence outside tenant/project/user/agent/run scope.

On ten labels in `sandbox/advisor_cases.csv`, complete supporting passages occur in the top three results for **10/10 semantic queries versus 4/10 fixed 40-word queries**. Both find the correct source 10/10 times. Semantic retrieval returns 751.1 words on average versus 118.2: this is a coverage comparison, not an equal-token efficiency claim. Coverage without overlap and idempotent indexing pass for all five sources; the existing rollback-on-embedding-failure and suffix-rollover tests remain passing. Corpus hashes and per-question results are included in the generated proof.

Reproduce from the assignment folder, without keys or running model services:

```bash
cd S13Code-2
uv sync --frozen --python 3.11.15
uv run --frozen --python 3.11.15 python -m pytest -q
uv run --frozen --python 3.11.15 ruff check . ../S13Proof/s13proof
cd ../S13Proof
uv run --frozen --python 3.11.15 --no-editable python -m pytest -q
uv run --frozen --python 3.11.15 --no-editable python -m s13proof.advisor_proof --output advisor-proof.json
uv run --frozen --python 3.11.15 --no-editable python run_a2a_proof.py --output a2a-proof.json
```

`advisor-proof.json` retains the request, graph, full ordered events, citations, assignments, revised worker answer, scoped denial, stale attack, retrieval evaluation, and HTTP floor runs for live expansion, durable memory after restart, and document recall. The second command retains the fourth floor case, A2A waiting/resume. These ignored outputs use synthetic identities; neither requires provider keys. `--no-editable` avoids relying on Python loading editable-install `.pth` files.

Limits: the offline proof uses heading segmentation, deterministic embeddings, and scripted model replies, including the worker revision. It proves orchestration and citation integrity, not that an actual advisor improves judgment. A genuine quotation can still be misread; a test explicitly demonstrates that limitation. These labels are starter cases for human review. Only the explicitly supplied claims are covered. The inherited local API trusts caller-supplied scope and does not authenticate identity; keep it behind a trusted caller. Advisor traces can be inspected but are not resumable through the ordinary run endpoint. Live gateway/Phi-4/Nomic runs, the full non-browser benchmark, and an advisor-versus-no-advisor judgment evaluation remain pending until models and credentials are available.

The paired comparison runner is prepared for that last evaluation. It generates one worker draft per question and shares it between the baseline and advisor arms. It retains the consultation and any worker revision, including cases where advice degrades a correct answer. Its 13 draft labels in `sandbox/advisor_judgment_cases.csv` cover ten supported claims, one contradicted claim, one unsupported universal claim, and a hostile self-certified source. Review these labels before treating agreement as meaningful. Generated `.reviews.csv` files leave unsupported-claim counts, preservation, and citation correctness blank for human assessment; no model grades its own prose.

From `S13Proof`, run the scripted rehearsal:

```bash
uv run --frozen --python 3.11.15 --no-editable python -m s13proof.advisor_comparison --output advisor-comparison.json
```

When a configured gateway is available, load role choices from `S13Code-2/.env` and run actual model calls:

```bash
uv run --frozen --python 3.11.15 --no-editable python -m s13proof.advisor_comparison --mode live --output advisor-comparison.json
```

`S13_COMPARISON_WORKER_PROVIDER` and `S13_COMPARISON_ADVISOR_PROVIDER` optionally select configured gateway providers; blank values fall back to `S13_GATEWAY_PROVIDER`. Provider keys stay in the gateway's `.env`. The report retains actual provider/model assignments, reported token counts, elapsed time, failures, corpus/case/prompt hashes, and a unique session prefix for gateway ledger correlation. Unknown usage and priced cost remain null; gateway chat responses do not return priced cost. Both arms use the same fixed offline retrieval to isolate model evaluation from local model availability, but the advisor may retrieve additional passages and use more calls. The report measures draft-label agreement and exposes regressions; it does not certify judgment quality. Failed cases remain in the report, and an incomplete CLI run exits unsuccessfully.

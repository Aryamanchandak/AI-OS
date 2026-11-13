# Consequence Radar

Consequence Radar turns a supplied, finite news batch into an auditable causal analysis for Indian equities and a newsletter-ready report. It is a standalone project; it does not import or modify What If Analyser.

The application selects one grounded premise relative to the supplied batch, maintains a versioned causal DAG, targets research at gaps, verifies exact evidence passages, records assumptions and Decimal estimates, attempts disproof once, selects one most-supported central case, and writes the report from canonical accepted context in one model call.

## Run

The only prerequisite is [uv](https://docs.astral.sh/uv/). From this folder, run:

```bash
./radar
```

That single command creates `.env` when needed, installs the exact locked dependencies, handles the workspace's literal `?` safely, and starts the app. Open `http://127.0.0.1:8010`.

Add `GEMINI_API_KEY` to `.env` for live runs. The interface and tests work without it; a submitted live run fails with a clear configuration error if credentials are absent. Runtime SQLite data stays under `data/`.

For an explicit dependency-only setup, run `./radar setup`. It is optional because `./radar` already performs it when necessary.

## Test

```bash
./radar test
```

The mocked suite never needs live credentials or network access.

## API example

```bash
curl -i http://127.0.0.1:8010/api/v1/runs \
  -H 'Content-Type: application/json' \
  -d @samples/input_batch.json
```

The response is `202 Accepted` with a `run_id`. Then use:

```bash
curl http://127.0.0.1:8010/api/v1/runs/RUN_ID
curl -N http://127.0.0.1:8010/api/v1/runs/RUN_ID/events
curl http://127.0.0.1:8010/api/v1/runs/RUN_ID/graph
curl http://127.0.0.1:8010/api/v1/runs/RUN_ID/audit
curl http://127.0.0.1:8010/api/v1/runs/RUN_ID/report
curl 'http://127.0.0.1:8010/api/v1/runs/RUN_ID/report?format=markdown'
curl http://127.0.0.1:8010/api/v1/runs/RUN_ID/export
```

## Configuration

Model IDs are configuration, not code constants: `FAST_MODEL`, `REASONING_MODEL`, and `REPORT_MODEL`. Central safety controls include research cycles, graph size, task/query/source/model-call limits, wall time, report-context tokens, worker count, fetch bytes/timeouts/redirects/retries, and report word bounds. See [.env.example](.env.example).

Google Search grounding is the production search provider. It yields grounded source URLs, which the controlled fetcher resolves, size-bounds, extracts, stores, and passes to exact-passage verification. There is no DuckDuckGo scraping fallback. The URL Context tool runs alongside Google Search grounding (`ENABLE_URL_CONTEXT_SEARCH`, default on) to produce real per-source relevance snippets; it never supplies the text used for claim verification -- that always comes from the controlled fetcher.

## Persistence and failure behaviour

SQLite stores the input batch, extracts and failures, groups, top candidates, every source and claim outcome, tasks and queries, every graph version and invalid patch, challenges and decisions, cases, model usage, report draft, and validation result. Events are persisted before the browser receives them. A new failed run remains inspectable and does not delete earlier completed runs.

Fatal analytical failures fail closed: no viable seed, irreparable graph, no concrete Indian-equity path, unsupported central case, context overflow, exhausted budgets, and report/citation failure. Recoverable source and non-load-bearing evidence gaps remain warnings.

## Samples and documentation

- [Sample input](samples/input_batch.json)
- [Sample completed report](samples/completed_report.md)
- [Sample exported run](samples/completed_run.json)
- [Architecture](docs/ARCHITECTURE.md)
- [Evaluation](docs/EVALUATION.md)
- [Codebase overview](docs/overview/overview.md)
- [Documentation map](docs/DOCUMENTATION.md)
- [End-to-end orchestration trace](deep-dive/orchestration.md)

## Live smoke test

No credential was available in the implementation environment, so no paid live call was made. When a key is available, use the sample batch, monitor the event stream, and verify the report and complete JSON downloads. Record the date, configured model IDs, run ID, terminal state, call/token ledger, elapsed time, source-marker validation, and any warning in `docs/EVALUATION.md`. The documented mocked smoke path is covered by `tests/integration/test_pipeline.py`.

## Known limitations and deferred work

- The MVP rejects feedback cycles and records them as limitations instead of modelling equilibrium feedback.
- SQLite plus an in-process bounded worker pool targets one deployment process; it is not a distributed queue.
- A process restart retains all run state and events but does not automatically resume a run interrupted mid-stage.
- De-duplication is intentionally conservative lexical housekeeping; the selector still sees every member and disagreement.
- The context budget uses a deterministic character-to-token approximation. Provider token counting can replace it later without changing the compiler contract.
- The compiled report context carries a short excerpt of each source body and of each claim's exact passage rather than the full text. Passage verification has already happened by that point and the untruncated text stays in the persisted `sources` and `accepted_claims` artifacts, so the audit trail is unaffected. A graph at every configured cap can still exceed `REPORT_CONTEXT_TOKEN_BUDGET` and fails closed; raise the budget if runs reach that size.
- No user accounts, continuous crawling, trading, recommendations, vector database, portfolio logic, or open-ended multi-agent framework are included.
- The UI loads Google Fonts when reachable and falls back to serif/sans-serif families offline.

This is research software, not investment advice. It does not issue buy, sell, hold, or personalised instructions.

# Gateway status

Graphiti readiness work is scoped in the [Graphiti readiness plan](graphiti-readiness.md).
The code fixes are implemented: offline checks report `182 passed, 4 deselected`
and mypy reports no issues in 47 source files (2026-10-23). The four live golden
checks fail because `gateway/.env` and the Anthropic key are absent and local
Ollama is unreachable. Live proof remains outstanding.
The direct-client/deferred-deployment direction below describes the prior status;
it does not establish Graphiti readiness through this gateway.

Immediate path: use the independent [simple_llm client](../../../simple_llm/README.md)
for direct provider calls. Gateway deployment and further work are deferred.

Gateway scope: give ingestion one working API for hosted LLM calls and local
embeddings. No further restructuring or new features are needed for that scope.

The main shrink is implemented: legacy routes, streaming, semantic cache,
duplicate logging and handwritten provider adapters are removed. Existing
budgets, ledger, profiles, retries and telemetry remain.

Live provider and ingestion validation has not been established. The golden
refusal expectation now requires one row with status `refused`.

The ingestion runner in `../projects/capture/ingestion-pipeline` still loads
`llm_gateway.client.LLM`; its comments describe port 8107. This gateway runs on
port 8000 with `/api/llm/*` endpoints. Verify the actual client configuration and
one ingestion request before calling the handoff complete.

The step plans and YAGNI reviews are historical context, not an active task list.
Together, batching, dashboards and further structural cleanup are deferred.

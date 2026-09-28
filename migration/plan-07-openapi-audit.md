# Plan 07 — GLC OpenAPI contract audit

## Resolution — 2026-09-27

All six missing backend operations have Gateway-owned implementations. The
current export registers 79 HTTP operations. Of the 43 baseline operations,
40 are registered at their original method/path; the remaining three (`GET /`,
`/channels`, `/help`) are explicitly accounted for by React shell navigation.
The root remains the ingestion landing page. `/dashboard` now redirects to
`/observability`. No baseline operation is left unclassified by the regression
gate in `gateway/tests/test_restored_contracts.py`.

- Channel send preserves the response envelope and supports install/bridge
  tokens. Disabled adapters return 503, unknown channels 404, and provider
  failures 502. Audit availability is checked before sending; requested,
  successful, and failed sends are recorded without message content.
- Preflight is available at `/api/llm/preflight` and `/v1/preflight` through
  the same LLM router. Chat and embedding probes run concurrently with
  30-second deadlines and the preserved response shape.
- Trace and refusal reads are restored at `/api/observability/*` and their
  old `/v1/*` aliases. HTTP request and LLM-stage spans use a bounded local
  exporter; successful chat responses include trace/span IDs. Refusal capture
  observes 402s without buffering successful SSE responses.
- Agent trace uses the enabled `agent_runtime` registry endpoint and returns
  503 when disabled or unreachable. Its optional `base_url` must match that
  configured target; arbitrary targets are deliberately rejected.
- The shell observability screen now displays recent traces and budget
  refusals, including loading/error/empty states and manual refresh.

Intentional security changes: legacy observability reads now require
`AI_OS_TOKEN`; diagnostic errors are redacted, agent content attributes are
filtered, and caller-supplied agent proxy targets are restricted. Trace and
refusal data is bounded, process-local, and resets on restart. Traces describe
Gateway HTTP/LLM-stage execution; they do not capture prompt or completion text.

Verification: 892 Gateway tests passed, 5 skipped; 123 shell tests passed;
Gateway mypy, TypeScript, Vite build, regenerated OpenAPI/types, and changed-file
whitespace checks passed. External paid providers and a real agent service
were not contacted by these controlled regression tests.

## Historical findings — 2026-09-25

Audited 2026-09-25 against `migration/baseline/contracts/glc-openapi.json`
and the newly exported `gateway/openapi.json`. Comparison key: HTTP method and
path. A matching key proves route registration, not response equivalence.

## Result

The baseline has 43 HTTP operations. Gateway now registers 33 at the same
method and path, including the restored `GET /healthz`. Ten baseline
operations are absent from OpenAPI. Gateway also adds 34 operations, mostly
new `/api/llm/*` and `/api/ingestion/*` contracts. The totals alone are not a
compatibility measure.

For the 33 exact-path operations, the declared response-status sets match.
Their JSON request-body schemas match structurally; the only raw schema
difference is a removed explanatory description on
`PUT /v1/channel-admin/{name}`. OpenAPI does not establish identical response
bodies or side effects, so existing characterization tests remain necessary.

| Baseline operation | Gateway state | Assessment |
| --- | --- | --- |
| `GET /` | React shell serves the ingestion screen. Original served GLC's dashboard. | Intentional new default UI; old page behavior differs. |
| `GET /channels` | React shell selects ChannelsAdmin at the same URL. | Replaced UI, not a missing feature. |
| `GET /dashboard` | React shell currently selects the ingestion screen because no dashboard path is recognized. New screens are `/llm` and `/observability`. | Wrong screen at old URL; needs redirect or deliberate retirement. |
| `GET /help` | React shell selects Help at the same URL. | Replaced UI, not a missing feature. |
| `POST /v1/channels/{name}/send` | No Gateway HTTP route. The old route authenticated with the channel bridge token, sent via the adapter, and audited success/failure. | Genuine missing proactive channel-send capability. |
| `POST /v1/preflight` | Request/response models exist in `gateway.llm.models`, but no route invokes chat and embedding readiness probes. | Genuine missing LLM readiness capability. |
| `GET /v1/traces/recent` | Gateway has an OTel exporter but no equivalent recent-trace ring or read route. | Genuine missing observability capability. |
| `GET /v1/traces/{trace_id}` | No local trace-detail ring or read route. | Genuine missing observability capability. |
| `GET /v1/refusals` | No 402-refusal recorder or read route. The shell Observability screen explicitly says refusal analytics are unavailable. | Genuine missing budget-refusal visibility. |
| `GET /v1/observability/agent_trace/{run_id}` | No agent-trace proxy route. | Genuine missing optional agent-trace view. |

`GET /healthz` was an eleventh missing operation at the start of this audit.
It now returns the original JSON shape (`ok`, `port`) using the resolved
Gateway port. `/health` remains Gateway's native health endpoint.

## Runtime behavior found and corrected

Before this audit, the shell catch-all returned HTTP 200 with `text/html` for
missing GET API paths, including `/v1/refusals` and `/v1/traces/recent`.
Missing POST paths returned 405. That could make a caller mistake a missing
API for success. Gateway now returns JSON 404 for unregistered `/v1/*` and
`/api/*` HTTP paths. Tests cover both GET and POST cases.

## What remains to decide or implement

1. Restore proactive channel send and preflight if Gateway must preserve the
   complete GLC operational contract. These are backend feature gaps, not
   client-migration bookkeeping.
2. Decide whether the trace, refusal, and agent-trace reads are required in
   Gateway. The existing shell observability screen intentionally shipped
   without them; the old endpoints cannot be called compatible as-is.
3. Redirect `/dashboard` to the intended new screen, or return a clear 404.
4. Keep response-level characterization tests for the 33 registered routes;
   OpenAPI's old 200-response schemas are frequently `{}` and cannot prove
   payload equivalence.

External caller migration and any usage-observation window are outside this
local contract audit.

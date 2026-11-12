# Contract snapshots — Plan 01 baseline capture

Captured 2026-09-14, against `glc_v5@604e425` and `gateway` (parent
`9fc863b`). Compatibility policy (Plan 01 §2, proposed default adopted):
freeze `/v1/*` (GLC) and `/api/ingestion/*` (Gateway) byte-for-byte —
URLs, status codes, response bodies, SSE frames, and WebSocket behavior —
until caller migration is complete. No selected exceptions.

## OpenAPI snapshots

- `migration/baseline/contracts/glc-openapi.json` — generated directly from
  `glc.main.app.openapi()` (GLC has no export script of its own; nothing
  added to `glc_v5` to produce this — the JSON was generated and written
  only under `migration/`). 39 paths, all under `/v1/*` plus `/`, `/healthz`,
  `/help`, `/channels`, `/dashboard`.
- `migration/baseline/contracts/gateway-openapi.json` — copy of the
  already-committed `gateway/openapi.json`, produced by `gateway/export_openapi.py`
  (also re-run as part of the baseline suite; see `results-*.log`, which
  confirms it's not stale). 8 paths, all under `/api/ingestion/*`.

Re-run to refresh either snapshot:

```bash
cd glc_v5 && uv run python -c "
import json
from glc.main import app
json.dump(app.openapi(), open('../migration/baseline/contracts/glc-openapi.json', 'w'), indent=2, sort_keys=True)
"
cp gateway/openapi.json migration/baseline/contracts/gateway-openapi.json
```

## Representative fixtures

No live provider calls were made to capture these (no credentials in this
environment, and refactoring providers is explicitly out of scope for Plan
01). Instead, each required scenario is pointed at the existing test(s) that
already exercise it — these are the fixtures to diff against once code
starts moving, and each one already runs with a mock/fake, not a live
provider, except where marked opt-in-live:

| Scenario | Where it's covered today |
|---|---|
| Chat + structured output | `glc_v5/tests/test_v9_compat.py::test_chat_request_minimal_body_validates`, `test_chat_request_rejects_bad_provider`; `glc_v5/tests/test_v4_routes.py::test_a_v3_chat_body_is_still_accepted`, `test_v3_response_shapes_are_unchanged` |
| Embeddings + profile resolution | `glc_v5/tests/test_v9_compat.py::test_embed_request_413_on_oversize`; `glc_v5/tests/test_profiles.py`; route contract documented in `ingestion-pipeline/docs/WORKFLOW_ingestion_glc_v5.md:32` (`GET /v1/chat/profiles/{profile}`) |
| Batch chat | `glc_v5/tests/test_v4_routes.py`, `glc_v5/tests/test_client.py` (`/v1/chat/batch` surface) |
| SSE streaming + disconnect | `glc_v5/tests/test_client.py::test_stream_closes_network_response_when_iteration_ends_early`, `test_stream_closes_the_owned_client_when_the_connection_itself_fails` |
| Channel WebSockets + webhooks | `glc_v5/tests/test_s16_channel_connections.py` (shared S16 websocket contract); `glc_v5/tests/test_webhook_replay.py` (replay/signature/staleness); `glc_v5/tests/channels/test_webhook.py` |
| Transcription + speech | `glc_v5/tests/test_transcribe_route.py` (400/501/502 cases); voice provider contract tests under `glc_v5/glc/voice/tts/providers/*/tests/` |
| Budget refusal + provider failure | `glc_v5/tests/test_economics_budget.py` (402 refusal paths, worst-case projection); `glc_v5/tests/test_direct_providers.py::test_vendor_error_is_normalized` (opt-in-live sibling: `test_direct_providers_live.py`) |
| Ingestion run/decision/retry/report/evidence/cleanup | `gateway/test_main.py` (exercises the `/api/ingestion/*` router mounted in `gateway/main.py`); `gateway/test_contract_staleness.py` (keeps `gateway/openapi.json` honest) |

Two GLC test modules are opt-in live and were **not** run as part of the
baseline (see `results-*.log` — they weren't invoked, not failed):
`test_cache_semantic_live.py`, `test_direct_providers_live.py`,
`test_local_models_live.py` — all gated by `requires_live_api`/
`requires_models` markers per `glc_v5/.github/workflows/ci.yml`.

## Environment variable defaults and precedence

GLC (`GLC_*`, all `os.getenv(NAME, default)` — explicit env var always wins
over the coded default; there is no config-file layer that outranks the env
var for these):

| Variable | Default | Purpose |
|---|---|---|
| `GLC_PORT` | `8111` | bind port (`glc/main.py`, `glc/cli.py`) |
| `GLC_HOST` | `0.0.0.0` | bind host (`glc/cli.py`) |
| `GLC_BASE_URL` | `http://127.0.0.1:8111` | client default target (`glc/client.py`) — this is what ingestion and any other caller override to point at a non-default GLC instance |
| `GLC_CONFIG_DIR` | `~/.glc` | root for local config |
| `GLC_GATEWAY_DB` | `~/.glc/gateway.sqlite` | call ledger — **relocation decided in Work Package F, not yet applied** |
| `GLC_AUDIT_DB` | `~/.glc/audit.sqlite` | audit log — same |
| `GLC_ARTIFACTS_DIR` | `~/.glc` | channel adapter artifacts (Gmail, IMAP, Twilio SMS) |
| `GLC_PAIRING_DB` | `~/.glc/pairings.sqlite` | agent pairing state |
| `GLC_PUBLIC_BASE` | request base URL | public URL channels advertise for webhooks |
| `GLC_S16_BRIDGE_TOKEN` / `GLC_S16_TIMEOUT` | `""` / `180` | S16 agent bridge auth + timeout |
| `GLC_S15_BASE_URL` | unset | observability upstream |
| `GLC_KILL_ALLOW_REMOTE` | unset (`!= "1"` blocks) | gates `/v1/control/kill` from non-localhost |
| `GLC_OTEL_ENABLED` / `GLC_OTEL_CONSOLE` / `GLC_OTEL_IN_MEMORY` / `GLC_OTEL_CAPTURE_CONTENT` / `GLC_OTEL_RECENT` / `GLC_TRACE_UI` / `GLC_JAEGER_UI` | mixed, see `glc/telemetry/otel.py` | tracing config |
| `GLC_WHISPER_MODEL_DIR` / `GLC_WHISPER_THREADS` / `GLC_WHISPER_BEAM_SIZE` / `GLC_GROQ_STT_MODEL` | provider-specific | voice STT tuning |
| `GLC_GATEWAY_HOST` / `GLC_GATEWAY_PORT` / `GLC_TWILIO_WEBHOOK_PORT` / `GLC_TWILIO_SKIP_SIG` | Twilio SMS bridge specific | see `glc/channels/catalogue/twilio_sms/` |

Ingestion / Gateway:

| Variable | Default | Purpose |
|---|---|---|
| `GLC_PROFILE` | task-specific, see `merged-ingestion/src/ingestion/{consumers/vector_consumer.py, coordinator/preflight.py, vector/vector_store.py}` | which GLC task profile ingestion resolves against — ingestion never selects a raw provider/model directly |
| `GLC_PROFILES_YAML` / `GLC_PROFILES_PATH` | unset | override path to the profile config ingestion reads |
| `INGESTION_DATABASE_ROOT` | root `Database/` (per `ingestion-pipeline/merged-ingestion/src/ingestion/config.py:38`) | overrides where ingestion writes its SQLite/Chroma/Neo4j data |
| `INGESTION_RESOLVER` | `local-reviewer` | which resolver `gateway/main.py` wires the ingestion router to |
| `AI_OS_TOKEN` | `""` | bearer token the gateway expects on its admin/API routes |
| `AI_OS_PREVIEW` | unset (`== "1"` enables) | switches gateway to the preview/mocked ingestion journey instead of the real coordinator |

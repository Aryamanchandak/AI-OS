# RECON.md — glc_v2 Part 1 Hardening (Phase 0)

Working repo: `glc_V2_fixed` (pristine reference: `glc_V2_original`; the two `glc/`
trees are byte-identical except compiled `__pycache__`, so no hardening had happened
before this pass).

## Live deployment (confirmed)

- **Only ONE Modal app is deployed:** `glc-v1-gateway` (App ID `ap-lg7sWV9Mrhx6MjXoPt8u5g`,
  deployed 2026-07-12, `min_containers=0` so scaled-to-zero / cold-starts on request).
  There is **no separate `glc-v2` app** — v1 and v2 are the same single deployment here.
  (Correction to the build brief's assumption of a distinct v2 slug.)
- **Workspace/profile:** `aryamanchandak7`
- **Public URL:** `https://aryamanchandak7--glc-v1-gateway-fastapi-app.modal.run`
  (pattern: `https://<workspace>--<app-name>-<function-name>.modal.run`; function is
  `fastapi_app` → `fastapi-app`.)
- `GET /healthz` → `{"ok":true,"port":8111}` (confirms this is the deployed gateway).
- One Modal Secret, `glc-llm-keys`, mounted on the whole Function. Modal hides secret
  values; ASSIGNMENT.md + README + modal_app.py comment all state mock keys only.
  **Dummy-ness not yet independently verified** (see open question in FINDINGS).

## 1. Adapters and the provider key(s) each actually needs

Because all keys live in ONE Secret on ONE Function, **every adapter currently sees every
key** — that itself is the invariant-1 bug.

**LLM provider keys (used by gateway core: `glc/providers.py`, `glc/embedders.py`):**
- `GEMINI_API_KEY`, `NVIDIA_API_KEY`, `GROQ_API_KEY`, `CEREBRAS_API_KEY`,
  `OPEN_ROUTER_API_KEY`, `GITHUB_ACCESS_TOKEN`

**Voice provider keys (voice STT/TTS adapters):**
- `CARTESIA_API_KEY` (tts/cartesia), `ELEVENLABS_API_KEY` (tts/elevenlabs),
  `GEMINI_API_KEY` (stt+tts gemini_live)

**Channel adapters — own channel tokens, NOT LLM keys** (still leak-shared today):
- telegram `TELEGRAM_BOT_TOKEN`; whatsapp `WHATSAPP_TOKEN` / `WHATSAPP_APP_SECRET` /
  `TWILIO_AUTH_TOKEN`; twilio_sms `TWILIO_AUTH_TOKEN`; teams `TEAMS_APP_PASSWORD`;
  line `LINE_CHANNEL_ACCESS_TOKEN` / `LINE_CHANNEL_SECRET`; gmail `GMAIL_OAUTH_CLIENT_SECRET`;
  webhook `WEBHOOK_SHARED_SECRET`; discord `DISCORD_BOT_TOKEN` (dev/test only).

## 2. `os.getenv`/`os.environ` provider-key read sites (glc/)

- `glc/embedders.py:207` GEMINI
- `glc/providers.py:1166,1168,1170,1172,1174,1178,1214,1216,1218,1220` GEMINI/NVIDIA/GROQ/CEREBRAS/OPEN_ROUTER/GITHUB
- `glc/voice/tts/providers/cartesia/adapter.py:82` CARTESIA
- `glc/voice/tts/providers/elevenlabs/adapter.py:37` ELEVENLABS
- `glc/voice/tts/providers/gemini_live/adapter.py:54` GEMINI
- `glc/voice/stt/providers/gemini_live/...` GEMINI (smoke only)
- Channel token reads: `routes/channels.py:127`, telegram/whatsapp/twilio_sms/teams/line/gmail/webhook adapters (see §1)

## 3. `Secret.from_name` sites

- `modal_app.py:52` — `modal.Secret.from_name("glc-llm-keys")` (the only one).

## 4. Routes (from live `/openapi.json` — its public readability is itself leak A2)

Data plane (currently **no auth**): `POST /v1/chat`, `/v1/chat/batch`, `/v1/vision`,
`/v1/embed`, `POST /v1/transcribe`, `/v1/speak`
Info (currently **no auth**): `GET /v1/embedders`, `/v1/cost/by_agent`, `/v1/providers`,
`/v1/capabilities`, `/v1/status`, `/v1/routers`, `/v1/calls`, plus `/`, `/healthz`,
`/docs`, `/openapi.json`
Control plane (**token-protected** via `_require_token`, keep): `POST /v1/control/pair`,
`/v1/control/pair/confirm`, `GET /v1/control/presence`, `POST /v1/control/kill`
Channel webhooks: `GET|POST /v1/channels/{name}/webhook`
WebSocket: `WS /v1/channels/{name}` (adapter connections; see `glc/routes/channels.py`)

## 5. Adapters importing gateway internals directly (Phase-1 blast radius)

Confirmed importable from the shared process today: `glc.policy` (module-level
`evaluate()` at `engine.py:168` — monkey-patchable), `glc.db` (`log_call()` at `db.py`,
validates nothing), `glc.security.pairing` (`force_pair_owner()` at `pairing.py:187`).
Full per-adapter import audit pending in Phase 1.

## Vulnerabilities confirmed against current code (not just brief prose)

- **A1** — `glc/routes/chat.py` has **no** FastAPI auth dependency; only `routes/control.py`
  checks a token. `/v1/status` returns full provider order/limits/models unauthenticated (verified live).
- **A2** — `/openapi.json`, `/docs`, `/v1/status`, `/v1/providers`, `/v1/capabilities`,
  `/v1/cost/by_agent`, `/v1/calls` all public (route map fetched live above).
- **C1** — `_resolve_image_urls` (`chat.py:288`) uses `follow_redirects=True`, no host allowlist → SSRF.
- **Leaks 3/5/10** — `force_pair_owner`, module-level `policy.evaluate`, `db.log_call` all
  present and reachable from any in-process code.

## Notes on the build brief

The brief is partially corrupted (garbled fragments: "outboulowlist", "audit DB wat the
OS layer", empty C5 fix, truncated sentences). Each vuln is being re-verified against the
actual code before writing its "repro before". Modal Sandbox egress param will be checked
against current Modal docs, not assumed.

# LLM Gateway V7 — Preflight + Embedding Profiles

| Field | Value |
|---|---|
| **Date** | 2026-07-27 |
| **Version** | `llm-gateway-v7` bumped `0.1.0` → `0.2.0` |
| **Scope** | Two additive, backward-compatible features closing T3 items #2 and #3 from the ingestion-pipeline plan (`integration/to_do_plans/llm_gateway_policy/PLAN_T3_llm_gateway_policy_2026-07-26.md`) |
| **Consumer of this doc** | Whoever next resyncs `merged-ingestion`'s `llm-gateway-v7` dependency — read this before re-running `uv sync` there. |

---

## 1. What changed — server side (`llm_gateway`)

### 1.1 Stable embedding profiles (`embedders.py`, `schemas.py`, `main.py`)

- New `embedders.PROFILES: dict[str, dict]` registry. Currently one entry:
  ```python
  PROFILES = {
      "chunker-v1": {"provider": "ollama", "model": "nomic-embed-text", "dim": 768},
  }
  ```
- `EmbedRequest` gained an optional field: `profile: Optional[str] = None`.
- `EmbedResponse` gained an optional field: `profile: Optional[str] = None` (echoes the request's profile back, `None` if not used).
- `POST /v1/embed` behavior when `profile` is set:
  - unknown profile name → **400** (`unknown embedding profile '<name>'. known: [...]`)
  - `profile` + a conflicting `provider` in the same request → **400**
  - profile resolves to a pinned `(provider, model)`; the call is made against that provider
  - **if the provider's actual response model OR dim doesn't match the profile's pin → 500**, fail loud, no silent pass-through. Both are checked — model-name alone would miss e.g. a re-pulled/reconfigured model returning a different width under the same name. This is the whole point of a profile: it is a guarantee, not a hint.
- `GET /v1/embedders` response gained a `"profiles"` key: the full `PROFILES` dict, for discoverability.
- Nothing existing was renamed or removed. Calling `/v1/embed` with `provider=` (or nothing) and no `profile=` behaves exactly as before.

### 1.2 No preflight-specific server changes

Preflight (below) is implemented entirely as a client-side composition of two **existing** real calls (`POST /v1/chat`, `POST /v1/embed`) — no new server endpoint was needed. `/v1/status` and `/v1/embedders` were considered but rejected for this purpose: they report rate-limiter/backoff bookkeeping, not actual reachability (e.g. a dead Ollama daemon with no prior failed call wouldn't show up there). A real minimal call is the only thing that actually proves the path works.

## 2. What changed — client (`client.py`)

- `LLM.embed()` gained a `profile: Optional[str] = None` kwarg, mutually exclusive with `provider`. Existing calls are unaffected.
- New `LLM.status()` → `GET /v1/status`.
- New `LLM.embedders()` → `GET /v1/embedders`.
- New `LLM.preflight(*, embedding_profile: str = "chunker-v1", chat_provider: Optional[str] = None) -> dict`:
  - Makes one minimal structured `chat()` call (`max_tokens=256, reasoning="off"`, a `{"ok": boolean}` JSON-schema `response_format`) and one `embed(profile=embedding_profile)` call.
  - Returns `{"chat": {"ok": True, "provider": ..., "model": ...}, "embedding": {"ok": True, "provider": ..., "model": ..., "dim": ...}}` on success.
  - Raises `GatewayPreflightError` (new exception, `.checks` attribute holds the same per-path dict with `"ok": False` and `"error": "..."` on the failing side) if either path fails.
  - **`max_tokens=256` and `reasoning="off"` are deliberate, not arbitrary** — see §3.1 below. Don't lower `max_tokens` without re-running `tests/test_client_preflight_live.py` several times against a reasoning-capable provider.
- New `GatewayPreflightError(Exception)` in `client.py`.

No existing client method signature changed in an incompatible way — every new parameter is optional and defaults preserve old behavior.

## 3. Tests added

- `tests/test_profiles.py` — server-side, in-process ASGI (same pattern as `test_embed.py`): known-profile resolution, unknown-profile rejection, profile+provider conflict rejection, fail-loud model mismatch, fail-loud dim mismatch, `/v1/embedders` profile listing. 6 tests, 2 marked `local` (hit real Ollama).
- `tests/test_client_preflight.py` — unit tests for `LLM.preflight()`'s own aggregation/error logic, with `chat()`/`embed()` stubbed (no network, no `local` marker needed). 3 tests.
- `tests/test_client_preflight_live.py` — **real, non-mocked** test: spins up `main:app` with `uvicorn` on a free localhost port in a background thread (client.py makes real `httpx` calls to a `base_url`, so it needs an actual listening server, not just an ASGI transport), points a real `LLM` at it, calls `preflight()` for real. 2 tests, both `local`.
- Full suite after this change: **23 passed** (was 12 before: `test_embed` 4 + `test_provider_registry` 2 + `test_tool_translation` 6; +11 new tests across the three files above, no regressions).

### 3.1 What the real (`_live`) test caught — and why the mocked test alone wasn't enough

The mocked `test_client_preflight.py` passed on the first try and would have shipped a broken default. Running the real test against a live gateway surfaced two genuine issues, neither visible with stubs:

1. **`max_tokens` too low for a reasoning-capable model.** The first draft used `max_tokens=16` (then `64`) with a trivial `{"ok": true}` schema. `gemini-2.5-flash` (the `gemini-flash` provider's model) spends output-token budget on invisible "thinking" before the visible answer; at low `max_tokens` it would sometimes burn the whole budget mid-thought, truncate the JSON (e.g. `{"ok":`), and fail schema validation — a real gateway 503, correctly raised, but a false preflight failure against a perfectly healthy gateway. Fixed by adding `reasoning="off"` and raising `max_tokens` to `256`: 10/10 clean structured completions in a row afterward (isolated via direct `provider.chat()` calls, bypassing the gateway HTTP layer, to rule out anything gateway-side).
2. **The gateway's default chat provider order tried `gemma` first** (local, small model) when no `chat_provider` was pinned, and it could fail even a trivial strict-JSON schema intermittently. **Superseded 2026-07-27** (see `change_receipts/2026-07-27_t5_gateway_gemma_policy.md`): Gemma is no longer built as a chat provider by default at all (`ENABLE_OLLAMA_CHAT=1` opt-in required), and `GatewayExtractor` in `merged-ingestion` now pins `profile="knowledge-extraction-v1"` (→ `anthropic-sonnet`) for all real extraction calls — so production no longer touches Gemma or the gateway's default order for chat at all. `tests/test_client_preflight_live.py`'s positive test still pins `chat_provider="gemini-flash"` explicitly (written before that change), which remains valid but is now belt-and-suspenders rather than load-bearing.

A third, *irreducible* source of intermittency was also observed directly against the Gemini API (outside the gateway): real upstream `503 UNAVAILABLE` responses. That's genuine transient cloud-provider unavailability, not a bug — `preflight()` reporting that as a failure is it doing its job.

## 4. Migration notes for `merged-ingestion`

Nothing in `merged-ingestion` was touched *by this change* — it depends on `llm-gateway-v7` via a **non-editable** path source (`[tool.uv.sources] llm-gateway-v7 = { path = "../../llm_gateway", editable = false }`), so it will keep running against whatever snapshot it was last synced to until someone deliberately runs `uv sync` there again. (A separate, later change did land the chat side of this — see `change_receipts/2026-07-27_t5_gateway_gemma_policy.md`: `GatewayExtractor` now pins `profile="knowledge-extraction-v1"`. The embedding-profile and `preflight()` adoption below remain open.) When ingestion next syncs this dependency:

1. **Nothing breaks by default.** Both changes are additive — existing calls with `provider=` (or no provider/profile at all) behave identically. `mypy --strict` / the existing 145-test ingestion suite should not need any changes just to pick up this version.
2. **Adopting the profile (optional, recommended before T5 cutover):** wherever ingestion currently does
   ```python
   client.embed(text, provider="ollama")
   ```
   and then separately validates the response is `nomic-embed-text`/768-dim (see `VectorConsumer`/`VectorStore` per the T3 plan doc §5 item 2), switch to
   ```python
   client.embed(text, profile="chunker-v1")
   ```
   and drop the manual model/dim validation — the gateway now enforces it and fails loud on mismatch instead.
3. **Adopting preflight (optional, recommended right before the T5 live smoke test):** call
   ```python
   llm.preflight(embedding_profile="chunker-v1", chat_provider="anthropic-sonnet")
   ```
   once at the start of `run_ingestion()`/`runner.py`, before capture, and refuse the run (per hard rule R1 / fail-fast philosophy) if it raises `GatewayPreflightError` — this is exactly the "refuse before capture instead of failing mid-run" gap the T3 plan flagged. Pinning `chat_provider` is no longer strictly necessary to dodge Gemma (Gemma is opt-in-disabled by default now, see §3.1), but pinning to the same provider `knowledge-extraction-v1` actually resolves to is still the most faithful check of what production will really use. `preflight()` doesn't yet accept a *chat profile* directly (only `embedding_profile`) — passing `chat_provider="anthropic-sonnet"` is the current equivalent; adding a `chat_profile=` parameter that resolves through `CHAT_PROFILES` the same way `embed(profile=...)` does would be a natural, small follow-up if this gets adopted.
4. **Version tracking:** `llm-gateway-v7` is now `0.2.0`. If `merged-ingestion`'s own `test_llm_gateway_policy.py` / `test_runner.py` ever assert an exact version, update the assertion; otherwise no action needed.

## 5. What did NOT change

- Chat routing, provider order, rate limits (`router.py`), tool translation — untouched.
- The Gemini embedding fallback — untouched; `PROFILES["chunker-v1"]` is pinned to `ollama` only. A profile that tolerates failover to a same-dimension-but-different-model fallback would defeat the point of pinning, so none was added.
- Batch APIs (T3 plan item #4) and the multimodal/VLM contract (T3 plan item #5) — **not addressed here**, deliberately deferred until T28/T17 are actually picked up (see `PLAN_T3_llm_gateway_policy_2026-07-26.md` §5).

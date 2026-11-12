# Unified implementation plan: evolve `glc_v5` from `llm_gateway`

Date: 2026-09-06  
Status: approved scope; implementation has not started.

## Goal

Make `Final Gateway/glc_v5` an independent, locally versioned gateway and add the useful `llm_gateway` capabilities without dismantling its larger control-plane code.

The delivered gateway will support:

- four named Ollama-backed local providers: `ollama`, `gemma`, `phi4-local`, and `cover-vision-local`;
- exact, config-defined chat and embedding profiles;
- direct OpenAI and Anthropic API providers when their keys are configured;
- a live preflight endpoint for chat and embeddings; and
- a small Python client for the new GLC API.

## Decisions already made

- `glc_v5` is the base. This is an additive migration, not a cleanup or a merge of the two codebases.
- `Final Gateway` is only a parent directory. Repository work applies to `Final Gateway/glc_v5`, which currently has inherited Git metadata.
- The new repository will have no inherited history and no remote until its owner supplies a destination.
- Gemini, routing/classifier, cascade/escalation, policy, channels, audit, economics, voice, and the existing agent/control-plane code remain intact and are not activated, removed, or tuned in this work.
- Gemini is inactive in the target deployment simply by leaving its API-key environment variables unset. Its code and routing configuration remain unchanged.
- OpenAI and Anthropic are direct adapters, not proxy-only integrations. They are registered only when their respective keys are non-empty.
- Existing dependent projects will be adapted later. This migration provides the best new GLC client contract; preserving `llm_gateway/client.py` paths is not required.
- No API key values, `.env` files, tokens, databases, virtual environments, or caches may be committed.

## Current state and migration constraint

`glc_v5` currently has an inherited `origin` remote and four uncommitted Phase 1 draft paths:

- `glc/config.py`
- `glc/providers.py`
- `glc/local_models.yaml`
- `tests/test_local_models.py`

The first baseline commit must represent the copied source before those drafts. Preserve the draft as an external patch, establish the baseline, then reapply it for review in Phase 1. Do not overwrite unrelated user changes.

## Ownership and working rules

One integration owner performs Git surgery, changes shared endpoint/schema files, runs complete verification, and creates commits. Focused contributors may own provider/config, profiles/embeddings, or client/preflight work, but must preserve concurrent edits and never revert unrelated work.

Every phase is independently reviewable and has exactly one implementation commit. Live checks that require models or credentials are opt-in: report them as skipped when unavailable rather than treating them as passing.

## Phase 0 — independent repository baseline

1. Record `glc_v5`'s current status, HEAD, and remotes in a temporary note outside `glc_v5`.
2. Export the four known Phase 1 draft paths, including untracked files, as a patch outside `glc_v5`.
3. Revert only those draft paths and confirm the copied source matches its inherited HEAD. Stop if unrelated modifications are present.
4. Move (do not delete) `glc_v5/.git` to a timestamped location outside the repository, then initialize a new Git repository with no remote.
5. Check that secrets and runtime artifacts are ignored and untracked.
6. Commit the clean imported source: `baseline: import glc_v5 as standalone repository`.
7. Reapply the saved Phase 1 patch without committing it.

**Gate:** one commit only; no remote; recoverable old metadata; working tree contains only the four known Phase 1 paths; no sensitive/runtime file tracked.

## Phase 1 — local-model catalogue and Ollama correctness

Add `glc/local_models.yaml` and validate it at startup. Each entry must define `model`, `needs_think_false`, `vision`, and `context_window`.

Register the named Ollama providers `ollama`, `gemma`, `phi4-local`, and `cover-vision-local`, all using `OLLAMA_URL`. Resolve configuration per provider so `OllamaProvider.chat()` only sends `think: false` where the corresponding model requires it. Normalize Ollama completion reasons `length` and `max_tokens` to the gateway stop reason `max_tokens`. Populate correct rate/context metadata for every separately named provider.

**Verification:** registry and mocked wire-payload tests; `/v1/providers` lists all four names; both truncation spellings normalize correctly; lint passes. Run a tiny-token live check only if the local models exist.

**Commit:** `phase 1: configure local models and normalize Ollama completion`

## Phase 2 — pinned, config-driven profiles

Create versioned `glc/profiles.yaml`, with separate `embedding` and `chat` mappings, using GLC's established packaged-default, user-config, and environment-override loading precedence.

Port the supported pins, including `chunker-v1`, `knowledge-extraction-v1`, `document-segmentation-v1`, `highlight-photo-summary-v1`, and `cover-classification-v1`. Add optional `profile` fields to chat and embedding request/response schemas.

A profile resolves to exactly one provider/model. A request may use either a profile or dynamic `provider`/`model` selection, never both; reject conflicts with HTTP 400 before a provider call. An unavailable pinned provider returns HTTP 503 and must not enter the fallback ring. After a live call, validate the returned model and, for embeddings, dimension; a mismatch is a clear server error, never a successful payload.

Add `GET /v1/chat/profiles/{profile}`, include useful profile metadata in discovery, and echo the selected profile in success responses and logs. Use an additive database migration only if the current ledger lacks the needed field.

**Verification:** known, unknown, conflicting, unavailable, model-mismatch, and dimension-mismatch tests for both profile kinds; backward compatibility for dynamic selection; lint passes.

**Commit:** `phase 2: add pinned chat and embedding profiles`

## Phase 3 — direct OpenAI and Anthropic adapters

Implement native `OpenAIProvider` and `AnthropicProvider` adapters within the existing provider interface. Retain GLC's canonical inline-image format and port Anthropic schema cleaning without weakening the gateway's final JSON Schema validation.

Cover text, tools, structured output, usage, stop reasons, model overrides, and normalized provider errors. Register each provider only when its key is set; use stable names matching Phase 2 profile pins. Add real vendor-specific limits, shortcuts, capability information, and status information. Add empty `OPENAI_API_KEY=` and `ANTHROPIC_API_KEY=` placeholders to `.env.example`.

**Verification:** mocked adapter contract tests; providers absent with blank keys and available with configured keys; startup/discovery work with no cloud keys; lint passes. Live minimum calls are marked opt-in and skipped without credentials.

**Commit:** `phase 3: add direct OpenAI and Anthropic adapters`

## Phase 4 — first-class preflight

Add typed `POST /v1/preflight`. It makes one minimal real chat request through the selected/default chat path and one minimal embedding request through the default embedding profile. Both checks always run independently.

Return a structured report containing overall `ok` plus provider, model, latency, and bounded safe error text per path. Expected authentication, model, and provider failures are report data, not an endpoint-level 500. Never expose credentials or raw authorization headers.

**Verification:** success, chat-only failure, embedding-only failure, and both-fail tests using application fakes, plus an in-process integration test; a deliberately broken provider yields a valid `ok: false` report; lint passes.

**Commit:** `phase 4: add live chat and embedding preflight`

## Phase 5 — Python client

Add `glc/client.py` with a compact synchronous `LLM` client unless existing GLC conventions establish a better shared sync/async pattern. Implement `chat`, `stream`, `embed`, `preflight`, and `resolve_chat_profile` against the real GLC routes and response shapes.

Expose configurable base URL and timeout, raise errors that retain HTTP status and safe server detail, and ensure streaming releases network resources when iteration ends early.

**Verification:** mocked HTTP contract test for every public method, including early stream cleanup; in-process or development-server exercise of all methods; live calls remain opt-in; lint passes.

**Commit:** `phase 5: add the GLC Python client`

## Final integration gate

1. Run the full unit/integration suite, repository lint, and configured type checks.
2. Start the app with cloud keys unset and check `/healthz`, `/v1/providers`, `/v1/embedders`, `/v1/capabilities`, and `/v1/status`.
3. Call `/v1/preflight`. Unavailable local infrastructure is acceptable only as a structured per-path failure, never an endpoint crash.
4. Confirm Git history contains the baseline and five phase commits (apart from narrowly documented review fixes), and `git remote -v` is empty.
5. Confirm no secrets, databases, virtual environments, caches, or old Git backup are tracked.
6. Deliver a handoff report with tests run, tests skipped and why, new config files/endpoints, and environment-only follow-up checks.

## Deferred work

The following are explicitly outside this implementation: routing tier/order tuning; classifier/router behavior; cascade/escalation policy; activation of policy, channels, audit, economics, voice, and agent systems; compatibility updates in dependent projects; and reconciliation of `/v1/vision` with inline chat image blocks.

The dashboard concept is also deferred. Once direct providers are working, a separate UI can visualize calls using existing status, provider, capability, and call-history endpoints without changing this backend migration.

## Stop conditions

Pause for owner direction if unrelated edits appear in target paths; old Git metadata cannot be moved recoverably; a required profile pin cannot be identified; a phase requires tuning/activating deferred systems; credentials are needed for a non-optional live check; or a remote destination is needed.


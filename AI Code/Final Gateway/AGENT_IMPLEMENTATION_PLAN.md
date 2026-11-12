# Agent execution plan: standalone `glc_v5` migration

Date: 2026-09-06
Status: planning only; do not execute until approved.
Source plan: `IMPLEMENTATION_PLAN.md`
Target repository: `Final Gateway/glc_v5`

## Outcome

Turn `glc_v5` into a new, independent Git repository and implement Phases 1–5
from `IMPLEMENTATION_PLAN.md` without deleting or activating the deferred GLC
subsystems.

The new repository must:

- have no commit history inherited from `theschoolofai/glc_v5`;
- have no Git remote until the owner supplies the new destination;
- contain one clean baseline commit of the copied source;
- contain one reviewable commit per implementation phase;
- leave Gemini, routing/classifier, cascade/escalation, policy, channels, audit,
  economics, and voice unchanged except where additive schema fields or shared
  provider registration are strictly necessary;
- never copy API-key values into source control.

## Current-state note

The copied directory still contains its original `.git` directory and has this
remote configured:

`origin https://github.com/theschoolofai/glc_v5.git`

There is also an uncommitted Phase 1 draft made during initial inspection:

- modified: `glc/config.py`
- modified: `glc/providers.py`
- new: `glc/local_models.yaml`
- new: `tests/test_local_models.py`

These changes must not contaminate the clean imported-source baseline. Phase 0
therefore preserves the draft as a patch outside `glc_v5`, restores only those
known draft changes, creates the independent baseline, and then reapplies the
patch for review during Phase 1.

## Agent roles

### Root/integration agent

Owns repository separation, phase gates, commits, full-suite verification, and
all edits to cross-cutting files:

- `.git` repository state
- `glc/main.py`
- `glc/llm_schemas.py`
- `glc/routes/chat.py`
- `.env.example`
- `pyproject.toml`
- integration tests and final documentation

Only this agent creates commits. Worker agents return reviewed working-tree
changes to the root agent. This avoids competing commits in the shared working
tree.

### Provider/config agent

Owns:

- `glc/providers.py`
- `glc/config.py`
- `glc/local_models.yaml`
- provider-focused tests

Works on Phase 1 first and Phase 3 later. It must not tune routing policy.

### Profile/embedding agent

Owns:

- `glc/profiles.yaml`
- `glc/embedders.py`
- profile loader/validator module if one is introduced
- profile-focused tests

Coordinates schema and route edits with the root agent rather than editing
cross-cutting files concurrently.

### Client/preflight agent

Owns:

- `glc/client.py`
- client tests
- preflight-focused tests

It may design Phase 4 and Phase 5 in parallel after the profile contract is
fixed, but the root agent integrates Phase 4 before Phase 5.

All workers must be told that they are sharing the codebase, must preserve
other agents' edits, and must not revert unrelated changes.

## Phase 0 — detach and establish a clean baseline

Owner: root/integration agent only. No parallel work during repository surgery.

1. Record the current source repository's `git status`, HEAD, and remotes in a
   temporary migration note outside `glc_v5`.
2. Export the known Phase 1 draft as a patch outside `glc_v5`, including the
   two untracked files.
3. Reverse only the four known draft changes and verify that the copied source
   matches its current HEAD. Do not touch unrelated user files.
4. Move the old `.git` directory to a timestamped backup outside `glc_v5`.
   Do not delete it. This makes the operation recoverable.
5. Run `git init` in `glc_v5`, create the new default branch, and confirm
   `git remote -v` is empty.
6. Confirm ignored secrets/runtime files are absent from the index. In
   particular, `.env`, databases, tokens, caches, and `.venv` must not be
   tracked.
7. Commit the exact copied application state as:
   `baseline: import glc_v5 as standalone repository`
8. Reapply the saved Phase 1 draft without committing it.

Gate:

- `git log --oneline` contains exactly one commit;
- `git remote -v` prints nothing;
- the old `.git` is recoverable from the external backup;
- `git status --short` contains only the four known Phase 1 draft paths;
- no secret file is tracked.

## Phase 1 — local model catalogue and Ollama fixes

Owner: provider/config agent. Reviewer/integrator: root agent.

1. Review the reapplied draft against the source plan; do not accept it merely
   because it already exists.
2. Add config-driven local registrations for `ollama`, `gemma`, `phi4-local`,
   and `cover-vision-local`, all sharing `OLLAMA_URL`.
3. Validate every config entry has `model`, `needs_think_false`, `vision`, and
   `context_window`; malformed config must fail startup clearly.
4. Make `OllamaProvider.chat()` set `think: false` only from the resolved model
   config.
5. Normalize Ollama `done_reason` values `length` and `max_tokens` to gateway
   `stop_reason: max_tokens`.
6. Populate rate/context metadata for every separately named local provider.
7. Test the provider registry and mocked Ollama wire payload. If the four
   models are installed locally, run the live tiny-`max_tokens` check too;
   otherwise record that live-model verification remains environment-gated.

Gate:

- targeted tests pass;
- `/v1/providers` contract test lists all four local provider names;
- truncation tests pass for both upstream done-reason spellings;
- lint passes for touched files.

Commit:

`phase 1: configure local models and normalize Ollama completion`

## Phase 2 — config-driven embedding and chat profiles

Owners: profile/embedding agent plus root agent for schemas/routes.

1. Define one versioned `glc/profiles.yaml` containing separate `embedding` and
   `chat` mappings.
2. Port all currently supported pins from `llm_gateway`, including
   `chunker-v1`, `knowledge-extraction-v1`, `document-segmentation-v1`,
   `highlight-photo-summary-v1`, and `cover-classification-v1`.
3. Load profiles using the same packaged-default, user-config, and env-override
   precedence used by other GLC YAML configuration.
4. Add optional `profile` fields to chat/embed request and response schemas.
5. Reject `profile` combined with `provider` or `model` using HTTP 400 before
   contacting any provider.
6. Resolve a profile to exactly one live provider/model. An unavailable pin
   returns HTTP 503 and must never enter the normal fallback ring.
7. Verify the returned provider model and embedding dimension after the live
   call. A mismatch returns a clear server error and never returns the payload
   as success.
8. Add `GET /v1/chat/profiles/{profile}` and expose profile metadata from the
   relevant discovery endpoints.
9. Echo the profile in successful responses and logs. Add the database column
   only if the current GLC ledger does not already support it, using the
   existing additive migration pattern.

Gate:

- known, unknown, conflicting, unavailable, model-mismatch, and dim-mismatch
  tests pass for both profile kinds;
- a profile request cannot silently fall back;
- existing dynamic provider/model requests remain backward compatible;
- targeted tests and lint pass.

Commit:

`phase 2: add pinned chat and embedding profiles`

## Phase 3 — direct OpenAI and Anthropic providers

Owner: provider/config agent. Root agent integrates environment and routing
metadata only; routing order itself is not tuned.

1. Port direct adapters into the existing provider interface while retaining
   GLC v5's canonical inline-image format.
2. Port Anthropic schema cleaning without weakening gateway-side validation of
   the caller's original JSON Schema.
3. Cover text, tools, structured output, usage, stop reasons, model overrides,
   and provider errors with mocked contract tests.
4. Register each vendor only when its API key is non-empty. Use stable provider
   names that match the Phase 2 chat-profile pins.
5. Add real vendor-specific entries to `LIMITS`, `SHORTCUTS`, capability
   reporting, and status reporting. Do not borrow proxy-provider limits.
6. Document empty key placeholders in `.env.example`; never add real keys.
7. Verify startup and all discovery routes with both keys absent.
8. Run opt-in live smoke tests only when the user supplies keys through the
   environment. Live tests must be marked and skipped by default.

Gate:

- adapter contract tests pass;
- providers are absent when keys are unset and present when set;
- existing providers still start and route normally;
- live minimal calls pass when credentials are available, otherwise the gate
  explicitly records `not run: credentials unavailable` rather than faking a
  pass;
- targeted tests and lint pass.

Commit:

`phase 3: add direct OpenAI and Anthropic adapters`

## Phase 4 — first-class preflight endpoint

Owners: client/preflight agent for tests/design, root agent for route
integration.

1. Add a typed `POST /v1/preflight` request/response contract.
2. Perform one real minimal chat through the selected/default chat path and one
   real minimal embedding call through the default embedding profile.
3. Run both checks independently and aggregate results so one failure does not
   suppress the other.
4. Always return a structured per-path report. Expected provider/auth/model
   failures are data in the report, not an unhandled endpoint 500.
5. Include overall `ok`, provider, model, latency, and a bounded safe error
   message. Never return credentials or raw authorization headers.
6. Test success, chat-only failure, embed-only failure, and both-fail cases
   with application-level fakes, plus an in-process integration test.

Gate:

- all four aggregation outcomes are tested;
- a deliberately broken provider produces `ok: false` for that path and a
  valid endpoint response;
- endpoint behavior is documented;
- targeted tests and lint pass.

Commit:

`phase 4: add live chat and embedding preflight`

## Phase 5 — Python client

Owner: client/preflight agent. Reviewer/integrator: root agent.

1. Add `glc/client.py` with a small synchronous `LLM` client unless existing
   project conventions strongly favor separate sync/async classes.
2. Implement `chat`, `stream`, `embed`, `preflight`, and
   `resolve_chat_profile` against the actual GLC routes and response shapes.
3. Use one configurable base URL and timeout; raise errors that include the
   HTTP status and safe server detail.
4. Ensure streaming closes network resources when iteration finishes early.
5. Unit-test every method with mocked HTTP transport.
6. Exercise every method against an in-process or running dev server. Calls
   requiring real models/keys remain opt-in and clearly reported.

Gate:

- every public method has a passing contract test;
- stream cleanup is tested;
- profile and preflight errors retain useful server detail;
- targeted tests and lint pass.

Commit:

`phase 5: add the GLC Python client`

## Final integration gate

Owner: root/integration agent.

1. Run the complete unit/integration test suite.
2. Run Ruff on the entire repository and any configured type checks.
3. Start the app with all cloud keys unset; check `/healthz`, `/v1/providers`,
   `/v1/embedders`, `/v1/capabilities`, and `/v1/status`.
4. Run `/v1/preflight`; local failures are acceptable only when the relevant
   daemon/model is genuinely unavailable, and must appear as structured check
   failures rather than endpoint crashes.
5. Inspect `git log` for the baseline plus exactly five phase commits (apart
   from any narrowly documented fixup commit approved during review).
6. Confirm `git remote -v` remains empty.
7. Confirm no `.env`, key, token, database, `.venv`, cache, or old `.git`
   backup is tracked.
8. Produce a handoff report listing tests run, tests skipped and why, config
   files added, endpoints added, and any environment-only live checks still
   needed.

## Stop conditions

Stop and ask the owner before continuing if:

- an unrelated user modification appears in the target paths;
- separating Git would require deleting rather than moving the old metadata;
- a profile's exact provider/model pin cannot be determined from the source
  gateway;
- implementing a phase would require tuning or activating a deferred subsystem;
- credentials are needed for live verification and have not been supplied;
- the new remote destination is needed. It is intentionally not configured
  until the owner provides it.

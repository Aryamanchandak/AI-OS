# Gateway trim plan 2: make the gateway LLM-only (for Codex)

Written 2026-10-17. **Run only after `TRIM_PLAN.md` steps 1–4 are finished and committed.**

## Goal

The gateway does one job: **how agents talk to an LLM.** Anything else gets deleted from it. If any
of it comes back later, it gets built as its own separate system, not re-added here. A copy of the
current code exists outside this repo, so no git tags or backups are needed.

## What stays and what goes

| Stays (LLM job) | Goes (not LLM) |
| --- | --- |
| `llm/`: chat, embeddings, providers, budgets, cache | `voice/`: speech-to-text, text-to-speech |
| `audit/`: LLM calls are written to it | `channels/`: all 15 adapters **and** the framework |
| `ledger/`: LLM call cost records | `control/`: pairing, presence, policy reload, kill |
| `platform/`: config, service registry, telemetry, startup checks | `policy/`: tool-call allow/deny rules |
| `security/ssrf.py`: LLM code uses it to fetch images safely | `security/` allowlists, pairing, rate limits, trust levels |
| `app/`: assembles the above | `config/channels.yaml`, `config/policy.yaml` |

Why the second column is safe to delete:

- **Control, pairing, allowlists, rate limits and trust levels** exist only to decide which
  channel users may send messages. No LLM code uses them.
- **The policy engine** is loaded at startup, but nothing in the gateway ever asks it for a
  decision. It holds the rules for tool actions (sending email, deleting files). Those rules belong
  wherever actions are taken, not in the LLM gateway.
- **The kill switch** (`/v1/control/kill`) sets a flag that nothing reads, so it does nothing today.

## Hard rules

1. **Work only inside `AI OS/gateway/`.** Don't read, list, edit or delete anything outside it.
   The git repo root is one level up, so `git status` will show `../` paths. Ignore them.
2. **Don't touch:** any docs except `README.md`, and only the edits listed in step 3. Docs inside the
   folders being deleted go with their folder. Also don't touch anything under
   `src/gateway/llm/`, `src/gateway/audit/`, `src/gateway/ledger/`, `src/gateway/security/ssrf.py`,
   `conftest.py`, `tests/test_llm*.py`, `tests/test_foundation.py`, `test_main.py`, or
   `tests/test_standalone_bootstrap.py`. The one exception is the single edit to that last file
   listed in step 2a.
3. **Only delete or edit the files named below.** If another file turns out to need a change, stop
   and report it. Don't make the change.
4. **Never skip, loosen or delete a test** except where a step below says so explicitly. The only
   tests deleted here are tests of deleted code.
5. **Do one step at a time** (there are 3). After each step, run the checks, show the full output,
   and stop. The user commits before the next step starts.

## Baseline (before step 1)

Run from `gateway/`:

```bash
.venv/bin/python -m pytest -q -p no:cacheprovider
.venv/bin/python -m mypy --config-file mypy.ini main.py src/gateway
find src/gateway -name '*.py' -not -path '*/__pycache__/*' | xargs cat | wc -l
```

Record all three results. It should be the end state of `TRIM_PLAN.md`: exactly 4 failures (the
shell/migration ones listed in `TRIM_PLAN.md` step 4e). Later steps must not add failures or mypy
errors.

---

## Step 1: Delete voice

### 1a. Edit tests first

**`tests/test_channels_voice_migration.py`** (the rest of this file is deleted in step 2):

- Delete `test_transcribe_route_preserves_response_shape_when_explicitly_enabled` and the `_STT`
  helper class above it.
- Delete the imports from `gateway.voice.routes`, `gateway.voice.stt.base`, and
  `gateway.voice.stt.router`. Remove `VOICE_PROVIDERS` from the `gateway.channels.service` import.
  Remove `import base64` if nothing else uses it.
- In `test_every_channel_and_voice_adapter_is_registered_dormant`: delete the `"voice": {...}` key,
  change `len(presence) == 23` to `== 15`, and change
  `set(CHANNEL_BOUNDARIES) | set(VOICE_PROVIDERS)` to `set(CHANNEL_BOUNDARIES)`.

### 1b. Delete

- `src/gateway/voice/` (whole folder)
- `tests/voice/` (whole folder)

Deleting `src/gateway/voice/` also removes these. Nothing extra to do; they're listed so you can
check that they're gone:

- Docs: each provider's `README.md` under `voice/stt/providers/` (`gemini_live`, `groq_whisper`,
  `whisper_cpp`) and `voice/tts/providers/` (`cartesia`, `elevenlabs`, `gemini_live`, `kokoro`,
  `system_fallback`), plus `voice/stt/providers/gemini_live/SETUP.md`.
- Tests stored inside the source folder: `voice/tts/providers/cartesia/tests/`,
  `voice/tts/providers/elevenlabs/tests/`, and `voice/tts/providers/kokoro/tests_internal/`.
- Scripts used only by hand: the `smoke.py` files under both `gemini_live` folders, and
  `kokoro/demo.py`.

### 1c. Edit code

**`src/gateway/app/router_registry.py`**: remove the `gateway.voice.routes` import and
`voice_registration(),`.

**`src/gateway/channels/service.py`**: delete the `VOICE_PROVIDERS` dict, the `voice_enabled`
method, and the 3-line `for name, (kind, provider) in VOICE_PROVIDERS.items():` loop in
`presence()`. (Throwaway edit, since step 2 deletes this file. It keeps step 1 passing on its own.)

**`config/channels.yaml`**: delete the `voice:` block.

**`mypy.ini`**: delete the `[mypy-gateway.voice.stt.providers.*]` and
`[mypy-gateway.voice.tts.providers.*]` sections.

**`pyproject.toml`**: remove the two `gateway.voice...` entries from `[[tool.mypy.overrides]]`.
Remove `"numpy>=1.26"` only if this returns nothing:
`grep -rnE "^\s*(import|from) numpy" --include='*.py' src tests . --exclude-dir=.venv`.
Otherwise keep it and report the match.

Then:

```bash
uv lock
uv sync --no-editable --extra dev
.venv/bin/python export_openapi.py
```

### 1d. Check

```bash
grep -rnE "gateway\.voice|VOICE_PROVIDERS|voice_enabled" \
  --include='*.py' --include='*.yaml' --include='*.toml' --include='*.ini' . --exclude-dir=.venv
grep -oE '"/[^"]*(transcribe|speak)[^"]*"' openapi.json
test ! -e src/gateway/voice && test ! -e tests/voice && echo "voice folders gone"
.venv/bin/python -m pytest -q -p no:cacheprovider
.venv/bin/python -m mypy --config-file mypy.ini main.py src/gateway
```

- First grep: no matches.
- openapi grep: no matches. `/v1/transcribe` and `/v1/speak` are gone from the API schema.
- Folder check prints `voice folders gone`.
- pytest: same 4 failures as baseline, no new ones. The openapi staleness test passes.
- mypy: no new errors.

**User commits:**

```bash
cd "/Users/aryamanchandak/Documents/AI OS/gateway"
git add -u .
git commit -m "Remove voice (STT/TTS) from gateway"
```

`git add -u .` stages only changes to files git already tracks, and only inside `gateway/`.

---

## Step 2: Delete channels, control, policy and channel security (trunk change, so tests first)

These four have to go together, because they import each other. For example, control's presence
route reads channels, and channels' routes use control's token.

### 2a. Delete or edit tests first

Delete these whole files. Every test in them tests code being deleted:

- `tests/channels/` (whole folder)
- `tests/test_channels_voice_migration.py`
- `tests/test_security_characterization.py`: allowlist, trust level, pairing, rate limit, kill,
  and policy SIGHUP reload
- `tests/test_policy_matcher.py`: policy engine

**`tests/test_platform_security_control.py`**

- Delete these tests (they test deleted code):
  `test_malformed_policy_refuses_startup_with_structured_dependency`,
  `test_policy_reload_route_preserves_auth_and_audits`,
  `test_pairing_and_presence_contract_round_trip`,
  `test_kill_compatibility_suspends_only_glc`,
  `test_rate_limit_refusal_is_stable`,
  `test_policy_reload_is_atomic_on_invalid_replacement`,
  `test_pairing_repository_has_only_live_tables`.
- Remove the imports `from gateway.policy import PolicyEngine` and
  `from gateway.security import PairingStore, RateLimiter`.
- In the `glc_environment` fixture, remove the `policy`, `channels`, `pairing`, `token_file` and
  `token` entries, the two files it writes for them, and their `monkeypatch.setenv` lines. Keep
  `audit`, `ledger` and `cache`.
- In `test_database_defaults_are_centralized_under_database_sqlite`, remove `paths.pairing_db` from
  the tuple. Keep every assertion.
- Keep unchanged: the startup-check, semantic-cache, telemetry, audit, SSRF, ledger and legacy-import
  tests.

**`tests/test_restored_contracts.py`**

- Delete `test_channel_send_auth_errors_success_and_failure_are_audited` and
  `test_channel_send_disabled_and_audit_failure_prevent_send`.
- Remove `from gateway.channels.envelope import ChannelReply`.
- Leave everything else, including the already-failing baseline test.

**`tests/test_standalone_bootstrap.py`** (the one allowed exception to hard rule 2)

- In the tuple `("GLC_GATEWAY_DB", "GLC_AUDIT_DB", "GLC_PAIRING_DB", "GLC_CACHE_DB")`, remove
  `"GLC_PAIRING_DB"`. The test clears these env vars so it starts from defaults, and that variable
  no longer exists. Change nothing else; no assertion changes.

### 2b. Delete code and config

- `src/gateway/channels/` (whole folder, including its `ADMIN_UI.md`)
- `src/gateway/control/` (whole folder)
- `src/gateway/policy/` (whole folder)
- `src/gateway/security/allowlists.py`, `pairing.py`, `rate_limits.py`, `trust.py`, `trust_level.py`
- `config/channels.yaml`, `config/policy.yaml`

Deleting `src/gateway/channels/` also removes these. Nothing extra to do; they're listed so you can
check that they're gone:

- Docs: `channels/ADMIN_UI.md`; the `README.md` in each of the 15 folders under
  `channels/catalogue/`; the `RUNTIME.md` files in those folders; and
  `catalogue/discord/PRIVACY_POLICY.md` and `catalogue/discord/TERMS_OF_SERVICE.md`.
- Example credential files: `catalogue/discord/env.example`, `catalogue/line/dev/line.env.example`.
- Tests stored inside the source folder: `catalogue/discord/tests/`, `catalogue/twilio_sms/tests/`,
  `catalogue/whatsapp/tests/`, and `catalogue/twilio_voice/test.py`.
- Scripts used only by hand: `catalogue/line/dev/`, `catalogue/telegram/dev/`,
  `catalogue/teams/setup/`, `catalogue/whatsapp/demo_webhook_server.py`.

### 2c. Edit trunk files

**`src/gateway/security/__init__.py`**: replace the whole file with one docstring line:
`"""Outbound-fetch SSRF guard used by the LLM service."""`. `ssrf.py` stays and is imported
directly by `llm/orchestration/normalization.py`.

**`src/gateway/app/router_registry.py`**: remove the `gateway.control.routes` and
`gateway.channels.routes` imports and `control_registration(),` / `channels_registration(),` from
the tuple.

**`src/gateway/app/lifespan.py`**

- Remove imports: `ControlService`, `PolicyEngine`, `PairingStore`, `RateLimiter`, the four
  `gateway.channels...` imports, and `Allowlist, bind_allowlist, bind_pairing_store, bind_rate_limiter`.
- Delete `_reload_policy_on_sighup`, and in `lifespan()` delete everything about SIGHUP
  (`previous_sighup` and both `signal` blocks). Remove `import signal` and `import sys` if unused.
  Remove `Any` from the `typing` import if unused.
- In `build_container`, delete the lines that build `policy`, `pairings`, `rate_limiter`,
  `channels_config` (all three lines), `allowlist`, the three `bind_*` calls, `install_token`,
  `bind_install_token`, `control`, `agent_url`, and `channel_service`.
- Delete `StartupCheck("policy.yaml", ...)` and `StartupCheck("pairing database", ...)`.
- In `DependencyContainer(...)`, remove `policy=`, `pairings=`, `rate_limiter=`, `control=`,
  `channels=`.

**`src/gateway/app/dependencies.py`**

- Remove imports: `ControlService`, `PolicyEngine`, `PairingStore, RateLimiter`, `ChannelService`.
- Remove fields: `policy`, `pairings`, `rate_limiter`, `control`, `channels`.
- In `close()`, remove `await self.channels.close()`.
- Delete `get_control_service` and `get_channel_service`.

**`src/gateway/platform/configuration/glc.py`**: remove the `policy`, `channels`, `pairing_db` and
`install_token` attributes, the `get_or_create_install_token` method, and `import secrets`.

**`config/services.yaml`**: delete the `telegram_worker:` block. Keep `agent_runtime`, because
observability uses it.

**`mypy.ini`**: delete the `[mypy-gateway.channels.catalogue.*]` section.

**`pyproject.toml`**

- Delete the whole `[[tool.mypy.overrides]]` block (nothing left in it).
- Remove `"twilio>=9.0"` only if this returns nothing:
  `grep -rnE "^\s*(import|from) twilio" --include='*.py' src tests . --exclude-dir=.venv`.

Then:

```bash
uv lock
uv sync --no-editable --extra dev
.venv/bin/python export_openapi.py
```

### 2d. Final check for leftover references

```bash
grep -rnE "gateway\.(channels|control|policy)|PairingStore|Allowlist|RateLimiter|bind_install_token|get_or_create_install_token|pairing_db|channels\.yaml|policy\.yaml|security\.(pairing|allowlists|rate_limits|trust)|GLC_PAIRING_DB|GLC_POLICY_YAML|GLC_CHANNELS_YAML|GLC_INSTALL_TOKEN_FILE|GLC_CHANNEL_SECRETS_DIR|GLC_S16_BRIDGE_TOKEN|telegram_worker" \
  --include='*.py' --include='*.yaml' --include='*.toml' --include='*.ini' . --exclude-dir=.venv
grep -oE '"/[^"]*(channel|control|webhooks)[^"]*"' openapi.json
for p in src/gateway/channels src/gateway/control src/gateway/policy tests/channels \
         config/channels.yaml config/policy.yaml; do test -e "$p" && echo "STILL THERE: $p"; done
```

Expected: both greps print nothing, and the loop prints nothing. Any output means stop and report
it. The openapi grep confirms that `/v1/channels*`, `/v1/channel-admin/*`, `/v1/control/*` and
`/webhooks/twilio_sms` are gone from the API schema.

### 2e. Run the checks

```bash
.venv/bin/python -m pytest -q -p no:cacheprovider
.venv/bin/python -m mypy --config-file mypy.ini main.py src/gateway
```

- pytest: the same 4 baseline failures, no new ones. The openapi staleness test passes.
- mypy: no new errors.

**Gateway must still start, and LLM routes must still be there:**

```bash
AI_OS_TOKEN=local-dev-token .venv/bin/python -c \
  "from fastapi.testclient import TestClient; from main import create_app; \
   c = TestClient(create_app(token='t')).__enter__(); \
   print(c.get('/health').json(), c.get('/api/diagnostics/services', headers={'Authorization': 'Bearer t'}).status_code); \
   print(sorted(p for p in c.app.openapi()['paths'] if 'llm' in p)[:5])"
```

Expected: `{'status': 'ok'} 200`, then a non-empty list of `/api/llm/...` paths.

**User commits:**

```bash
git add -u .
git commit -m "Make gateway LLM-only: remove channels, control, policy, pairing"
```

---

## Step 3: Remove the deleted features from `README.md` (docs only, no code)

Steps 1 and 2 delete the code and the docs inside its folders. `README.md` is the only surviving
doc that still describes the deleted features. Make **only** the edits below. Find each one by its
heading or quoted text, not by line number. Don't change anything about ingestion, the legacy
listener, `migration/`, the shell, or the regression commands (see Out of scope).

### 3a. Edits

1. **Top section, the paragraph starting "Port 8000 is the deliberate stable Gateway entry
   point."** Replace this text:

   > Run one Gateway process for chat, ingestion, control, audit, and short webhooks. Enable
   > long-running channel workers explicitly; Telegram's worker is started with
   > `python -m gateway.channels.catalogue.telegram.worker` only when configured.

   with:

   > Run one Gateway process for chat, ingestion, and audit.

2. **`## Restored operational contracts`**: delete the whole bullet that starts
   ``- `POST /v1/channels/{name}/send` sends a proactive `ChannelReply`.`` (3 lines). Keep the
   preflight and observability bullets.

3. **Same section, the paragraph starting "Gateway now owns the migrated GLC policy, security,
   audit, ledger, and control domains."** Replace the whole paragraph with:

   > Gateway owns the migrated GLC audit and ledger domains. Their SQLite files default to
   > `../Database/sqlite/audit.sqlite` and `gateway.sqlite`; `GLC_AUDIT_DB` and `GLC_GATEWAY_DB`
   > remain supported overrides. Audit writes are fail-closed.

4. **Same section, the paragraph starting "The compatibility control routes remain at
   `/v1/control/*`"** (the one about policy reload, SIGHUP and `/v1/control/kill`): delete the
   whole paragraph.

5. **`## Channels and voice`**: delete the whole section, from that heading down to (not
   including) `## Regression commands`.

### 3b. Check

```bash
grep -niE "channel|voice|telegram|twilio|pairing|install token|/v1/control|policy|SIGHUP|kill|presence|transcribe|speak|webhook|STT|TTS" README.md
git diff --stat -- README.md
```

- grep: no matches.
- `git diff --stat`: only `README.md` changed in this step, with deletions plus the 2 replaced
  paragraphs.
- Re-run the tests to confirm a docs-only change broke nothing:
  `.venv/bin/python -m pytest -q -p no:cacheprovider`. Expect the same 4 baseline failures.

**User commits:**

```bash
git add README.md
git commit -m "README: drop channels, voice, control and policy docs"
```

---

## Report back after all three steps

- One plain-English line for each deleted or edited file, including every doc deleted with its
  folder.
- Full pytest and mypy output from step 2e, and the pytest output from step 3b.
- Output of the checks in 1d, 2d and 3b (all should be empty apart from `voice folders gone`).
- `src/gateway/` line count before (baseline) and after.
- Anything unexpected that made you stop.

## Out of scope (later)

- `README.md` is still out of date on things `TRIM_PLAN.md` deferred: ingestion
  (`/ingestion`, `AI_OS_PREVIEW`, `INGESTION_DATABASE_ROOT`, `ingestion_tests`, the `mypy --strict`
  ingestion command), the legacy 8111 listener and `scripts/legacy_usage_report.py`,
  `migration/plan-07-cutover-status.md`, and the shell build commands. Step 3 leaves them alone on
  purpose.
- Runtime data outside `gateway/`, which hard rule 1 stops Codex from touching:
  `../Database/sqlite/pairings.sqlite`, `../Database/sqlite/glc_install_token` and
  `../Database/sqlite/channel_secrets/`. Delete them by hand if you want them gone.
- The shell's `/channels` admin screen (`../shell/src/screens/ChannelsAdmin.tsx`) is outside
  `gateway/`. Once step 2 lands, its API calls will fail.
- The `audit` table still has `channel`, `channel_user_id`, `trust_level` columns; LLM writes
  `channel="llm"`. Renaming them changes the database schema.
- The `/v1/*` alias routes, the routing fields in `llm/models.py`, and the 4 shell/migration test
  failures (all already deferred by `TRIM_PLAN.md`).
- The `OTHER_DOMAINS` list in `tests/test_llm_contract.py` still names `/v1/control/`,
  `/v1/channels`, `/v1/speak`. It's harmless: the test skips without the baseline file. Leave it,
  because it's checked against a historical baseline.

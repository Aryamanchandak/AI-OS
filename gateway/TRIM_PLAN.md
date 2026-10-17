# Gateway trim plan (for Codex)

Written 2026-10-17. Approved scope: delete build leftovers, legacy migration leftovers, the dead
routing config, and the ingestion feature. Nothing else.

## Hard rules

1. **Work only inside `AI OS/gateway/`.** Don't read, list, edit or delete anything outside it.
   That includes `../Old Code`, `../Original Code`, `../To Do`, `../Project plan` and `../shell`.
   The git repo root is one level up, so `git status` will show `../` paths. Ignore them.
2. **Don't touch:**
   - any docs (`*.md`, including `README.md`, `GATEWAY_REQUIREMENTS.md` and this file)
   - `src/gateway/channels/` and `tests/channels/`
   - `src/gateway/voice/` and `tests/voice/`
   - `conftest.py`
   - `tests/test_standalone_bootstrap.py`
   - `tests/test_restored_contracts.py`
3. **Only delete or edit the files named below.** If another file turns out to need a change, stop
   and report it. Don't make the change.
4. **Never skip, loosen or delete a test** except where a step below says so explicitly.
5. **Do one step at a time.** After each step, run the checks, show the full output, and stop. The
   user commits before the next step starts.

## Baseline (before step 1)

Run from `gateway/`:

```bash
.venv/bin/python -m pytest -q -p no:cacheprovider
.venv/bin/python -m mypy --config-file mypy.ini main.py src/gateway
```

Expected pytest result: **884 passed, 5 failed, 8 skipped.** These 5 failures exist before any
trimming. They happen because `../shell` and `../migration` were moved away. They are out of scope,
so don't fix them:

- `test_contract_staleness.py::test_committed_typescript_schema_is_current`
- `test_main.py::test_health_and_shell_entry_need_no_credentials[/ingestion]`
- `test_main.py::test_health_and_shell_entry_need_no_credentials[/]`
- `test_main.py::test_health_and_shell_are_available_but_ingestion_api_requires_bearer`
- `tests/test_restored_contracts.py::test_every_baseline_operation_is_registered_or_has_explicit_ui_replacement`

Record the mypy result too, since it hasn't been checked yet. Later steps must not add new mypy
errors.

---

## Step 1: Build leftovers

Delete:

- `build/`
- `src/ai_os_gateway.egg-info/`
- every `__pycache__/` directory under `gateway/`, but **not** inside `.venv/`
- `.pytest_cache/`
- `config/channels 2.yaml`. First confirm it's identical: `diff "config/channels.yaml" "config/channels 2.yaml"` must print nothing.

**Check:** pytest gives the same result as the baseline.
**Git:** all of these are already git-ignored, so there's nothing to commit.

---

## Step 2: Legacy migration leftovers

Delete:

- `src/gateway/compatibility/` (`__init__.py` and `legacy_listener.py`)
- `tests/test_legacy_listener.py`
- `tests/test_legacy_listener_live.py`
- `scripts/legacy_usage_report.py`
- `scripts/runtime_cutover_smoke.py`

Before deleting, confirm nothing else imports them:
`grep -rn "legacy_listener\|gateway.compatibility" --include='*.py' . --exclude-dir=.venv` should
match only the files above.

Leave these alone; they stay for now: the `/v1/*` alias routes, `/healthz`, `/dashboard`.

**Check:** pytest shows the same 5 failures and no new ones. The pass count drops only by the
tests deleted with the two legacy listener test files.

**User commits:**

```bash
cd "/Users/aryamanchandak/Documents/AI OS/gateway"
git add -u .
git commit -m "Remove legacy port-8111 listener and cutover scripts"
```

`git add -u .` stages only changes to files git already tracks, and only inside `gateway/`.

---

## Step 3: Dead routing config

Delete:

- `config/routing.yaml`. `src/gateway/llm/routing/__init__.py` states it is never consulted.
- `src/gateway/llm/routing/__init__.py` (the whole `llm/routing/` folder). Nothing imports
  `gateway.llm.routing`. Confirm with `grep -rn "llm.routing" --include='*.py' src tests`. It must
  return nothing.

**Don't** touch `src/gateway/llm/orchestration/routing.py`. It's a different, live file.
**Don't** edit `src/gateway/llm/models.py`. Its unused routing fields are deferred to a later
cleanup, because removing them changes the request and response formats.

**Check:** pytest shows the same result as after step 2.

**User commits:**

```bash
git add -u .
git commit -m "Remove dormant routing.yaml and empty llm.routing package"
```

---

## Step 4: Ingestion (trunk change, so tests first)

### 4a. Update `test_main.py` first

1. Remove these two imports:
   `import gateway.ingestion` and `import gateway.ingestion.preview`.
2. In `test_local_application_folders_are_connected`, delete only the line
   `assert gateway.ingestion.__file__ is not None`. Keep the other two asserts.
3. Change `PROTECTED_PATHS` from `("/api/ingestion/run", *sorted(SCHEMA_AND_DOCS_PATHS))` to
   `("/api/diagnostics/services", *sorted(SCHEMA_AND_DOCS_PATHS))`.
   The four login-check tests (missing token → 401, wrong token → 401, correct token → 200,
   no token configured → 503) keep checking exactly the same thing, against a route that still
   exists. Don't change those test bodies.
4. Leave `OPEN_PATHS` unchanged. Those are shell routes, which are still undecided.
5. Delete these tests. They test only ingestion behaviour:
   - `test_authorized_report_returns_the_typed_durable_record`
   - `test_health_and_shell_are_available_but_ingestion_api_requires_bearer`. Its health check is
     already covered by `test_health_stays_open_even_when_no_token_is_configured`, and its shell
     check by `test_health_and_shell_entry_need_no_credentials`.
   - `test_openapi_exposes_prefixed_ingestion_routes_only`
   - `test_preview_lifecycle_reaches_confirmed_completion`
6. Remove `import time` and `from typing import Any` if nothing uses them any more.

### 4b. Delete the ingestion code

- `src/gateway/ingestion/` (whole folder)
- `ingestion_tests/` (whole folder)
- `scripts/live_smoke.py`
- `scripts/verify_environment.py`

### 4c. Edit trunk files

**`src/gateway/app/main.py`**

- Replace `from gateway.ingestion.setup import AI_OS_ROOT as AI_OS_ROOT` with
  `from gateway.platform.configuration.glc import AI_OS_ROOT as AI_OS_ROOT`.
  Both resolve to the same `AI OS/` folder. `main.py` at the gateway root re-exports `AI_OS_ROOT`,
  so keep the name.
- Replace:
  ```python
  ingestion, *other_domains = migrated_domain_registrations()
  register_routers(
      app,
      (
          ingestion,
          _diagnostics_registration(),
          *other_domains,
      ),
  )
  ```
  with:
  ```python
  register_routers(
      app,
      (
          _diagnostics_registration(),
          *migrated_domain_registrations(),
      ),
  )
  ```

**`src/gateway/app/router_registry.py`**

- Remove the line `from gateway.ingestion.routes import registration as ingestion_registration`.
- Remove `ingestion_registration(),` from the returned tuple.

**`src/gateway/app/lifespan.py`**

- Remove the two imports:
  `from gateway.ingestion.setup import build_review_service` and
  `from gateway.ingestion.http_client import configure_gateway_url`.
- Remove the line `ingestion = _construct("ingestion review service", build_review_service)`.
- In the `except BaseException:` block after `run_startup_checks`, remove `ingestion.close()` and
  keep `telemetry.close()` and `raise`.
- Remove the line `configure_gateway_url(services.url_for("gateway"))`.
- Remove `ingestion=ingestion,` from the `DependencyContainer(...)` call.

**`src/gateway/app/dependencies.py`**

- Remove the two imports:
  `from gateway.ingestion.server import ReviewService` and
  `from gateway.ingestion.http_client import configure_gateway_url`.
- Remove the field `ingestion: ReviewService`.
- In `close()`, remove `self.ingestion.close()` and `configure_gateway_url(None)`.
- Delete the function `get_ingestion_service`.

**`pyproject.toml`**

Remove these dependencies. Each is imported only by ingestion code; confirm each with grep before
removing it:

- `chromadb`
- `neo4j`
- `ocrmac` (the line with the `sys_platform == 'darwin'` marker)
- `opencv-python`
- `pillow`
- `pillow-heif`
- `pymupdf`
- `python-docx`

Keep `numpy`, because voice text-to-speech uses it. Then run:

```bash
uv lock
uv sync --no-editable --extra dev
```

### 4d. Final check for leftover references

```bash
grep -rn "gateway.ingestion\|ingestion_tests\|build_review_service\|ReviewService" \
  --include='*.py' --include='*.toml' --include='*.ini' . --exclude-dir=.venv
```

The only expected matches are in `tests/test_restored_contracts.py` and
`tests/test_standalone_bootstrap.py`, which stay unchanged per rule 2. Any other match means stop
and report it.

### 4e. Regenerate the API schema and run the checks

```bash
.venv/bin/python export_openapi.py
.venv/bin/python -m pytest -q -p no:cacheprovider
.venv/bin/python -m mypy --config-file mypy.ini main.py src/gateway
```

**Expected pytest result:** exactly these **4** failures, the baseline ones minus the deleted test:

- `test_contract_staleness.py::test_committed_typescript_schema_is_current`
- `test_main.py::test_health_and_shell_entry_need_no_credentials[/ingestion]`
- `test_main.py::test_health_and_shell_entry_need_no_credentials[/]`
- `tests/test_restored_contracts.py::test_every_baseline_operation_is_registered_or_has_explicit_ui_replacement`

`test_contract_staleness.py::test_committed_openapi_schema_is_current` must **pass**. The four
`test_protected_paths_*` tests must pass for every path.

**Expected mypy result:** no new errors compared with the baseline.

**Gateway must still start:**

```bash
AI_OS_TOKEN=local-dev-token .venv/bin/python -c \
  "from fastapi.testclient import TestClient; from main import create_app; \
   c = TestClient(create_app(token='t')).__enter__(); \
   print(c.get('/health').json(), c.get('/api/diagnostics/services', headers={'Authorization': 'Bearer t'}).status_code)"
```

Expected output: `{'status': 'ok'} 200`.

**User commits:**

```bash
git add -u .
git commit -m "Remove ingestion domain from gateway"
```

---

## Report back after all steps

- One plain-English line for each deleted or edited file.
- The full pytest and mypy output from step 4e.
- Anything unexpected that made you stop.

## Out of scope (later)

Docs (including the now-stale ingestion sections in `README.md`), channels, voice, the routing
fields in `llm/models.py`, the `/v1/*` alias routes, the 4 shell/migration test failures, and
`AI_OS_PREVIEW` in `conftest.py` (now unused but harmless).

# Plan 02 — Gateway Foundation

## Related decisions

This plan builds the empty, packaged container: DI, lifecycle, config,
service registry. It imports no GLC runtime code (see "Explicitly out of
scope" below) — Plan 04 is what fills the container with GLC's actual LLM
domain code afterward, using the dependency container's typed construction
(§3) as the injection point for the `LLMService` protocol Plan 04 defines.
Plan 04 cannot start until this plan's container exists. The authentication
model decided here (§2) is the backend policy that `To Do/UNIFIED UI/
UNIFIED_UI_PLAN.md` consumes on the frontend side — that plan does not
redecide it here.

## Goal

Turn the current thin `gateway/main.py` application into a stable package that
can own multiple domains without accumulating global state or sibling-path
imports. Preserve the existing shell and ingestion API behavior.

## Proposed target

```text
gateway/
├── pyproject.toml
├── uv.lock
├── config/
│   ├── gateway.yaml
│   └── services.yaml
├── src/gateway/
│   ├── app/
│   │   ├── main.py
│   │   ├── lifespan.py
│   │   ├── middleware.py
│   │   └── dependencies.py
│   └── platform/
│       ├── configuration/
│       ├── networking/
│       ├── database/
│       ├── observability/
│       └── service_registry/
└── tests/
```

## Decisions required before implementation

### 1. Package and environment ownership

Proposed default: Gateway gets its own `pyproject.toml` and lockfile. During
migration it may reference imported domains as packages in the same workspace,
but it must stop borrowing ingestion's virtual environment as its documented
runtime.

Today `gateway/` has no `pyproject.toml`, no lockfile, and no virtual
environment of its own — `gateway/README.md`'s own regression commands run
gateway's tests with `../ingestion-pipeline/merged-ingestion/.venv/bin/python`
(the ingestion project's interpreter), not a gateway-owned one. That's the
"borrowing" this decision is about.

- **Approve a Gateway-owned environment and lockfile** means: add a
  `gateway/pyproject.toml` and run a lock step to produce `gateway/uv.lock`,
  giving gateway its own `.venv`. Cost: one more lockfile to keep current.
  Benefit: gateway can add or upgrade a dependency without touching
  ingestion's environment, and `cd gateway && pytest` works without reaching
  outside the folder for an interpreter — which also decouples gateway's
  Python version from ingestion's.
- **Use one root monorepo environment instead** means: one shared
  `pyproject.toml`/lockfile/`.venv` at the AI OS root, used by gateway,
  ingestion, and (later) GLC. Cost: a dependency bump for one domain can
  break another's tests, since they share one resolved set of versions.
  Benefit: one lockfile instead of several, and no risk of the domains'
  dependency sets silently drifting apart.

- [ ] Approve a Gateway-owned environment and lockfile.
- [ ] Use one root monorepo environment instead; describe the desired tool.

**How you'll verify this landed:** `gateway/README.md`'s regression commands
no longer reference `../ingestion-pipeline/merged-ingestion/.venv/bin/python`;
running `cd gateway && pytest` (or the equivalent for whichever option was
picked) succeeds using an interpreter that lives under `gateway/` itself (or
the root, if you picked the monorepo option) rather than under
`ingestion-pipeline/`.

### 2. Authentication model

The current Gateway bearer guard protects `/api/*` and API documentation, but
GLC routes have different security assumptions and channel webhooks use native
signature checks.

Concretely, today's guard is `main.py`'s `_requires_token` (`gateway/main.py`
lines 66–75): any path starting with `/api/`, plus `/openapi.json`, `/docs`,
and `/redoc`, must present `Authorization: Bearer <AI_OS_TOKEN>` (checked
literally at line 88) or get a 401; if `AI_OS_TOKEN` isn't set at all, those
paths 503 instead of silently opening up. `/health` and the shell's catch-all
route are deliberately left open, because the shell has to load before it can
ask you for a token. None of this changes in this plan — GLC and channel
routes don't exist under Gateway yet (that's Plans 04/05); this decision just
fixes the policy now so those later plans don't each invent their own.

Proposed default:

- Gateway bearer token for internal administration APIs — i.e., the same
  `AI_OS_TOKEN` check that exists today, applied to whatever Gateway's own
  admin/diagnostic routes become.
- Provider-native signature validation for inbound webhooks — e.g. a
  WhatsApp or Twilio webhook checks the HMAC signature that provider sends,
  not your bearer token, because the provider has no way to know your token.
- Explicit policy per compatibility route rather than a blanket `/v1/*` rule —
  each old GLC route gets its auth requirement decided and written down
  individually, rather than assuming every `/v1/*` path wants the same guard.
- No secrets in query strings or service-registry diagnostics — a token or
  webhook secret must never appear in a URL (it ends up in logs/browser
  history) or in the output of a `/health`-style diagnostics endpoint.

- [ ] Approve this split.
- [ ] Specify a different identity/authentication design below.

**How you'll verify this landed:** the existing `gateway/test_main.py`
parametrized tests (`test_protected_paths_reject_a_missing_token` and
siblings) still pass unchanged — this decision shouldn't touch today's
`/api/ingestion/*` behavior. Once Plan 04/05 add GLC and webhook routes,
look for an equivalent test showing a webhook path answers to a valid
provider signature with no bearer header, and rejects an invalid one.

### 3. Dependency container

Proposed default: construct typed domain services during lifespan and inject
them into route factories. Avoid adding new module-level singletons or loosely
typed `app.state` access.

There is no container today. All `create_app()` (`gateway/main.py` line 54)
does is build one `ReviewService` via the module-level `_service()` helper
(line 37) and stash it as `app.state.review_service` (line 64); the ingestion
router then reads it back out. That single untyped `app.state.<name>` slot is
the entire "dependency injection" story right now — fine for one service, not
for several domains.

- **Approve typed construction and route factories** means: at startup
  (inside the `lifespan` context manager, where `service.close()` already
  runs today at line 61), build each domain's real service object with a
  known type, then hand it explicitly to a function that builds that
  domain's `APIRouter` — instead of routes reaching into `app.state` and
  hoping the right attribute exists with the right type. Cost: a small
  amount of new plumbing code (a container/registry of typed services).
  Benefit: a route can't accidentally read the wrong or a missing service
  and only find out at request time; a type checker catches the mismatch
  instead.
- **Prefer another composition mechanism** — e.g. FastAPI's `Depends()`
  overrides for everything, or a third-party DI framework. Cost: more
  machinery/indirection than the proposed default. Possible benefit: easier
  per-test override of a single dependency without touching app
  construction at all.

- [ ] Approve typed construction and route factories.
- [ ] Prefer another composition mechanism; describe it below.

**How you'll verify this landed:** `grep -rn "app.state\." gateway/src` turns
up only the container's own construction code, not individual route
handlers reaching into it directly.

### 4. Service registry

Proposed default: `config/services.yaml` owns non-secret host/port definitions;
environment variables may override them for deployment.

Today there is no registry at all: `gateway/main.py`'s only port reference is
the literal `port=8000` passed to `uvicorn.run` at line 119, and GLC's port
8111 is likewise hard-coded wherever it's started (see `00-program-roadmap.md`
under "Current verified baseline"). Nothing today validates that two services
aren't accidentally configured onto the same port.

- **Approve YAML plus typed environment overrides** means: a checked-in
  `config/services.yaml` lists each domain's default host/port; a typed
  loader reads it, and specific environment variables can override individual
  values for a given deployment (e.g. a different port in a container).
  Benefit: one place to see every service's address, and duplicate-port
  bugs get caught by validation at startup rather than by a mysterious
  "connection refused" later.
- **Use environment-only configuration** means: no YAML file — every host/port
  comes from an environment variable, full stop. Simpler (one mechanism, not
  two), but there's no single file you can open to see the whole map of
  services, and nothing to validate against unless you write that validation
  against the environment directly.

- [ ] Approve YAML plus typed environment overrides.
- [ ] Use environment-only configuration.

**How you'll verify this landed:** the "duplicate-port and redaction tests"
mentioned under Work Package C exist and fail if you point two enabled
services at the same port in the config; a `/health`- or diagnostics-style
route shows resolved service addresses with no secret values in the output.

## Work packages

### A. Package the current application

- Add package metadata and a lockfile. *(This is decision #1 above, made
  real — the new `pyproject.toml`/`uv.lock` this plan's target layout shows
  under `gateway/`.)*
- Move app construction beneath `src/gateway/app/`. *(Today all of it — the
  token guard, the router mount, the shell static-file mount, `create_app()`
  itself — lives in the single 120-line `gateway/main.py`. This splits that
  one file into `app/main.py`, `app/middleware.py`, `app/lifespan.py`,
  `app/dependencies.py` per the target layout above; it does not change what
  any of that code does.)*
- Retain a small compatibility entry point if current commands require it.
  *(`gateway/README.md`'s run command is `uvicorn main:app ...` — if that
  exact invocation should keep working, a thin `main.py` re-exporting the
  real `app` from its new location is the compatibility entry point.)*
- Preserve shell static-file behavior and SPA fallback. *(The two blocks at
  `main.py` lines 98–108: mounting `/assets` from `shell/dist/assets`, and
  the catch-all route that serves a matching static file or falls back to
  `index.html` for any other path — this is what makes React-Router-style
  client-side routes work on a hard refresh.)*

**How you'll know Work Package A is done:** `gateway/README.md`'s run command
(`uvicorn main:app --host 127.0.0.1 --port 8000`, currently in the "Regression
commands" section) still starts the app and serves the shell at
`http://127.0.0.1:8000/ingestion` exactly as before, but the code it starts
now lives under `src/gateway/app/` instead of one flat `main.py`.

### B. Extract cross-cutting application services

- Extract bearer authentication middleware. *(The `@app.middleware("http")`
  function `bearer_auth` and its helper `_requires_token`, `main.py` lines
  66–90, move to `app/middleware.py` as-is — same 401/503 behavior, same
  `SCHEMA_AND_DOCS_PATHS` set, just no longer inline inside `create_app()`.)*
- Extract lifespan startup/shutdown. *(The `@asynccontextmanager` `lifespan`
  function, `main.py` lines 58–61 — today it only calls `service.close()` on
  shutdown — moves to `app/lifespan.py` and becomes the place where every
  domain's typed services get constructed, per decision #3.)*
- Define the typed dependency container. *(New code — this is where decision
  #3's "typed construction" actually gets implemented, replacing the single
  `app.state.review_service = service` assignment at line 64.)*
- Create domain router registration without importing domain internals in
  the application entry point. *(Today `main.py` imports
  `cockpit.server.create_router` directly at line 34 and calls
  `app.include_router(create_router(service), prefix="/api/ingestion", ...)`
  at line 96 — the entry point knows about ingestion's internals. After this
  work package, the entry point calls a generic "register this domain's
  router" function and doesn't import `cockpit.server` itself.)*

**How you'll know Work Package B is done:** `gateway/test_main.py`'s existing
tests pass unmodified against the refactored code — same 401/503/200
behavior for the same paths — which is the proof that this was a pure
extraction, not a behavior change.

### C. Add typed configuration and service registry

- Validate hosts, ports, duplicate enabled ports, and environment overrides.
  *(New code implementing decision #4 — e.g. loading `config/services.yaml`
  and refusing to start if two enabled services resolve to the same port.)*
- Derive internal URLs from resolved services. *(So that, once GLC moves in
  under Plan 04, in-process code can ask the registry for "the LLM service's
  address" instead of a second hard-coded port literal appearing next to the
  one that already exists for 8111.)*
- Add authenticated diagnostics with secrets redacted. *(A route — behind
  the same bearer guard as other `/api/*` routes — that shows resolved
  service addresses for debugging, with any secret values stripped out
  before they're returned.)*
- Define the rule for optional external workers. *(Decide, and write down,
  what happens if an optional worker — e.g. a future channel worker from
  Plan 05 — isn't running: does Gateway still start? This is the general
  rule Plan 05's Work Package C later relies on.)*

**How you'll know Work Package C is done:** a test exists that configures two
services onto the same port and asserts startup fails with a clear error
(the "duplicate-port test" the Exit Gate below asks for); a request to the
new diagnostics route, made with a valid bearer token, returns service
addresses but no token, password, or API key value anywhere in the response
body.

### D. Preserve ingestion composition temporarily

- Keep the current ingestion router mounted at `/api/ingestion`. *(No change
  to `test_main.py`'s `test_health_and_shell_are_available_but_ingestion_
  api_requires_bearer` or any other existing ingestion route test.)*
- Isolate sibling-path injection in one clearly temporary adapter. *(Today
  `main.py` lines 18–32 manually compute `INGESTION_ROOT` as a sibling
  folder — `ingestion-pipeline/merged-ingestion` — and insert it into
  `sys.path` so `from cockpit.server import ...` (line 34) works, because
  ingestion isn't an installed package gateway depends on normally. That
  `sys.path.insert` block is the "sibling-path injection" this item means —
  it gets moved into one clearly-labeled adapter module instead of sitting
  at the top of the main app file, so it's obvious and greppable, but it
  isn't removed yet — that's Plan 06's job.)*
- Add a test that will fail once accidental new sibling imports appear.
  *(A test that scans gateway's source for new `sys.path.insert`-style
  imports outside the one documented adapter, so nobody accidentally adds a
  second one while this plan's replacement is pending.)*
- Do not move ingestion source in this plan. *(`ingestion-pipeline/` itself
  is untouched — only how gateway reaches into it changes.)*

**How you'll know Work Package D is done:** `grep -rn "sys.path" gateway/src`
finds exactly one place doing this, clearly named as temporary; every
existing `/api/ingestion/*` test in `test_main.py` still passes unchanged.

### E. Verification

- Gateway unit and contract tests. *(Today's `gateway/test_main.py` and
  `gateway/test_contract_staleness.py`, run with `pytest` from `gateway/`,
  should all still pass — this is the "did I break anything that already
  worked" check.)*
- OpenAPI snapshot. *(`gateway/export_openapi.py` regenerates
  `gateway/openapi.json`; `test_contract_staleness.py` fails if the checked-in
  file doesn't match what the app actually serves. Run
  `python export_openapi.py` and `git diff gateway/openapi.json` — a diff
  here on `/api/ingestion/*` paths is a red flag; a diff only from brand-new
  routes is fine.)*
- Static shell build and UI journey. *(`cd shell && npm run build`, then
  load `http://127.0.0.1:8000/ingestion` in a browser and click through the
  same journey by hand — this is the one check that isn't automatable
  against the refactor and needs an actual look.)*
- Startup/shutdown and missing-configuration tests. *(Equivalent of today's
  `test_protected_paths_refuse_service_when_no_token_is_configured`, but for
  every new required piece of configuration this plan introduces — e.g.
  `config/services.yaml` missing or malformed should fail loudly at startup,
  not silently at first use.)*
- Duplicate-port and redaction tests. *(See Work Package C above — these are
  the concrete tests decision #4 needs to exist.)*

**How you'll know this plan is actually done:** every command in
`gateway/README.md`'s "Regression commands" section still exits 0, run from
wherever the new package structure says they should be run from, and the
manual shell walkthrough above shows the same behavior you see today.

## Explicitly out of scope

- Importing GLC runtime modules.
- Changing ingestion behavior.
- Changing port 8111.
- Redesigning the frontend.

## Exit gate

- Gateway runs from its own package and environment.
- Existing `/api/ingestion/*`, `/health`, shell, docs, and auth tests pass.
- Configuration, dependencies, and lifecycle have explicit typed boundaries.
- Service registry rejects invalid or duplicate ports.
- The only remaining sibling ingestion coupling is the documented temporary
  adapter.

## Aryaman's comments

Add desired package layout, auth rules, configuration preferences, and service
boundaries here.


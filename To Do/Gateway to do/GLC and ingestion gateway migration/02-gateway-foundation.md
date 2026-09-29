# Plan 02 — Gateway Foundation (Implementation Plan)

## Scope and dependencies

This plan builds the empty, packaged container: DI, lifecycle, config,
service registry. It imports no GLC runtime code (see "Explicitly out of
scope" below) — Plan 04 is what fills the container with GLC's actual LLM
domain code afterward, using the dependency container's typed construction
(§3) as the injection point for the `LLMService` protocol Plan 04 defines.
Plan 04 cannot start until this plan's container exists. The authentication
model decided here (§2) is the backend policy that `To Do/UNIFIED UI/ UNIFIED_UI_PLAN.md` consumes on the frontend side — that plan does not
redecide it here.

**Lift-and-shift boundary:** `glc_v5/` and `ingestion-pipeline/` are read-only
sources for this migration, not destinations. Every new or moved file this
program produces is authored under `gateway/` (this plan's container, or the
domain folders Plans 03–06 add beneath it). Nothing is built or edited in
place inside `glc_v5/`; that folder stays untouched until Plan 07 removes it.

## Goal

Turn the current thin `gateway/main.py` application into a stable package
that can own multiple domains without accumulating global state or
sibling-path imports. Preserve the existing shell and ingestion API
behavior.

## Target structure

```text
gateway/
├── pyproject.toml           # Gateway's own package metadata (decision #1)
├── uv.lock                  # Gateway's own lockfile — not ingestion's
├── config/
│   ├── gateway.yaml         # non-domain app config (host, log level, etc.)
│   └── services.yaml        # service registry: every domain's host/port (decision #4)
├── src/gateway/
│   ├── app/                 # the ASGI application itself — wiring only,
│   │   │                    # no domain logic lives here
│   │   ├── main.py          # create_app() and the ASGI entry point
│   │   ├── lifespan.py      # startup/shutdown; builds the typed container (decision #3)
│   │   ├── middleware.py    # cross-cutting HTTP concerns (bearer auth today)
│   │   └── dependencies.py  # typed Depends() accessors over the app-state container
│   └── platform/            # shared infrastructure every domain can depend on;
│       │                    # never a place for one domain's business logic
│       ├── configuration/   # typed config loading/validation for gateway.yaml
│       ├── networking/      # shared HTTP client setup, outbound call policy
│       ├── database/        # shared DB/connection-pool setup (not domain schemas)
│       ├── observability/   # logging/tracing/metrics wiring
│       └── service_registry/# loads + validates config/services.yaml (decision #4)
└── tests/                   # gateway-level tests (app wiring, not domain internals)
```

Each folder above owns exactly the responsibility noted next to it — a
domain (GLC, ingestion, channels) never puts its own logic under
`platform/`, and `app/` never grows domain-specific code. When Plans 03–06
add domain folders beneath `src/gateway/` (e.g. `gateway/llm/`, channel
packages), each new top-level folder they introduce should get the same
one-line scope statement in its own plan document before code lands in it —
this tree is the pattern to follow, not a one-off.

## Locked decisions



### 1. Package and environment ownership — gateway owns its own environment

Gateway gets its own `pyproject.toml`, lockfile, and `.venv`. During
migration it may reference imported domains as packages in the same
workspace, but it must stop borrowing ingestion's virtual environment as its
documented runtime. Everything Gateway depends on is resolved and installed
for Gateway alone — gateway is a large enough project to own its
dependencies exclusively; a shared root monorepo environment was considered
and rejected.

Today `gateway/` has no `pyproject.toml`, no lockfile, and no virtual
environment of its own — `gateway/README.md`'s own regression commands run
gateway's tests with `../ingestion-pipeline/merged-ingestion/.venv/bin/python`
(the ingestion project's interpreter), not a gateway-owned one. That
borrowing is what this decision removes.

Cost accepted: one more lockfile to keep current. Benefit: gateway can add
or upgrade a dependency without touching ingestion's environment, and
`cd gateway && pytest` works without reaching outside the folder for an
interpreter — which also decouples gateway's Python version from
ingestion's.

**Done when:** `gateway/README.md`'s regression commands no longer reference
`../ingestion-pipeline/merged-ingestion/.venv/bin/python`; running
`cd gateway && pytest` succeeds using an interpreter that lives under
`gateway/` itself.

### 2. Authentication model — bearer for admin, native signatures for webhooks

The current Gateway bearer guard protects `/api/*` and API documentation, but
GLC routes have different security assumptions and channel webhooks use
native signature checks.

Concretely, today's guard is `main.py`'s `_requires_token` (`gateway/main.py`
lines 66–75): any path starting with `/api/`, plus `/openapi.json`, `/docs`,
and `/redoc`, must present `Authorization: Bearer <AI_OS_TOKEN>` (checked
literally at line 88) or get a 401; if `AI_OS_TOKEN` isn't set at all, those
paths 503 instead of silently opening up.

*What this bearer check actually is:* it's Gateway's HTTP-layer front door —
proof that whatever is calling Gateway's own admin/API surface (a browser,
`curl`, the shell) is allowed to be there at all. It has nothing to do with
which LLM provider ends up serving a request — that's a separate, already-
decided concern: Plan 04 calls LLM providers exclusively through named
profiles (`LLMService.call(profile=..., ...)`, Plan 04 §"Proposed domain
shape"), never a hard-coded provider-specific call, and Plan 06 uses the
same named-profile convention for ingestion. Nothing in this decision
changes that.

`/health` and the shell's catch-all route are deliberately left open because
the shell's own HTML/JS has to load in the browser *before* that JS can show
you a place to type a token in — if loading the shell itself required a
bearer token, there would be no way to ever enter one. None of this changes
in this plan — GLC and channel routes don't exist under Gateway yet (that's
Plans 04/05); this decision just fixes the policy now so those later plans
don't each invent their own.

Policy:

- Gateway bearer token for internal administration APIs — i.e., the same
`AI_OS_TOKEN` check that exists today, applied to whatever Gateway's own
admin/diagnostic routes become.
- Provider-native signature validation for inbound webhooks — e.g. a
WhatsApp or Twilio webhook checks the HMAC signature that provider sends,
not your bearer token, because the provider has no way to know your
token. Each channel keeps and owns its own signature-verification logic
in its own package (per Plan 03's decision to keep vendor signature
schemes decentralized rather than hoisted into a shared module) — this
plan does not add a unified auth-enforcement layer on top of that. See
Plan 05's "Channel activation checklist" for the concrete per-channel
checklist this implies.
- Explicit policy per compatibility route rather than a blanket `/v1/*`
rule — each old GLC route gets its auth requirement decided and written
down individually, rather than assuming every `/v1/*` path wants the same
guard.
- No secrets in query strings or service-registry diagnostics — a token or
webhook secret must never appear in a URL (it ends up in logs/browser
history) or in the output of a `/health`-style diagnostics endpoint.

**Done when:** the existing `gateway/test_main.py` parametrized tests
(`test_protected_paths_reject_a_missing_token` and siblings) still pass
unchanged — this decision shouldn't touch today's `/api/ingestion/*`
behavior. Once Plan 04/05 add GLC and webhook routes, an equivalent test
shows a webhook path answers to a valid provider signature with no bearer
header, and rejects an invalid one.

### 3. Dependency container — lifespan-owned services and typed route access

**Standing rule for every new domain:** construct long-lived services in the
ASGI `lifespan` startup phase, fail startup if construction or validation
fails, and close those services during lifespan shutdown. Store the typed
container as the one permitted `app.state` value; route handlers obtain
individual services through typed `Depends()` accessors in
`app/dependencies.py`, never by reading untyped `app.state.<name>` values.
This keeps imports and application-factory calls free of configuration reads,
network clients, connection pools, and other resource construction, while
making the correct async ownership pattern already available to Plan 04's LLM
clients and Plan 05's workers.

Uvicorn does not begin serving requests when lifespan startup raises, so this
retains fail-fast behavior: malformed required configuration and unavailable
required resources still prevent the process from serving traffic.

**Temporary ingestion exception, removed by Plan 06:** the frozen external
`cockpit.server.create_router(review_service)` contract closes over a concrete
`ReviewService` when its router is registered; it has no `Depends()` seam.
The Plan 02 temporary ingestion adapter may therefore construct that one
`ReviewService` while assembling the router and hand it directly to
`create_router`. This is a compatibility boundary, not a second construction
pattern: it must not cause gateway configuration, the service registry, LLM
clients, database pools, or future domain services to be constructed eagerly.
Plan 06 replaces `cockpit.server` and deletes both this exception and its
adapter.

There is no container today. All `create_app()` (`gateway/main.py` line 54)
does is build one `ReviewService` via the module-level `_service()` helper
(line 37) and stash it as `app.state.review_service` (line 64); the
ingestion router then reads it back out. That single untyped
`app.state.<name>` slot is the entire "dependency injection" story right
now — fine for one service, not for several domains.

Cost accepted: a small amount of new plumbing code (a typed container plus
typed dependency accessors), instead of a third-party DI framework. Benefit:
routes cannot accidentally read the wrong or missing service from an untyped
state slot, and the type checker can catch a mismatch before requests arrive.

**Done when** (once code has moved under `gateway/src/`):
`grep -rn "app.state\." gateway/src` turns up only the container installation
and typed accessors in `app/dependencies.py`, not individual route handlers.
Tests prove that a required lifespan startup failure prevents serving, and
that the temporary ingestion adapter is the sole direct construction exception.

### 4. Service registry — YAML defaults, reserved port range, validated overrides

`config/services.yaml` owns non-secret host/port definitions. Reserve a
dedicated, unused-elsewhere block for every AI OS-owned service registered
here going forward — e.g. `81xx` — so a collision with some other tool on
the machine (Postgres, a dev server, Docker Desktop, etc.) is structurally
unlikely rather than a matter of luck. Every entry in `services.yaml` must
state its port explicitly and unambiguously; no service is left to "whatever
the library defaults to."

Override policy: the checked-in YAML values are the canonical defaults.
Environment variables may still override an individual value for a real
deployment need (e.g. a container that must remap a port) — but every
resolved port, whether from YAML or an override, goes through the same
duplicate-port validation at startup, so a mistaken override fails loudly
instead of silently colliding with another service. This is a narrower
allowance than "never overridden": the override path stays open for
deployment flexibility, but it can never bypass validation, and the
intent is that overrides stay rare and deliberate, not a routine knob.

Today there is no registry at all: `gateway/main.py`'s only port reference
is the literal `port=8000` passed to `uvicorn.run` at line 119, and GLC's
port 8111 is likewise hard-coded wherever it's started (see
`00-program-roadmap.md` under "Current verified baseline"). Nothing today
validates that two services aren't accidentally configured onto the same
port.

**Scope note — existing ports 8000 and 8111:** this plan's reserved-range
convention applies to *new* registry entries added from here forward (e.g. a
future channel worker). Gateway's own port 8000 and GLC's legacy port 8111
are both explicitly out of scope for this plan (see below) — whether they
also move into the reserved range is Plan 07's decision to make as part of
runtime cutover, and a note has been added there pointing back to this
convention.

**Done when:** the "duplicate-port and redaction tests" mentioned under
Step C exist and fail if you point two enabled services at the same port in
the config; a `/health`- or diagnostics-style route shows resolved service
addresses with no secret values in the output.

## Implementation steps



### A. Package the current application

- Add package metadata and a lockfile. *(Decision #1, made real — the new*
`pyproject.toml`*/*`uv.lock` *under* `gateway/`*.)*
- Move app construction beneath `src/gateway/app/`. *(Today all of it — the
token guard, the router mount, the shell static-file mount,*
`create_app()` *itself — lives in the single 120-line* `gateway/main.py`*.
Split into* `app/main.py`*,* `app/middleware.py`*,* `app/lifespan.py`*,*
`app/dependencies.py` *per the target structure above; do not change what
any of that code does.)*
- Retain a small compatibility entry point if current commands require it.
*(*`gateway/README.md`*'s run command is* `uvicorn main:app ...` *— if
that exact invocation should keep working, a thin* `main.py`
*re-exporting the real* `app` *from its new location is the compatibility
entry point.)*
- Preserve shell static-file behavior and SPA fallback. *(The two blocks at*
`main.py` *lines 98–108: mounting* `/assets` *from* `shell/dist/assets`*,
and the catch-all route that serves a matching static file or falls back
to* `index.html` *for any other path — this is what makes
React-Router-style client-side routes work on a hard refresh.)*

**Done when:** `gateway/README.md`'s run command (`uvicorn main:app --host 127.0.0.1 --port 8000`, currently in the "Regression commands" section)
still starts the app and serves the shell at
`http://127.0.0.1:8000/ingestion` exactly as before, but the code it starts
now lives under `src/gateway/app/` instead of one flat `main.py`.

### B. Extract cross-cutting application services

- Extract bearer authentication middleware. *(The* `@app.middleware("http")`
*function* `bearer_auth` *and its helper* `_requires_token`*,* `main.py`
*lines 66–90, move to* `app/middleware.py` *as-is — same 401/503
behavior, same* `SCHEMA_AND_DOCS_PATHS` *set, just no longer inline
inside* `create_app()`*.)*
- Extract lifespan startup/shutdown. *(The* `@asynccontextmanager`
`lifespan` *function,* `main.py` *lines 58–61 — today it only calls*
`service.close()` *on shutdown — moves to* `app/lifespan.py` *and becomes
the place where every non-exempt domain's typed services are constructed,
validated, installed as the typed app-state container, and later closed,
per decision #3.)*
- Define the typed dependency container and accessors. *(New code
implementing decision #3: `app.state` holds only the typed container, and
`app/dependencies.py` exposes typed FastAPI `Depends()` accessors instead
of allowing route handlers to read arbitrary state attributes.)*

- Create domain router registration without importing domain internals in
the application entry point. *(Today* `main.py` *imports*
`cockpit.server.create_router` *directly at line 34 and calls*
`app.include_router(create_router(service), prefix="/api/ingestion", ...)`
*at line 96 — the entry point knows about ingestion's internals. After
this step, the entry point calls a generic "register this domain's
router" function and doesn't import* `cockpit.server` *itself.)*

**Done when:** `gateway/test_main.py`'s existing tests pass unmodified
against the refactored code — same 401/503/200 behavior for the same
paths — which is the proof that this was a pure extraction, not a behavior
change.

### C. Add typed configuration and service registry

- Validate hosts, ports, duplicate enabled ports, and environment
overrides. *(Implements decision #4 — loading* `config/services.yaml`
*and refusing to start if two enabled services resolve to the same
port.)*
- Derive internal URLs from resolved services. *(So that, once GLC moves in
under Plan 04, in-process code can ask the registry for "the LLM
service's address" instead of a second hard-coded port literal appearing
next to the one that already exists for 8111.)*
- Add authenticated diagnostics with secrets redacted. *(A route — behind
the same bearer guard as other* `/api/` *routes — that shows resolved
service addresses for debugging, with any secret values stripped out
before they're returned.)*
- Define the rule for optional external workers. *(Decide, and write down,
what happens if an optional worker — e.g. a future channel worker from
Plan 05 — isn't running: does Gateway still start? This is the general
rule Plan 05's worker-lifecycle step later relies on.)*

**Done when:** a test exists that configures two services onto the same
port and asserts startup fails with a clear error (the "duplicate-port
test" the Exit Gate below asks for); a request to the new diagnostics
route, made with a valid bearer token, returns service addresses but no
token, password, or API key value anywhere in the response body.

### D. Preserve ingestion composition temporarily

- Keep the current ingestion router mounted at `/api/ingestion`. *(No
change to* `test_main.py`*'s*
`test_health_and_shell_are_available_but_ingestion_api_requires_bearer`
*or any other existing ingestion route test.)*
- Isolate sibling-path injection in one clearly temporary adapter. *(Today*
`main.py` *lines 18–32 manually compute* `INGESTION_ROOT` *as a sibling
folder —* `ingestion-pipeline/merged-ingestion` *— and insert it into*
`sys.path` *so* `from cockpit.server import ...` *(line 34) works,
because ingestion isn't an installed package gateway depends on
normally. Move that* `sys.path.insert` *block into one clearly-labeled
adapter module instead of leaving it at the top of the main app file, so
it's obvious and greppable — it isn't removed yet, that's Plan 06's
job.)*
- Add a test that will fail once accidental new sibling imports appear.
*(A test that scans gateway's source for new* `sys.path.insert`*-style
imports outside the one documented adapter, so nobody accidentally adds
a second one while this plan's replacement is pending.)*
- Do not move ingestion source in this plan. *(*`ingestion-pipeline/`
*itself is untouched — only how gateway reaches into it changes.)*
- Keep the legacy router's eager composition narrowly contained. *(Because
`cockpit.server.create_router(review_service)` captures its concrete service
at registration time, the temporary adapter is the only Plan 02 code allowed
to construct `ReviewService` outside lifespan. It passes that service directly
to the frozen router factory; it does not publish it as another app-state
attribute or become a precedent for any later domain. Plan 06 removes this
adapter when it replaces `cockpit.server`.)*

**Done when** (once code has moved under `gateway/src/`):
`grep -rn "sys.path" gateway/src` finds exactly one place doing this,
clearly named as temporary; every existing `/api/ingestion/*` test in
`test_main.py` still passes unchanged.

### E. Verification

- Gateway unit and contract tests. *(Today's* `gateway/test_main.py` *and*
`gateway/test_contract_staleness.py`*, run with* `pytest` *from*
`gateway/`*, should all still pass — this is the "did I break anything
that already worked" check.)*
- OpenAPI snapshot. *(*`gateway/export_openapi.py` *regenerates*
`gateway/openapi.json`*;* `test_contract_staleness.py` *fails if the
checked-in file doesn't match what the app actually serves. Run*
`python export_openapi.py` *and* `git diff gateway/openapi.json` *— a
diff here on* `/api/ingestion/` *paths is a red flag; a diff only from
brand-new routes is fine.)*
- Static shell build and UI journey. *(*`cd shell && npm run build`*, then
load* `http://127.0.0.1:8000/ingestion` *in a browser and click through
the same journey by hand — this is the one check that isn't automatable
against the refactor and needs an actual look.)*
- Startup/shutdown and missing-configuration tests. *(Equivalent of
today's* `test_protected_paths_refuse_service_when_no_token_is_configured`*,
but for every new required piece of configuration this plan introduces —
e.g.* `config/services.yaml` *missing or malformed should fail loudly at
startup, not silently at first use.)*
- Duplicate-port and redaction tests. *(See Step C above — these are the
concrete tests decision #4 needs to exist.)*

**Done when:** every command in `gateway/README.md`'s "Regression commands"
section still exits 0, run from wherever the new package structure says
they should be run from, and the manual shell walkthrough above shows the
same behavior you see today.

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

# Unified Surface Architecture

Status: NORMATIVE. Any new UI-capable component follows this document. Existing components migrate toward it incrementally; deviations require explicit justification recorded in the decisions log, not silent drift.

## The problem this replaces

Historically, each new project (Planner, UPI tracker, Page Scanner, Podcast pipeline, ingestion cockpit, etc.) shipped as its own isolated pair: its own server process, its own hand-built webpage, its own hand-maintained request/response shapes on both sides. This is the conventional frontend/backend split — appropriate when there are separate teams, a real trust boundary between client and server, or independent scaling needs. None of those conditions hold here. The system is solo-maintained, local-first, and both "sides" are written by the same hand in the same sitting.

The result of applying the split anyway: ~16 independently reinvented UI surfaces, 4+ services silently colliding on the same port, no consistent auth, and duplicated request/response types on both ends of every boundary — with zero benefit gained in exchange for the duplication tax.

## Core principle

**Separate things only where a REAL boundary exists. Everywhere else, one process, one shell, one contract.**

A real boundary is a genuine change in trust or execution domain — code running in a browser sandbox, a stdio MCP child process, an external service you don't control. It is NOT "this is conceptually a different feature." Different features are ROUTES, not different servers.

## Where real boundaries actually exist in this system

Only these justify a network/process hop with its own contract:

1. **Browser extension ↔ local gateway.** The extension runs in a sandboxed browser process outside this system's control. This is the one legitimate client/server split.
2. **MCP tool boundary.** Any MCP server called by an agent with dynamic input and structured output — per the existing MCP-wrapping criterion. Stdio + process-spawn possession is the trust model; this is sufficient and is NOT to be over-engineered with additional auth layers.
3. **External services.** Anthropic/OpenAI APIs, Neo4j, Ollama, third-party APIs. Real network calls to systems outside this codebase.

Everything else — Planner, ingestion pipeline, finance agent, decision tracker, research MCP consumer UI, study system dashboards — is INTERNAL. Internal means: same trust domain, same machine, same maintainer. Internal components do not get their own server process or their own hand-rolled webpage.

## The shape: one gateway, one shell, sections attached to both

```
┌─────────────────────────────────────────┐
│  [Ingestion] [Finance] [Planner] [Study] │  ← nav, one shell
├─────────────────────────────────────────┤
│                                          │
│      active section renders here        │
│                                          │
└─────────────────────────────────────────┘
        one URL, one process, no reload between sections
```

### Backend: one FastAPI process, routers per section

- ONE FastAPI app is the gateway. It is the only process that binds a port for internal HTTP.
- Each domain (ingestion, finance, planner, study, decision tracker, etc.) is a `router` mounted under its own prefix: `/api/ingestion/...`, `/api/finance/...`, `/api/planner/...`.
- A section's internal logic (pipeline coordinators, DB access, business logic) stays exactly as encapsulated and separate as it is today. Only the OUTER SERVING LAYER consolidates. Nothing outside a section's own router imports or calls into that section's internals directly — the router is the only door.
- The existing LLM gateway (`llm_gateway/main.py`) remains its own dedicated service for LLM chat/embedding/provider routing. It is infrastructure other things call, not a UI-serving gateway, and stays separate for that reason — this is itself an example of the "real boundary" rule: it's a distinct capability consumed by many callers, including future non-Python ones.
- Bind to `127.0.0.1`, not `0.0.0.0`, unless a specific component genuinely needs LAN access.
- Auth is ONE bearer-token middleware on the gateway, not per-service. Every internal route requires it except an explicit `/health` check. This replaces the current state where nearly everything is unauthenticated.

### Frontend: one shell, sections are routes inside it

- ONE frontend application (React, following the stack already used for Accountability Agent / Flashcards) is the shell.
- The shell owns: navigation, layout, auth token handling, shared components (tables, forms, cards).
- Each section is a route/component inside the shell (`/ingestion`, `/finance`, `/planner`), not a separate build, not a separate `index.html`, not a separate dev server.
- A section's page fetches from its own API prefix (`/api/ingestion/...`) on load. The shell does not need to know what a section's data looks like — it just provides the frame.
- Hand-rolled vanilla HTML/JS dashboards (Planner SPA, ingestion review screen, Page Scanner cockpit, UPI dashboard, Model Forge, ReAct UI) are migration targets: each becomes one route in the shell, not a rewrite of logic — only the presentation layer moves.
- Static build output is served by the same FastAPI gateway process. One process answers both API requests and page requests.

### Contracts: shared types, not duplicated ones

- Define request/response shapes ONCE as Pydantic models on the backend. Do not hand-write matching JS object literals on the frontend from memory — generate or share the schema (OpenAPI-generated TS types, or a single source of truth file) so drift is structurally impossible, not just disciplined against.
- This applies to every internal router. It does NOT apply to the MCP boundary (schema-from-signature via FastMCP is already correct there) or to genuine external API calls (their contract is owned by the external service).

## Chrome extension specifics

- The extension is the one place a real trust boundary exists — treat it accordingly, but keep it thin.
- The extension talks to the ONE gateway, authenticated, not to a bespoke per-extension bridge server.
- Do not give the extension's bridge wildcard CORS or no-auth — this is the boundary that most needs the lock, and historically has been the least protected one.
- The extension's own UI (sidepanel, popup) can either stay as lightweight native extension UI for capture-specific interactions, OR embed a webview pointed at a route of the shell for anything more complex. Do not reimplement shell components inside the extension.

## What NOT to do

- Do not give a new project its own `uvicorn.run()` on its own port "for now." There is no "for now" — it goes in as a router from the start.
- Do not hand-write a new `static/index.html` for a new feature. It goes in as a route in the shell from the start.
- Do not add auth, schema validation, or network-boundary ceremony to the MCP tool layer — that boundary is already correctly minimal.
- Do not treat "this is a different domain conceptually" as justification for a different process. Conceptual separation is a router/route boundary, not a network boundary.
- Do not let a component bind `0.0.0.0` by default.

## Migration approach

Do not attempt a single rewrite. Migrate one section at a time into the gateway + shell pattern, smallest first, to validate the pattern before repeating it. Retire the standalone version of a section only after its route in the shell is confirmed working — do not run both indefinitely. Byte-identical or near-identical legacy copies (found via hash comparison across worktrees) are deleted outright, not migrated; they are clutter, not decisions.

## Why this doesn't contradict "bronze as source of truth" or trust-layer separation

This document governs the SERVING layer (how UI and API get delivered), not the data layer. Bronze immutability, trust-layer separation between source material/interpretation/machine output, and the MCP tool boundary are unaffected — those are real boundaries in the data and provenance model and stay exactly as strict as they are today. Consolidating servers and shells is purely about not re-deriving the same client/server split N times when no boundary justifies it N times.
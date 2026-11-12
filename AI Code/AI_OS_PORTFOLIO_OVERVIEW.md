# AI OS Portfolio Overview

## Purpose of this document

This is a directional map of the workspace as it exists on 4 September 2026. It is written for a new collaborator or model: it explains what each folder is for, which pieces are active foundations versus experiments or historical copies, how they fit into one product, and the most sensible route from the current portfolio to a coherent system.

It intentionally does not explain source code or prescribe implementation detail. Folder status is inferred from the documentation and artifacts in the workspace; “working” means that the project documents describe a runnable, tested path, not that a live environment check was run while writing this overview.

## Executive summary

This is not a collection of unrelated agents. It is an emerging **local-first personal AI operating system** for turning personal and professional information into durable knowledge, better judgement, and safe action.

The system has six recurring capabilities:

| Capability | What it means here | Strongest current foundations |
|---|---|---|
| Capture | Bring in articles, PDFs, books, audio, messages, payments, and web material | Ingestion pipeline, Marginal, raw-data capture tools, podcast systems, UPI agent |
| Knowledge | Preserve sources, provenance, embeddings, concepts, claims, and relationships | Database, merged ingestion, Neo4j/Chroma, study-system read contracts |
| Reasoning | Research, analyse, challenge, forecast, and make causal models | Research MCP, Steelman Generator, Mirofish, Model Forge, Advisor |
| Learning | Turn knowledge into durable recall and practice | Learning System, study automation, Flashcards |
| Action | Plan, track decisions, manage reminders, and present useful local interfaces | Planner, Decision Tracker, UPI Agent, AI OS shell |
| Infrastructure | Provide model access, tool access, safe UI delivery, and shared contracts | LLM Gateway, MCP Server, AI OS gateway/shell, Constitution |

The common design philosophy is unusually consistent: local-first where possible, provenance over unsupported fluent output, a human gate before consequential writes, structured artifacts rather than disposable chat, and feedback loops that turn predictions and outcomes into calibration.

The central issue is not lack of ideas or components. It is that these capabilities were built as independent rooms, often with separate local databases, model clients, dashboards, and UI servers. The work now should be **integration by promotion, not a rewrite or monorepo merge**: retain the strongest existing implementation of each horizontal capability, publish a small stable interface around it, and migrate vertical applications incrementally.

## The intended product in one sentence

An AI-native personal operating system that captures what enters your life, preserves what supports it, helps you reason under uncertainty, turns useful knowledge into memory and action, and learns from the results.

## The intended product in one flow

**Sources and life signals** → **immutable, reviewable capture** → **shared knowledge and provenance layer** → **specialist reasoning and learning engines** → **one secure local interface and MCP surface** → **decisions, reminders, practice, and outcomes** → **calibration back into the knowledge layer**.

The system should make it possible to trace an action or belief backward to sources and forward to observed results. That is the differentiation. It should not become a single generic chat interface that merely has many buttons.

## Workspace map at a glance

### A. Core platform and integration spine

| Folder | Role | Current status and intended place |
|---|---|---|
| `Constitution/` | The architectural constitution for the entire workspace. | The most important directional material. It defines the target shared substrate and the one-gateway/one-shell UI rule. Treat it as the decision record for integration, not as an executable project. |
| `AI OS/` | The first implementation of the unified serving layer. `gateway/` is the single FastAPI process; `shell/` is the React shell. | Active integration home. Ingestion is the first route; future internal applications should enter as routes and routers rather than new standalone servers. |
| `llm_gateway/` | Shared LLM and embedding infrastructure, currently V7. | Active horizontal service. It centralises provider routing, local/hosted model selection, embeddings, rate policy, and a constrained local Phi-4 segmentation route. It should be the common inference door, augmented with unified cost/budget controls. |
| `mcp_server/` | The broad capability surface exposed to agents through MCP. | Active tool layer with documented domain groups: documents, finance, knowledge, graph, media, news, raw data, research, utilities, and vector search. Valuable but presently carries stale sibling-path assumptions and some compatibility stubs. |
| `Database/` | Shared data root, deliberately data-only. | Active source-of-truth location for immutable bronze captures, ingestion state, vector/graph derivatives, and study-system data. It is the preferred physical home for shared artifacts, not a project in which application logic belongs. |
| `ingestion-pipeline/` | The mature route from source material to reviewed, structured knowledge. | The strongest current integration project. `merged-ingestion/` is the future production path; `integration/` contains its governing plan/history; older implementations are intentionally retained only until the merged route is proven. |
| `Future gateway porting /` | Notes for moving earlier gateway work to the current architecture. | Planning/historical material. Use it to understand compatibility and migration decisions, not as a second gateway. |

### B. Decision, reasoning, and knowledge products

| Folder | Role | Current status and intended place |
|---|---|---|
| `AI Agent/` | Typed five-stage cognitive agent with vector memory, artifacts, MCP dispatch, and a small local planning UI. | A reference agent spine and early integrator of the LLM gateway plus MCP server. It depends on both siblings at runtime. Its memory-index MCP tools have a known stale import-path regression, so it should be repaired before being made the flagship orchestration layer. |
| `React Loop/` | A deliberately hand-built ReAct loop using textual JSON decisions rather than provider-native tool calling. | Educational/reference agent spine with strong guardrails, trajectory recording, MCP interaction, and a demo UI. Useful as an agent-control experiment; do not duplicate its local tool server when the main MCP surface is ready. |
| `Advisor/` | Provider-neutral executor-to-advisor escalation loop. | A small, reusable deliberation primitive: a cheaper executor may privately consult a stronger model, with optional per-call usage records. Best viewed as a policy that can be incorporated into the LLM gateway or selected agent workflows, not as a separate user product. |
| `Decision Tracker/` | Local-first, append-only journal for decisions, forecasts, outcomes, calibration, alerts, recall, graph analysis, and a dashboard. | One of the most product-ready vertical applications. It is the natural system of record for hypotheses and outcomes emitted by research, Model Forge, Steelman, and PRAXIS. It should become the feedback loop for the wider system. |
| `Steelman Generator/` | Evidence-aware reconstruction of the strongest case for and against a claim, including forensic-accounting reviews. | Mature specialist reasoning engine with typed argument graphs, evidence grades, adversarial hardening, predictions, calibration hooks, SQLite persistence, optional Neo4j export, and local UI. It is a high-value reasoning service rather than a general chat feature. |
| `Mirofish/` | MIRFISH, an event-transmission mapping system and hypothesis generator. | A specialist second-order consequences engine. Its curated India macro graph, validation, aliases, and neighbourhood queries are in place; event propagation, proposed-edge review, backtesting, and reports are later milestones. Its explicit boundary is important: it proposes hypotheses and transmission paths; it is never a trading signal. It pairs naturally with Model Forge and Decision Tracker. |
| `Mental Models Creator/` | Model Forge: a library of typed causal mental models that make falsifiable predictions. | Architecturally central and implemented as a local web/CLI tool with stable JSON/Markdown artifacts and local fallbacks. It identifies the missing shared entity namespace: models, entities, causal edges, boundary conditions, predictions, anomalies, and provenance. Use its existing narrow workflows before graph-scale expansion. |
| `Accountability Agent/` | PRAXIS: situational mental-model retrieval and practice. | A working local React/Express product around principle cards, passages, contradiction/graph reasoning, and four action-oriented modes. Its key contribution is the closed loop from cue-matched recommendation to prediction to Decision Tracker outcome. It remains a standalone surface pending a later AI OS migration. |
| `Consequence Radar/` | Named future concept. | Empty placeholder. Retain the name only if it becomes a distinct product from Mirofish; otherwise fold it into Mirofish’s event/cascade capability to avoid duplicate concepts. |

### C. Research, learning, and media products

| Folder | Role | Current status and intended place |
|---|---|---|
| `Learning System/` | Headless study engine: concepts and source material become flashcards, FSRS review state, Feynman/challenger practice, and progress. | Active domain engine. It is intentionally separated from its MCP adapter in `mcp_server` and automation host. It should consume the canonical knowledge layer rather than own an incompatible one. |
| `Automation Personal/study-automation/` | Scheduled/headless host for Learning System card generation. | Active companion to the Learning System. Keep automation outside the core engine, as designed. |
| `frontend/Flashcards/` | Mobile-first flashcard interface, initially designed for German and extensible to other domains. | A product/UI concept with an excellent interaction specification. It should become the Study route in the unified shell when it has a working minimally scoped study loop. |
| `Personal/Research_MCP/` | Adaptive research and claim-verification engine, exposed through FastMCP and a Python client. | The strongest research implementation and a key reference for typed contracts, prompts-as-files, metering, source provenance, and citation gates. It is intended to stay independently usable while serving other applications. |
| `Personal/research/` | Deliberately reduced research boundary. | A placeholder for future extraction, not a second research engine. Keep it light until there is a clear package/service boundary to move here. |
| `Personal/Podcast pipeline/` | The podcast evolution path: older pipeline, a more capable MCP-oriented version, and related artifacts. | A vertical media capability. The documented design says Research MCP is its intended V3 research/aggregator seam. Consolidate around that seam instead of continuing separate research logic. |
| `Automation Personal/podcast-pipeline/` | Direct CLI/automation caller for the podcast pipeline. | Useful fallback and scheduling adapter. It deliberately contains little domain logic and should stay thin. |
| `Work /Podcast-Agent`, `Work /Podcast_Agent_Ver_1`, and `Work /Podcast_Agent_Ver_1 finished` | Earlier podcast summarisation generations. | Historical prototypes: RSS/audio → transcription → Gemini summary → Markdown, with Streamlit/CLI variants. They explain the lineage but should not be extended; retain only as reference until their useful assets have been folded into the current pipeline. |
| `Work /Audio to Text/` | Audio transcription experiments and sample outputs. | Input/output experiment, useful as provenance or test material but not a live subsystem. |
| `Work /Newsletter/` | A real-estate/market-news briefing prototype. | A targeted news-ranking and presentation experiment. Its future home is likely the MCP `news/market_brief` tool group or a Finance route, rather than an independent interface. |

### D. Personal action and life-management products

| Folder | Role | Current status and intended place |
|---|---|---|
| `Personal/Planner and Reminders/` | Local macOS planning assistant that reads/writes Apple Calendar and Reminders through a confirmation-gated agent loop and saves session memory as Markdown. | One of the most central action products. Its explicit read-versus-confirmed-write safety model should be promoted as a reusable pattern. The server/UI should migrate into the unified AI OS gateway and shell without moving its domain logic. |
| `Personal/upi-agent/` | Local UPI payment ledger: reads forwarded SMS, enriches with calendar context, categorises spend, detects anomalies, tracks goals/recurrence, tells weekly stories, and supports SBI statement workflows. | Strong self-contained personal-finance vertical. Its local-only and read-only access posture is valuable. Calendar access should eventually come from the shared macOS capability rather than a duplicate accessor. |
| `Personal/Notion to Obsidian/` | One-off Notion-to-markdown vault migration. | Historical but strategically important: it established the vault as a shared long-lived knowledge root. Keep it as a migration utility, not a continuously running subsystem. |
| `Personal/Chrome Plugin/` | Earlier browser-side critical-thinking/analysis extension, referred to in the architecture notes as Sharpen. | A browser extension is a real trust boundary and should remain thin. Its future role is capture, highlighting, and authenticated access to the local gateway; it should never own an API key or a second local server. |
| `Personal/prompt-plan-optimizer/` | Next.js prompt/plan editor with decomposition, versioning, diff/conflict concepts, and model-assisted revision. | Promising developer-experience vertical, but its visible README understates the planned product. It should eventually access shared inference and artifacts through the gateway, while retaining its focused editing workflow. |
| `Personal/Painting_shapes/` | Small MCP/agent experiment. | Explicitly excluded from the original AI OS integration plan. Keep as a sandbox or archive; do not design the platform around it. |
| `Personal/Lecture 7/` | Earlier copy of the EAGV3 agent work and an LLM gateway version. | Historical duplicate/reference of the AI Agent and gateway lineage. Do not treat as an active integration target. |

### E. Capture and user-interface products

| Folder | Role | Current status and intended place |
|---|---|---|
| `frontend/Highlighter project/` | Marginal, a local-first Chromium extension that freezes articles, stores robust multi-anchor highlights, supports search/export/backup, and safely overlays highlights back onto source pages. | A particularly strong capture component. It should feed reviewed/frozen content and highlights into ingestion, rather than being replaced. Its use of immutable captures and ambiguity refusal matches the system’s provenance principles. |
| `frontend/Ingestion Review Screen/` | The original one-screen human review cockpit for the ingestion pipeline. | Explicitly superseded as a production surface. It remains the visual/interaction reference while the real production route moves into the React AI OS shell at `/ingestion`. Do not add new production behaviour here. |
| `frontend/overview/` | Earlier overview material for frontend work. | Reference material, not a standalone product. |
| `frontend/static/` | Shared/legacy static frontend artifacts. | Supporting material; assess case by case during shell migration. |
| `AI OS/shell/` | The React host for all internal sections. | This is the canonical future home for the user-facing products above. It owns navigation, auth-token handling, shared components, and generated API types; it does not own each product’s business logic. |
| `gesture control/` | Camera-based macOS gesture-control POC with an explicit wake/sleep safety gate. | An intentionally bounded local interaction experiment: no screen context, no agent, no smart path. It could become an optional input layer later, but must not enter core integration until reliability and permissions have been proven with real hands. |

### F. Work-domain applications and historical prototypes

| Folder | Role | Current status and intended place |
|---|---|---|
| `Work /AI Analyst/` | A work-oriented earlier bundle of agent, MCP server, and LLM gateway. | The direct ancestor of root-level `AI Agent/`, `mcp_server/`, and `llm_gateway/`. Use for lineage/reference; centralise fixes and new development in the root-level descendants. |
| `Work /AI Analyst POC/` | Earlier proof of concept for the AI Analyst bundle. | Historical precursor, superseded by the more evolved work copy and root-level projects. |
| `Work /Financial Shenanigan/` | Multi-prompt annual-report analysis for accounting manipulation signals, with reports, prompts, documents, and notebooks. | An early finance specialist. Its reusable concepts have been absorbed by Steelman’s forensic pack and MCP finance tools; preserve its domain prompts and examples, but do not make its one-off script the production foundation. |
| `Work /Claude for financial services/` | Downloaded packaged examples for finance-oriented Claude workflows. | Reference library, not an internally developed service. Mine for workflow ideas only after checking licence/usage restrictions. |
| `Work /Prefab UI/` | UI and MCP exploration, including a design plan and local artifacts. | Experimental UI work. Its useful design principles can inform the unified shell; avoid creating a competing serving surface. |
| `Work /Book-to-Skill/` | Book-to-skill exploration with a source book. | Incubation material. It connects naturally to Learning System, PRAXIS, and Model Forge, but has no separate active product boundary yet. |
| `Work /Lecture 7 copy/` | Earlier LLM Gateway V7 copy. | Historical duplicate of gateway lineage. |

### G. Organizational and archival folders

| Folder | Role | Current status and intended place |
|---|---|---|
| `_archive/` | Root-level historical material. | Preserve as an archive. Do not wire it into current runtime paths. |
| `Database/_trash/` and `Database/Raw Data/_archive/` | Staged deletions and pre-pipeline clutter. | Explicitly non-production. Review before eventual removal; nothing active should read from them. |
| `Automation Personal/Page Scanner/` and `Automation Personal/Page Scanner copy/` | Earlier page-scanner implementations/copies. | Legacy equivalents of source capture/review work. Do not extend both. Retain as comparison/reference while `merged-ingestion` proves its production path. |
| `ingestion-pipeline/Page Scanner copy/`, `ingestion-pipeline/archive/`, and `ingestion-pipeline/b4-bounded-intake/` | Pre-merge ingestion implementations and bounded intake experiments. | Historical and investigative material. The active implementation is `merged-ingestion/`; use these only where the governing integration documentation points to them. |
| `Consequence Radar/` and `untitled folder 2/` | Empty root-level folders. | No active role evidenced by the workspace. Rename with intent or archive/delete after confirming they are not externally referenced. |
| `.claude/`, `.venv/`, nested `.venv/`, `.git/`, caches, `dist/`, and `.next/` folders | Tooling, environments, repository metadata, and generated output. | Not product modules. Exclude from architecture decisions and Claude context except where a project’s environment setup is relevant. |

## What is already coherent

Several decisions have already been made on paper and should be treated as settled unless new evidence appears.

1. **Keep applications separate; share packages/services instead of forcing a monorepo merger.** The target is horizontal capabilities consumed by vertical applications.
2. **Markdown/vault content and immutable bronze captures are durable memory, not incidental files.** They need one logical namespace, stable identifiers, provenance, and explicit access methods.
3. **One LLM gateway, not many raw provider clients.** It should handle providers, embeddings, model policy, pricing, budgets, and auditability.
4. **One internal UI gateway and one React shell.** Different features become gateway routers and shell routes, not their own local servers and hand-maintained frontends.
5. **MCP is the agent/tool boundary.** It is for structured tools and externalised capabilities, not a reason to add another REST service for every domain.
6. **Human review is a product feature.** Ingestion, calendar/reminder writes, and high-stakes judgement should surface evidence and legal actions rather than hide uncertainty behind automation.
7. **Predictions and outcomes matter.** Reasoning engines should emit falsifiable claims; Decision Tracker should resolve them; calibration should change confidence over time.

## The timeline so far

### Phase 1 — Standalone experiments and domain discovery

The earliest work was a broad set of direct experiments: podcast transcription/summarisation, newsletters, finance analysis, a manual ReAct loop, early agent/MCP/gateway bundles, a calendar planner, a UPI ledger, and browser/highlighter work. These projects discovered the required domains and safety constraints through use rather than through a top-down platform plan.

The Work folder is the clearest record of this phase. It contains prototype generations and duplicated bundles. Its value is historical: it shows which workflows were compelling enough to survive into more structured root-level projects.

### Phase 2 — Specialist engines become structured products

The system then developed more rigorous vertical engines: Research MCP for cited research, Learning System for spaced repetition, Steelman for evidence-aware adversarial reasoning, Mirofish for second-order hypotheses, Decision Tracker for calibration, and Model Forge/PRAXIS for causal models and situational judgement.

This phase introduced the key product insight: a high-quality answer is not enough. The system needs structured claims, provenance, uncertainty, predictions, and feedback.

### Phase 3 — Recognition of the shared substrate

The June 2026 architecture work in `Constitution/` made the central diagnosis explicit: multiple projects had independently rebuilt pieces of the same substrate—vault memory, local stores, LLM access, macOS context, and agent tools.

The intended remedy was to promote the best available implementation of each capability into shared infrastructure while preserving separate vertical applications.

### Phase 4 — Foundation consolidation

During July and August 2026, the work moved from conceptual architecture toward a real spine:

- LLM Gateway V7 became the shared model/embedding infrastructure.
- MCP Server was restructured around one folder per tool and documented domain groups.
- The database was separated into a data-only shared root with bronze/source, state, vector, graph, and study locations.
- The ingestion work was merged into a governed `merged-ingestion` implementation, with highlight-level provenance and review foundations.
- The AI OS gateway and React shell were established as the canonical internal serving layer, with ingestion chosen as the first migration.

### Phase 5 — Present moment: prove one vertical slice, then repeat

The portfolio is now past the “what are we building?” stage. The immediate challenge is operational consolidation: prove an end-to-end vertical slice that uses the shared data root, LLM gateway, review gates, AI OS gateway, and React shell; then migrate the next applications without reintroducing duplicate paths.

## Target architecture and responsibilities

The target should be understood as layers with explicit jobs, not as a single giant application.

| Layer | Owns | Should not own |
|---|---|---|
| Source and capture | Immutable original material, frozen articles/highlights, raw audio, documents, imports, source metadata | Hidden interpretation or irreversible downstream decisions |
| Ingestion and knowledge | Envelopes, review state, canonical notes, source lineage, entities, claims, graph/vector derivatives | A separate generic end-user UI for every stage |
| Shared services | LLM access, embeddings, budgets, contracts, macOS actions, policy, common identity | Domain-specific product workflows |
| Specialist engines | Research, study, causal modelling, argument analysis, finance analysis, decision evaluation | Their own incompatible database root, gateway, or UI host |
| Tool boundary | MCP tools for agents, with structured inputs/outputs and documented capabilities | Browser-facing application state or a duplicate UI API |
| Product surface | One authenticated local gateway and React shell, with routes such as Ingestion, Research, Planner, Study, Finance, Decisions | Business logic that bypasses domain routers |
| Feedback | Decisions, predictions, outcomes, calibration, user corrections | Silently changing source facts or obscuring history |

## Proposed wiring order

This sequence is intentionally conservative. Each stage produces a usable capability and a migration pattern before the next begins.

### 1. Establish the non-negotiable platform contract

Declare `Database/` as the only shared data root, `llm_gateway/` as the model/embedding door, `AI OS/gateway` plus `AI OS/shell` as the internal UI host, and `mcp_server/` as the principal agent tool surface. Record exceptions explicitly. This is mostly an ownership and configuration exercise, not a rewrite.

Success looks like: no new internal project chooses its own arbitrary database path, starts another unauthenticated local UI server, or calls providers directly without a documented reason.

### 2. Finish and harden the ingestion vertical slice

Take the already advanced merged-ingestion path all the way through the production AI OS route: source intake → evidence/review → bronze and structured records → graph/vector derivatives → visible run report. Keep Marginal and other capture products as inputs to this path.

Success looks like: one real document or article can be captured, reviewed, stored with lineage, found again, and inspected through `/ingestion`, with errors and human decisions visible.

### 3. Stabilise shared identity, provenance, and access contracts

Introduce a small common vocabulary for Source, Note, Entity, Claim, Concept, Decision, Prediction, and Artifact. Give each stable identifiers and clear lineage. Do not start with a grand graph redesign; start with the fields the active ingestion, research, study, and decision workflows already need.

Success looks like: a claim from Research MCP, a concept in Learning System, and a prediction in Decision Tracker can all refer to the same source/entity without brittle path matching.

### 4. Connect research to knowledge and learning

Make Research MCP the canonical research engine for podcast and other research-consuming workflows. Route verified research outputs and sources into the shared knowledge layer. Let Learning System draw from approved concepts/chunks rather than inventing a competing corpus.

Success looks like: a podcast or research query yields cited outputs that can be reviewed, saved, turned into study material, and traced back to sources.

### 5. Add the closed judgement loop

Connect Model Forge, Steelman, Mirofish, and PRAXIS to Decision Tracker through a shared prediction/outcome contract. Start with just one or two workflow paths—for example, a Steelman conclusion becoming a forecast record—not every engine at once.

Success looks like: the system can say what it expected, later record what happened, and expose how confidence/calibration changed.

### 6. Migrate high-value action surfaces one at a time

After the platform pattern is proven, migrate Planner, UPI, Study/Flashcards, Decision Tracker, and Finance as gateway routers plus shell routes. Preserve their domain logic and safety controls; replace only duplicate serving layers and hand-written frontend contracts.

Success looks like: one local login/token, one navigation shell, one consistent error/state experience, while each product remains independently testable and conceptually separate.

### 7. Retire duplicates deliberately

Only after a replacement works, designate the old path as reference or archive. The important targets are repeated gateway copies, old AI Analyst bundles, legacy page scanners, standalone cockpit surfaces, and overlapping podcast generations. Do not delete raw inputs, documented decisions, or examples that still support evaluation.

## Recommended next 90 days

### First 30 days: make the spine real

- Complete the production `/ingestion` route in the AI OS gateway and shell, using the merged-ingestion coordinator rather than the legacy static screen.
- Repair known sibling-path drift between AI Agent and MCP Server so the documented memory/index tools have one valid integration path.
- Write and enforce a minimal shared configuration convention: workspace root, database root, vault root, LLM gateway URL, and AI OS token.
- Decide whether the existing LLM gateway itself absorbs universal metering/budget enforcement or whether a thin shared policy module sits immediately above it. Do not leave multiple products with raw model calls.
- Create a concise registry marking each major folder as active, migration target, reference, or archive. This overview can be its initial source.

### Days 31–60: make knowledge reusable

- Define the first stable Source/Entity/Claim/Concept/Prediction contracts from actual ingestion and Research MCP outputs.
- Wire Research MCP outputs to the canonical data root with source provenance, then make the podcast pipeline use it as the intended aggregator rather than rebuilding research logic.
- Select a single narrow Learning System scenario using approved ingested/researched material and expose it through a Study route or a minimal shell bridge.
- Keep Model Forge and PRAXIS focused on their existing narrow user loops and prediction handoff; defer graph-scale automation until those loops prove their value.

### Days 61–90: close a feedback loop and migrate one action product

- Send one specialist-engine prediction into Decision Tracker and resolve at least several real outcomes; use that experience to refine contracts and calibration rules.
- Migrate either Planner or Decision Tracker into the AI OS gateway/shell, choosing the one whose existing domain logic and tests are easiest to preserve.
- Put the browser extension boundary on the gateway: authenticated, thin, and free of provider credentials.
- Decide which legacy folders can be explicitly archived once the new route demonstrably replaces them.

## Product priorities and non-priorities

### Build next

1. Ingestion as the trusted entry point to the shared knowledge base.
2. Shared identity/provenance contracts, because every later integration depends on them.
3. Research → knowledge → learning, because it demonstrates compounding value from one source of truth.
4. Prediction → decision → outcome, because it makes the system better over time rather than merely more convenient.
5. Incremental UI consolidation, using the same migration pattern repeatedly.

### Defer deliberately

- A universal autonomous agent that tries to orchestrate every tool.
- New standalone dashboards or localhost servers.
- Neo4j-first redesigns before the shared contracts and data paths prove the need.
- Broad multi-agent schemes for Model Forge, PRAXIS, or podcast work before their small real-user loops are validated.
- More duplicate provider clients, vector stores, calendar accessors, and generic research functions.
- Gesture control beyond its constrained POC until reliability is demonstrated in daily use.

## Main risks to manage

| Risk | Why it matters | Practical control |
|---|---|---|
| Integration becomes a rewrite | Valuable working domain logic gets stalled or lost. | Extract interfaces and migrate one thin vertical slice at a time; retain old paths until verification. |
| Overbuilding the graph | Graph capability becomes a schema project with no useful user loop. | Start with identifiers and lineage required by active workflows; add richer graph behaviour only when it unlocks a concrete query. |
| “One OS” turns into one blob | Independent domains become tightly coupled and hard to change. | Keep vertical applications separate behind domain routers; share only genuine horizontal capabilities. |
| Duplicate UI/server drift returns | The same state and contracts are reimplemented repeatedly. | Enforce the Constitution: one FastAPI UI gateway and one React shell for internal surfaces. |
| Unsupported fluent reasoning | Finance, learning, research, or planning outputs look authoritative without evidence. | Preserve source links, evidence grades, review gates, and explicit uncertainty. |
| Privacy and credentials drift | Personal data and provider keys are spread across browser/client code and copies. | Local-first defaults, server-side keys, rotated exposed credentials, gateway mediation, and documented external boundaries. |
| The portfolio never ships | New designs displace real use and feedback. | Each quarter prioritise one end-to-end loop used personally, with a definition of done based on observed use rather than architecture completeness. |

## How to pitch the project

### Short pitch

This is a local-first personal AI operating system that turns scattered information—documents, articles, conversations, media, plans, and personal signals—into grounded knowledge, better decisions, and follow-through. Unlike a generic chatbot, it preserves provenance, asks for review before consequential actions, and learns from the outcomes of its recommendations.

### Product pitch

Most AI tools solve one moment: search a document, summarise a podcast, make a plan, or answer a question. This system connects the moments. It captures source material safely, creates a durable knowledge layer, applies specialised research and reasoning engines, turns useful material into learning and actions, and records what happened so future recommendations can be calibrated. The result is a personal system that compounds rather than resetting with every new chat.

### Technical/strategic pitch

The project is a modular, local-first AI workbench built from specialist applications over a shared substrate. The shared layer provides provenance-aware storage, model and embedding routing, structured tool access, and a unified local user surface. Vertical modules handle research, ingestion, learning, financial analysis, planning, and decision calibration. The architecture avoids the common trap of building a giant agent: it keeps domain workflows independent but lets trusted facts, entities, sources, and outcomes flow between them.

### Why it is different

- It is designed around durable artifacts and lineage, not ephemeral conversation history.
- It separates source facts, machine interpretation, and user decisions.
- It treats uncertainty, counterarguments, and falsifiable predictions as first-class outputs.
- It is local-first for sensitive personal and financial context.
- It uses human confirmation as an intentional control surface, especially for writes and ambiguous extraction.
- It becomes more useful as it accumulates reviewed knowledge and resolved outcomes.

## Suggested Claude handoff prompt

Attach this document and ask Claude to act as an integration partner, not to immediately rewrite the workspace. Tell it to: preserve the stated constitutional decisions; distinguish active modules from historical references; identify the narrowest verifiable next slice; propose changes in the order set out here; and flag any change that would introduce a second data root, UI host, model gateway, or incompatible identity scheme.

## Bottom line

The portfolio’s real asset is not any single agent, dashboard, or model call. It is the emerging closed loop:

**capture with evidence → build durable knowledge → reason with specialised tools → learn and act safely → observe outcomes → improve future judgement.**

The next step is to make that loop real in one production-quality path—starting with ingestion and extending through research, learning, and decision calibration—then let the rest of the workspace converge on it incrementally.

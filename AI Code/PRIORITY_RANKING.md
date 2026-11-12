# Priority ranking — AI OS workspace

Evidence base: independent code audit (ran `merged-ingestion`'s test suite directly — 451 passing;
booted `AI OS/gateway` in real, non-preview mode and confirmed it imports and mounts
`merged-ingestion`'s `ReviewService`/router as its only live backend; grepped for real cross-project
imports of `llm_gateway` and `mcp_server`; inspected `Database/` contents and `mcp_server/tools/`
stub files directly) plus `AI_OS_PORTFOLIO_OVERVIEW.md` for folders not independently re-audited
(marked *doc-sourced* below). Ranking reflects build priority, not folder size or age.

Dependency chain as it actually exists in code: `llm_gateway` **→** `merged-ingestion` **→** `AI OS/gateway` **→** `AI OS/shell`**.**

---



## Tier 1 — Foundation (everything else depends on these being solid)

1. `llm_gateway` — confirmed broad real fan-in: AI Agent, Learning System, `mcp_server/tools/study`,
  and merged-ingestion all live-import it. Already stable. Job now is guarding it (metering/budget),
   not rebuilding it.
2. `ingestion-pipeline` — proven load-bearing (sole producer of everything in `Database/`,
  consumed live by AI OS's gateway) and still visibly unfinished (`integration/to_do_plans/` shows
   active, incomplete iteration). **Top active-work priority.**
3. `AI OS` — the only real consumer of ingestion; the gateway boots it as a live backend today.
  Priority: finish the `/ingestion` route for real use, don't let the `AI_OS_PREVIEW` fixture
   coordinator substitute for it long-term.
4. `Database` — no code of its own, just the substrate merged-ingestion writes to. No dev work
  needed; priority here is housekeeping — the 363MB `_trash` of superseded systems, confirming
   nothing still reads from archived dirs.
5. `Constitution` — docs only (one `.docx`, one `.svg`), no code. Keep it honest as the above
  changes; don't let it drift into describing a system that no longer matches reality.



## Tier 2 — Where the value loop gets proven next

1. `Decision Tracker` *(doc-sourced)* — most product-ready vertical; natural first home for a
  real feedback loop once ingestion output is trustworthy.
2. `Personal/Research_MCP` *(doc-sourced)* — strongest research implementation; second connector
  into the knowledge layer.
3. `mcp_server` — mostly scaffold today: 8 of 10 tool categories are empty 16-line stub
  `__init__.py` files (confirmed); only `study/` has real logic. Nothing outside the package
   currently imports it. Low priority *right now*, rises once Tier 1 is stable and something needs
   to call tools through it.
4. `AI Agent` *(doc-sourced)* — real 5-stage loop, but has a known unfixed regression
  (`index_document`/`search_knowledge` broken since 2026-07-05, left unfixed on purpose). Fix
   before treating it as an orchestration layer.



## Tier 3 — Specialist engines (valuable, can wait on Tier 1/2)

1. `Learning System` *(doc-sourced)* — real, tested plumbing, but grading is contractually tied
  to a production knowledge graph that's unpopulated for arbitrary topics.
2. `Steelman Generator` *(doc-sourced)* — mature, well-built engine, high quality, but stands
  alone until there's knowledge for it to consume.
3. `Mental Models Creator` *(doc-sourced)* — conceptually central (Model Forge), but only narrow
  workflows are built out.
4. `Mirofish` *(doc-sourced)* — early-stage; curated event graph exists, but propagation and
  backtesting are later milestones.
5. `Accountability Agent` *(doc-sourced)* — working standalone product (PRAXIS); good closed-loop
  idea, premature to migrate.



## Tier 4 — Standalone action/capture products (real value, deliberately separate for now)

1. `frontend` — mixed: Marginal (highlighter) is a genuinely strong capture input worth feeding
  into ingestion soon; the old Ingestion Review Screen is superseded; Flashcards is future work.
2. `Personal` *(as a folder)* — Planner+Reminders and upi-agent are both solid verticals
  *(doc-sourced)*, but neither should get more investment before the shared substrate (Tier 1) is
    real.
3. `Automation Personal` *(doc-sourced)* — thin scheduling wrappers around Learning System and
  the podcast pipeline; correctly kept thin, don't build ahead of the engines underneath.
4. `Advisor` *(doc-sourced)* — small, already-fine deliberation primitive; low priority to touch.



## Tier 5 — Reference / do not build on this

1. `React Loop` — educational reference agent (hand-built ReAct loop); don't extend or duplicate
  its local tool server.
2. `gesture control` *(doc-sourced)* — deliberately bounded experiment, no core integration until
  reliability is proven with real use.
3. `Work` *(doc-sourced)* — near-entirely historical prototypes and duplicated bundles (earlier
  AI Analyst, gateway, podcast generations); lineage reference only.
4. `Future gateway porting` *(doc-sourced)* — planning notes on migrating earlier gateway work;
  read for context, no action.



## Tier 6 — Cleanup, not investment

1. `_archive` — archive; leave alone.
2. `Consequence Radar` *(doc-sourced)* — empty placeholder; decide now (fold into Mirofish's
  event/cascade capability, or delete) rather than let it linger undecided.
3. `untitled folder 2` — empty; delete.

*(Excluded from ranking:* `.agents`*,* `.claude`*,* `.venv` *— tooling and environments, not projects.)*

---



## Bottom line

Don't spread effort past #1–#3 until those three are genuinely solid. Everything in Tier 2 and below
is waiting on that substrate whether or not it looks that way from inside those individual folders —
`ingestion-pipeline` is the one place where "real and running" and "still unfinished" overlap, which
is the actual definition of a bottleneck worth fixing first.
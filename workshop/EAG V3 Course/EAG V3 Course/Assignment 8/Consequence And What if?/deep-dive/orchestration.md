# System Orchestration — How It All Fits Together

**Last updated:** 2026-08-24

---

## 1. System Overview (Plain English)

Consequence Radar accepts a finite set of news links, chooses one development that can plausibly matter to Indian equities, researches the causal chain, challenges that chain, and writes a cited newsletter article. It behaves like a small research desk whose filing cabinet records each source, decision, revision, warning, and failure. The article is not the source of truth: the versioned graph and append-oriented SQLite artifacts are. The system is research software and deliberately refuses to issue trading instructions.

---

## 2. The 30-Second Mental Model

FastAPI accepts work and a bounded thread pool runs a synchronous `Pipeline`. The pipeline normalises and pre-reads the batch, groups duplicates, asks Gemini for typed proposals, locally validates a versioned causal graph, performs Google-grounded search plus guarded page fetching, verifies exact source passages, challenges the resulting hypothesis, compiles only accepted context, and validates a one-call report. `Repository` persists status, events, and every meaningful artifact so the browser, API, and audit export all read the same durable record.

---

## 3. Architecture Diagram

```text
[Browser form / JSON API]
            |
            v
 [FastAPI web/app.py] ----read----> [SQLite Repository]
            | submit                       ^
            v                              | artifacts/events/status
 [bounded worker thread]                   |
            |                              |
            v                              |
 [Pipeline.run()] -------------------------+
    |       |          |
    |       |          +--> [Gemini typed generations + grounded search]
    |       +-------------> [guarded HTTP fetch + text extraction]
    +---------------------> [local graph/evidence/report validators]
            |
            v
 [validated report or inspectable failure]
            |
            v
 [HTML / SSE / report / graph / audit / export endpoints]
```

---

## 4. End-to-End Execution Trace — A Story Through the System

### Layer 1 — The Story in Plain English

A user supplies article links. The application validates the list, saves a queued job, and starts it in the background. The research process cleans the links, reads enough of each item to compare them, groups repeated coverage, and chooses the most defensible development. It builds a cause-and-effect map, searches for evidence to test weak links, and keeps only claims whose quoted passage really appears in the fetched page.

The map is revised only through small checked changes. After bounded research, the application makes sure the chain reaches a concrete Indian-equity outcome, tries to disprove it, resolves the objections once, chooses the best-supported case, and gives a reduced accepted record to the writer. The finished article is published only if deterministic checks accept it; otherwise the draft and errors remain available for audit.

### Layer 2 — The Story With File Names

`web/app.py` turns a form or JSON submission into a strict `NewsBatch`, asks `storage.Repository` to create a run, and submits `pipeline.Pipeline.run()` to its `ThreadPoolExecutor`. The pipeline uses `ingest` and `deduplicate` before `select` asks the model for candidates and local ranking chooses the winner. `graph.build_initial_graph()` gets one repair chance, after which `research` repeatedly generates tasks, calls the search and fetch providers, extracts draft claims, and delegates literal passage verification to `evidence`.

Research patches are applied to a deep copy by `graph.apply_patch()` and persisted only after graph validation. `challenge` performs whole-graph review, challenge, and adjudication; `cases` validates a central path; `report_context` topologically orders and size-bounds the accepted state; and `report` generates and validates the newsletter. All stages write through `storage.Repository`, while the web layer exposes the same records through HTML, SSE, JSON, Markdown, graph, audit, and export routes.

### Layer 3 — The Full Trace

1. `web/app.py:create_run_from_form()` (L62–77) splits nonblank lines and constructs a `NewsBatch`; invalid URLs re-render the form with HTTP 422. The JSON route `create_run()` (L86–90) receives the richer typed batch directly. Both call `Repository.create_run()` (`storage/__init__.py` L126–132), which commits a `runs` row and then separately commits the first event. A crash between those commits can leave a queued run without its queued event.
2. The web route submits `start(run_id)` to a process-local `ThreadPoolExecutor` (`web/app.py` L29–30, L53–56, L75–76/L88–89). `start` creates a fresh pipeline and catches any exception escaping it, although `Pipeline.run()` normally converts its own exceptions into failed artifacts and status.
3. `Pipeline.run()` loads the stored batch and replaces upstream IDs with SHA-256-derived IDs of canonical URLs (`pipeline/__init__.py` L49–56; `ingest/__init__.py` L10–27). Exact duplicate canonical URLs disappear. Unsafe URLs can fail here before the run reaches pre-reading because `normalize_batch()` does not catch `UnsafeUrl`.
4. Pre-reading (`pipeline` L56–58; `ingest` L30–46) uses supplied headline-plus-snippet text when both exist and total at least 240 characters. Otherwise `PageFetcher.fetch()` performs DNS/public-address checks, bounded manual redirects, type and byte checks, transport retries, and Trafilatura extraction (`providers/fetch/__init__.py` L54–115). Fetch errors become `DiscoveryExtract.failure_reason` rather than aborting the batch.
5. `deduplicate()` groups extracts by Jaccard overlap over filtered tokens and assigns the least-settled factual label observed in each cluster (`deduplicate/__init__.py` L32–56). `select_candidate()` then gives all extracts and groups to Gemini, drops candidates citing unknown item IDs, retains at most three by local rank, and raises when none passes both gates (`select/__init__.py` L16–35).
6. `build_initial_graph()` makes a reasoning-model call, resets the returned version to 1, and validates topology and references (`graph/__init__.py` L123–132). A bad graph gets one structured repair request; a second failure aborts the run.
7. The research loop runs at most `MAX_RESEARCH_CYCLES` times (`pipeline` L64–97). `generate_tasks()` priority-sorts and caps model-proposed tasks (`research/__init__.py` L14–17). `retrieve_for_tasks()` enforces query/source counters, searches, normalises and de-duplicates URLs within that call, fetches each page, and returns explicit failure strings (`research` L20–40). Source IDs use the run-wide source counter.
8. `extract_claims()` sends at most 8,000 characters per source to the model (`research` L43–46). `verify_claims()` accepts a draft only if the normalised exact passage is a substring of the stored fetched text and the strict `EvidenceClaim` validates (`evidence/__init__.py` L14–31). Rejections are persisted beside accepted claims.
9. Gemini proposes a `GraphPatch`; `apply_patch()` changes a deep copy, increments its version, and validates before return (`pipeline` L80–95; `graph` L89–114). One repair is attempted after any exception. There is a current structural defect: assumption and estimate operations import from nonexistent `.models` (`graph` L99–110), so those operations fail as `ModuleNotFoundError` and are recorded as ordinary invalid patches.
10. Finalisation validates an Indian path and estimate references (`pipeline` L98–106; `graph` L59–66). If only estimates are missing, a quantification patch is requested; unlike research patches, that application has no repair wrapper. `whole_graph_review()` may apply another patch, also without a repair wrapper (`pipeline` L107–109).
11. The pipeline persists challenge findings, asks a separate adjudicator for decisions, flattens every operation belonging to an `accept_...` decision, and applies them as one patch (`pipeline` L110–123; `challenge/__init__.py` L15–24). `cases.select_cases()` then checks the model's central and alternative cases against active graph IDs, claim IDs, estimates, path adjacency, and material assumptions (`cases/__init__.py` L12–43).
12. `compile_context()` keeps verified claims, excerpts source bodies to 600 characters and exact passages to 400, topologically orders nodes, and approximates tokens as JSON characters divided by four (`report_context/__init__.py` L28–54). On overflow it removes non-load-bearing accepted background claims; it never similarly removes contradicting claims. Remaining overflow is fatal.
13. `write_report()` makes one report-tier call and locally checks word bounds, source IDs, exact assumption strings after whitespace collapse, two minimal narrative fields, a nonempty change list, and prohibited investment language (`report/__init__.py` L27–46). Validation errors save `report_draft` and produce `report_validation_failed`; otherwise the report is saved and status becomes `completed` or `completed_with_warnings` (`pipeline` L128–140).
14. The browser reads persisted state. The SSE route resumes from `Last-Event-ID`, polls every 0.35 seconds, performs one final drain after terminal status, and stops after the run budget plus 60 seconds (`web/app.py` L98–133). Report, graph, audit, and export routes never reconstruct analysis; they return repository artifacts (`web/app.py` L135–160).

---

## 5. Component Map

| File/package | What it does in the system | Owns this state | Talks to |
|---|---|---|---|
| `web/app.py` | HTTP entry points, worker pool, rendering, SSE, downloads | Executor and app state | Pipeline, repository, templates |
| `pipeline/__init__.py` | Fixed end-to-end orchestration | Active run ID, ledger, latest model-call ID | Every analytical stage |
| `models/__init__.py` | Strict shared schemas and enums | Type contracts only | Pydantic |
| `storage/__init__.py` | Durable run/event/artifact ledger | SQLite rows | SQLAlchemy/SQLite |
| `graph/__init__.py` | Graph validation, ordering, patching, initial build | Returned graph versions | NetworkX, model client |
| `research` + `evidence` | Gap tasks, source retrieval, claim extraction and literal verification | Per-cycle lists/counters supplied by pipeline | Search, fetch, model |
| `providers/*` | External model, search, and page boundaries | SDK clients and settings | Gemini, DNS/HTTP |
| `challenge`, `cases` | Disproof, adjudication, and scenario selection | Returned typed decisions | Model and graph validator |
| `report_context`, `report` | Accepted-context reduction and publication gate | Returned context/report | Model and local validators |

---

## 6. Mode / State Machine

In plain English, a run advances through named milestones so the user can see where it is, then lands in one terminal state. Internal work such as whole-graph review and case selection occurs inside a surrounding milestone and does not have its own persisted `RunStatus`.

The enum defines `queued`, `pre_reading`, `selecting`, `building_graph`, `researching`, `quantifying`, `challenging`, `adjudicating`, `compiling_context`, `writing_report`, `completed`, `completed_with_warnings`, `failed`, and `report_validation_failed` (`models/__init__.py` L51–65). `Pipeline._stage()` updates status, persists an event, and invokes the optional callback in that order (`pipeline` L46–47). Whole-graph review runs while status still reads `quantifying` (L98–110), and case selection runs while it still reads `adjudicating` (L112–125).

There is no transition guard in storage: `Repository.set_status()` accepts any enum or string and simply overwrites the row (`storage` L134–141). Restarted processes retain state but do not resume in-flight work. A worker cancelled at shutdown can therefore remain in a nonterminal state indefinitely; SSE stops its own polling after a deadline, but it does not repair the run.

---

## 7. Key Integration Points

The prompt paths in stage code must match package files because `load_prompt()` joins each name beneath `src/consequence_radar` (`providers/model` L36–41). Pydantic schemas are the explicit handoff between all model calls and local code. Artifact kinds and keys are an implicit contract shared by the pipeline and web page; renaming `report`, `graph`, `cases`, `usage`, or `report_validation` in one side requires updating the other.

Graph IDs are another system-wide contract. Claims originate in `evidence`, source IDs originate in `research`, graph operations originate in model responses, and `graph`, `cases`, and `report_context` validate or consume those references. `GraphPatch` allows assumption and estimate operations, so the incorrect relative imports in `graph.apply_patch()` are a cross-cutting failure, not an isolated unused branch.

Configuration is read once through cached `get_settings()` for the module-level app, while tests normally construct `Settings` directly. `.env.example` must stay aligned with `Settings`; currently it omits several optional fetch bounds and states `MAX_MODEL_CALLS_PER_RUN=30` / `MAX_WALL_TIME_SECONDS=600`, overriding code defaults of 45 / 1800 when copied by `./radar`.

---

## 8. External Dependencies (System-Level)

- Gemini Developer API supplies structured generations and Google-grounded search. Missing credentials fail real pipeline construction; SDK/network/model errors normally fail the run, while per-source search/fetch errors can become warnings.
- DNS and arbitrary public HTTP(S) article hosts supply research pages. The fetcher rejects local/private destinations and bounds redirects, type, time, and bytes; it cannot make paywalls or extraction-resistant pages readable.
- SQLite is the durable local source of truth. Schema creation happens at app startup; WAL and a five-second busy timeout reduce reader/writer contention, but the design still targets one process.
- Jinja2, FastAPI, and Uvicorn provide the browser/API shell. The analytics pipeline does not import them.
- Google Fonts is referenced by the UI when available and is cosmetic; local font fallbacks remain usable offline.

---

## 9. Known Architectural Risks

- `graph.apply_patch()` cannot currently add or update assumptions or estimates because L99–110 import from `.models` instead of `..models`. Broad patch exception handling makes the defect resemble ordinary invalid model output.
- The quantification and whole-graph-review patches do not receive the one-repair protection used in research cycles (`pipeline` L100–109).
- Search-source de-duplication is local to each `retrieve_for_tasks()` call, so the same URL can be fetched and assigned a new source ID in later cycles.
- Report validation permits a report with no citation marker, does not require marker equality with `source_ids_used`, and does not prove every factual sentence is supported (`report` L27–41).
- `warning_count` is stored and returned but never incremented; `completed_with_warnings` is inferred from in-memory failures/rejected claims instead.
- In-flight work is not restartable, and the process-local thread pool is not a distributed queue.
- The health route reports configured state but performs no live database, Gemini, search, or fetch probe (`web/app.py` L162–164).
- `.env.example` overrides two newer, larger code defaults when `./radar` copies it: model calls become 30 instead of 45 and wall time becomes 600 seconds instead of 1800. Operators should treat the copied environment as authoritative.

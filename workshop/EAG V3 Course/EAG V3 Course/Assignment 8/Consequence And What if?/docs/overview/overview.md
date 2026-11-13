# Consequence Radar — Codebase Overview

Last updated: 2026-08-24 (Asia/Kolkata)

## 1. What This Project Is

Consequence Radar is a research application that accepts a finite batch of news stories, chooses the story with the strongest defensible connection to Indian equities, and turns it into a causal, evidence-linked newsletter article. Its purpose is not to predict share prices or recommend trades; it is to make the reasoning between “this happened” and “this may matter to an Indian company, sector, or market measure” visible, testable, and auditable [WHAT IT SHOULD DO IS THE FOLLOWING, I WANT TO REWORD IT IN A WAY THAT MAKES IF MORE THE WAY I SEE IT WORKING,   

ITS JOB IS TO TAKE A LARGE NUMBER OF POSSIBLE HEADLINES FROM A SYSTEM, ITS THEN SUPPOSED TO, READ THE HEADERS OF THE LINKS ITS GHIVEN, AND BASED ON READING THIS ITS SUPPOSED TO DECIDE IF THIS NEWS IS RELEVANT TO INDIAN EQUITIES AND IN WHAT WAS IS IT RELEVANT, IS THERE A SCENRIO IN  WHICH THIS STORY WILL HAVE POSSIBLE KNOCK ON EFFECTS, AND HOW, WHAT ARE THE POSSIBLE KNOCK ON EFFECTS THIS STORY WILL HAVE ??]

The project is standalone. Nothing in its running code imports or depends on the older What If Analyser project.

## 2. The Big Picture — How It All Fits Together

The easiest way to picture Consequence Radar is as a small editorial research desk with a strict filing system. A bundle of news arrives at the front desk. An editor chooses the most promising story, researchers gather evidence for the links in the story, an analyst builds a map of causes and consequences, a sceptic tries to break that map, and a writer turns the surviving analysis into an article. Behind everyone is an archivist who keeps every meaningful draft, source, decision, failure, and revision. [THE IDEA IS THAT THESE ARE NOT DIFFERENT PEOPLE, THEY ARE THE SAME PEOPLE DOIONG THE SAME THING, THE SAME TASK, THE IDEA IS THAT AN ANALYST SEE'S MULTIPLE NEWS STORIES RIGHT NOW, WHAT WE WANT TO DO IS, HAVE 2 DIFFERENT VERSIONS OF THE SYSTEM THAT TAKES A BUNCH OF LINKS AND MAKES THE KNOCK ON EFFECTS OF THE GRAPHS FROM THIS TO SHOW, THE NEXT BEING TAKES A BUNCH OF LINKS AND THEN BUILDS ON TOP OF IT, BUILDS ON TOP OF IT BY FIRST GOING THROUGH ALL THE HEADLINES AND FINDING THE NEWS AND THEN DECIDING WHICH NEWS IS ACTUALLY GOING TO HAVE THE MOST LONG TERM EFFECT THEN FOR THAT IT RUNS THE WHOEL SUITE, NOW THIS NEEDS TO BE MAPPED OUT, AND NEEDS TO BE MAPPED OUT WELL   

WHAT NEXT ALSO NEEDS TO BE DONE IS REFRAMING YOU PERSONA VIEW, THE WAY THIS WORKS IS THAT AN ANALYST THINKS A FEW NEWS ARTICLES ARE REALTED AND HE WANT TO KNOW HOW, HE COMES TO YOU AND GIVES YOU THE LINKS OF THE ARTICLES, YOU THEN TAKE THE NEWS ARTICLES AND YOU START DOING DEEP RESEARCH ON THEM, (THIS IS THE PART WE BUILD FIRST, WE DONT BUILD THE NEWS SEELCTION FIRST, THATS FOR ITERATION 2) BY DEEP RESERARCH I MEAN REALLY REALLY DEEP RESEARCH AND TRULY AGENTIC RESEARCH AS IN THE AGENT FIND THE ANNUAL REPORT ANALYSES IT, GOES AND SEARCHES THE COMPANY WEBSITE, FIND OUT EVERYTHIGN GHT ECONTRACTS THE SUPPLIERS THE COUNTRY ALL OF IT, AND DOES THIS BLOODY BLOODY WELL NO ROOM FOR SHIT JOBS] 

The front door is a web application. A user can paste one to one hundred news links into a simple page, or another system can send a richer batch through the public programming interface. The richer route can include headlines, summaries, publishers, dates, and topics [YOU WILL HAVE TO FIND ALL OF THIS THE PERSON INPUTTING THE LINKS WONT PUT THIS]. Submission does not keep the web request open while research runs. The application records a new job, returns its identity immediately, and hands the work to a small pool of background threads. The user’s run page then listens to a stream of progress events and refreshes when the work finishes or fails.

The central research process is a fixed, bounded sequence rather than an open-ended autonomous agent [THATS WRONG AND A STUPID MISTAKE TO MAKE, DONT MAKE IT, THIS NEEDS TO BE CHANGED ASAP]. First, it cleans the supplied links, assigns stable internal identities, and gathers just enough page text to understand each development [I THINK THIS IS THE WRONG APPROACH FOR NOW]. It groups substantially similar coverage and applies a cautious label such as rumour, proposal, announcement, implementation, or measured outcome. A language model proposes up to three candidate research seeds [BASED ON WHAT AND HOW ?], but ordinary local code performs the final ranking and refuses to proceed when neither the premise nor the Indian-equity route is credible.

The winning seed becomes a causal map. This is a one-way graph: a set of connected statements showing how the reported event may cause an immediate effect, how that effect may travel through costs, demand, regulation, financing, competition, or another business mechanism, and where it may ultimately reach a concrete Indian company, sector, operating result, earnings measure, or market variable. The graph is the application’s working memory, not just a picture for the reader. Assumptions, evidence references, contrary evidence, estimates, timing, confidence, and conditions all belong to specific links in this map [BUT IT DOESNT ACTUALLY DO ANY RESEARCH DOES IT ?] .

Local validation acts like building control. It insists that the map have one active news root, real endpoints, no duplicate identities, no circular reasoning, no disconnected outcome, and no direct leap from a headline to a stock price [HOW DOES IT DO THIS ?]. Later in the run it also insists on a reachable Indian-equity outcome and at least an explicit directional estimate at each Indian terminal. The language model is allowed one repair attempt for a malformed initial graph and one repair attempt for each malformed research patch. If repair fails, the process keeps the last valid graph rather than accepting the broken replacement. [WHAT IS THIS AND HOW DOES IT DO IT ??}   

[WE ACTUALLY HAVE THE CAPABILITIES TO MAKE SOEMTHING REALLY SPECIAL HERE LETS NOT FUCK THIS UP]

Research is driven by gaps in that map. A model identifies targeted questions about the premise, load-bearing mechanisms, Indian exposure, quantities, assumptions, and counterevidence. A Google-grounded search adapter finds source links. A guarded page reader checks that each destination is public, follows only a limited number of safe redirects, accepts only readable text formats, limits download size, and extracts clean article text [SO MANY RESTICTIONS YOU HAVE MENTIONE DBUT YOU HAVE NOT MENTIONED WHAT IT FINDS AND LOOKS FOR AND HOW IT DOES THAT ? WHAT SOURCES IS IT PULLING RESEARCH FROM AND HOW ACCURATELY IT IS DOING SO]. Another model proposes small, atomic claims from bounded excerpts. Local code then performs the decisive evidence check: the quoted passage must literally occur in the stored source after conservative whitespace normalisation. If it does not, the claim is rejected and retained as a rejection record [WHAT DO YOU MEAN BY THIS ?].

Research changes the graph through named operations—adding, updating, or rejecting a node, connection, assumption, or estimate. It does not ask the model to rewrite the entire graph [CAN WE DEFINE EACH OF THE ABOVE AS A TOOL OR ATLEAST SEPERATE THEM OUT FOR NOW THEY ARE USEFUL TOOLS AND DEFINITIONS TO HAVE IN PLACE]. Every accepted change creates a new graph version and a revision record [IS THAT THE RIGHT WAY TO DO THIS ?? I AM NOT SOO SURE IT IS, TELL ME IF YOU THINK I AM WRONG ?]. The cycle can repeat, but central limits cap research rounds, tasks, searches, sources, model calls, graph size, and elapsed time. It can also stop early when there are no more tasks or the patch reports no remaining gaps. [YES THAT IS FINE, BUT I STILL WANT TO UNDERSTAND THE TECH STACK AND HOW IT WORKS, WHAT IT DOES AND WHY IT DOES IT] 

Once research stops, the pipeline checks the Indian endpoint and its estimate. If the graph lacks even a directional estimate, it asks for one more evidence-constrained graph patch. It then reviews the whole chain in one fresh pass, because individually plausible links can still form an implausible story when joined together. A challenger receives the full graph, claims, and research failures and names concrete ways it could be wrong. A separate adjudicator considers each finding once and may revise, remove, branch, reject, or leave the issue unresolved. There is no endless debate. [YES BUT HOW, THIS IS A MAJOR CONCERN BUT I AM NOT ENTIRELY SURE OF THIS, I DONT KNOW WHY IT EXISTS AND WHAT IT MEANS] [MAYBE ITS BEST TO MAKE THE GRAPH AND THEN FEED THE GRAPH TO THE SYSTEM FOR AN OVERALL EVALUATION, DOES IT MAKE PLAUSIBLE SENSE, IF NOT THEN WE CAN CHANGE IT] 

The surviving graph is used to select one central case and only those alternatives caused by material assumptions. A deterministic compiler then packages the accepted graph, cases, evidence, estimates, challenge decisions, gaps, and source records [BY COMPILER YOU MEAN THE UI CODE ?]. It deliberately excludes raw article pages from the writing prompt [WHY ?]. One report-writing call produces the structured newsletter. Local checks reject unknown source markers, unknown assumptions, prohibited investment instructions, thin required summaries, and articles outside the configured word range [THERE SHOULD BE NOTHING THAT IS UNKNOWN, IF ITS BEEN READ THEN WHY IS IT UNKNOWN ?, IF ITS LOAD BEARING YOU HAVE USED IT TO WRITE AND YOU ARE REJECTING IT BECUASE YOU DONT/CANT CITE IT THEN YOU SHOULDNT HAVE READ IT AT ALL].

Throughout this journey, SQLite is the durable filing cabinet. The input, status changes, progress events, discovery extracts, candidate ranking, sources, accepted and rejected claims, research tasks, every graph version, invalid patches, revisions, challenges, cases, report context, report or failed draft, usage, and errors remain inspectable [I THINK WE NEED TO PUT THIS ON THE SHELF, I DONT THINK WE NEED TO SHOW THIS RIGHT NOE, I THINK IT CAN BE AVOIDED FOR NOW, TO DO IT AND PUT TH ECODE ON SHELF FOR LATER USE]. A failed investigation therefore leaves a useful record and does not erase earlier successful ones. [IT SHOUDLNT DO THAT AT ALL RIGHT, IF ITS FAILED, ITS FAILED YOU SHOW THE ERROR ON THE TERMINAL, CROSS SESSION MEMORY IS NOT SOMETHING WE NEED TO WORRY ABOUT RIGHT NOW] 

## 3. Every Component — What It Does and Why It Exists



### The shared vocabulary

The domain model is the system’s common language. It describes news items, batches, pre-reading results, duplicate groups, candidate stories, graph nodes and links, assumptions, estimates, source passages, research tasks, challenge findings, cases, reports, usage records, and run states. These descriptions are deliberately strict: unexpected fields are refused, important text cannot be empty, candidate grades must cover exactly seven dimensions, numerical ranges must be ordered, sourced estimates must cite claims, and calculated ranges must expose their inputs and formula. Without this layer, each model call and pipeline stage could interpret the same concept differently, and malformed responses could travel far into the run before failing. [EACH OF THESE ASSUMPTIONS NEEDS TO BE CHALLENGED, WE WILL MODUALRISE THE OCDE AND INSPECT IT I WILL THEN HAVE A READ OVER EVERYTHING, NOT THAT ITS WRONG I WANT TO LEARN WHY YOU MADE THESE DECISIONS AND PUSH THEM A BIT] 

This vocabulary also makes distinctions that matter editorially. A fact is not a forecast, a forecast is not an assumption, and an inference is not an observed result. Decimal values are used for research calculations so money and ranges are not quietly distorted by ordinary binary rounding.

### The central pipeline

The pipeline is the project’s conductor. It receives a saved run identity, loads the original batch, advances the run through each stage, calls the specialist modules in order, records every artifact, and converts an uncaught problem into an inspectable failed run. It has no knowledge of web pages or FastAPI, so tests or a future command-line interface can run it directly.

The pipeline owns the only complete end-to-end sequence: normalisation and pre-reading, de-duplication, candidate choice, initial graph creation, bounded research cycles, quantification check, whole-graph review, challenge, adjudication, case selection, context compilation, report writing, and final validation. It also connects each model call to the run’s usage record and connects each graph change to the model call that prompted it. If this file disappeared, the component parts would still exist but there would be no application-level research process.

### The graph engine

The graph engine is the analytical spine. It checks the integrity of a proposed causal map, orders active nodes from cause to outcome, applies small changes to a copy, and commits a higher version only if the result remains valid. Rejected nodes and links remain in the graph’s history rather than vanishing.

Validation covers identity uniqueness, graph size, valid link endpoints, reference integrity, exactly one active news root, absence of cycles, root direction, reachable outcomes, and basic protection against a direct headline-to-share-price leap. During finalisation it adds India-specific requirements: at least one concrete Indian endpoint must be reachable, and each such endpoint must have an estimate reference—even if that estimate honestly says only the direction is known. The engine is why the model’s output is treated as a proposal rather than truth.

One current defect works against that design. The code path that applies a patch adding or updating an assumption or an estimate imports the wrong module and crashes with an unrelated import error rather than validating normally; because patch-application errors are caught broadly and retried once, this currently looks like an ordinary rejected-and-repaired patch in the run record rather than the structural bug it is. See “Known Issues” below for the exact lines and effect.

### Durable storage and audit history

The repository is a thin durable memory built on SQLite. It stores three kinds of records: one row describing each run, an ordered stream of progress events, and a general artifact ledger. The artifact ledger can hold many types and versions without changing the database layout whenever the analysis vocabulary grows.

Artifacts are append-oriented. Saving a newer graph, task set, report draft, or usage snapshot does not overwrite the older copy. Each artifact has a kind, an optional key such as a research cycle, and a version. The repository also works with a temporary in-memory database for tests. On startup it creates the initial schema when necessary and stamps that schema as the first migration. An Alembic migration exists for managed database setup outside normal application startup.

### Ingestion, cautious grouping, and candidate selection

The ingestion cluster prepares supplied news without pretending to perform deep research. It removes common tracking parameters, normalises host names and paths, drops exact duplicate URLs, and replaces upstream identities with stable identities derived from canonical URLs. When the upstream item already supplies a sufficiently informative headline and summary, pre-reading avoids a network fetch. Otherwise it tries to fetch the page and keeps either the bounded result or an explicit failure reason.

De-duplication uses conservative word overlap rather than a model or semantic index. It groups stories only when their headline and opening text substantially overlap. It records publisher variety and, when different members imply different factual states, chooses the least settled label. This is deliberately biased against accidentally turning a rumour into an established event.

Candidate selection asks the fast model for candidates tied only to supplied item identities. Local code discards any candidate that cites an unknown item, scores the remaining candidates, retains at most three, and requires both a non-low grounded premise and a non-low Indian transmission grade. The gate matters because it lets the application fail honestly rather than fabricate an equity connection.

### Research, sources, and evidence

The research cluster converts graph gaps into ranked tasks, limits the number taken into each cycle, issues each task’s search queries, fetches unique pages within that cycle, and turns retrieved pages into stored source records. Source suitability is recorded in relation to the task that caused retrieval rather than through a universal domain ranking.

The fetching adapter is also the project’s network safety boundary. It refuses non-web links, local names, private and reserved addresses, unsafe resolved addresses, unapproved content types, oversized bodies, and excessive redirects. It checks every redirect destination again. It retries only transport and timeout problems within a small configured limit, and it uses a readable-text extractor for web pages.

Claim extraction is shared work between the model and local code. The model names an atomic claim and copies its passage; local code verifies the source exists and the passage is genuinely present. Accepted claims receive stable run-local identities. Failed attempts become rejected claims with reasons. This division is one of the strongest parts of the system because the language model cannot validate its own quotation by assertion.

### Quantification helpers

The quantification module provides deterministic range multiplication, currency conversion, and a simple plus-or-minus sensitivity calculation. Calculations preserve input identities, formulas, periods, units, currencies, assumptions, and caveats. A conversion produces a separate derived estimate so the original currency record is not lost.

These helpers currently exist as validated building blocks and are tested directly. The main pipeline does not yet discover inputs and invoke them automatically. Instead, it relies on the graph-patching model to add sourced ranges, derived ranges, or an explicit directional-only estimate. That difference is important when assessing how complete the promised quantification pass really is.

### Whole-story challenge and case selection

The challenge cluster provides three separate intellectual roles. The whole-graph reviewer inspects whether the entire chain remains coherent. The challenger tries to disprove named parts of the graph. The adjudicator considers those findings once and returns explicit changes only for accepted findings. Local graph validation remains the final authority after those changes.

Case selection happens after challenge. The model proposes a central path, alternatives, and broken paths. Local rules require the central path to be ordered and active, to refer only to existing assumptions and estimates, and not to consist entirely of assumption-only links. An alternative is accepted only if it depends on at least one material assumption. These rules prevent a mechanical four-scenario output, although the quality of “most supported” ranking still depends on the model’s judgment.

### Context compilation and report production

The context compiler is the wall between research and prose. It topologically orders the graph, includes only verified claims and their sources, separates supporting and contradicting evidence, and carries forward assumptions, estimates, challenges, decisions, gaps, and failures. It estimates prompt size using a simple character-based approximation. If the context is too large, it first removes supporting background claims that are not attached to active links or selected cases. It refuses to continue if the reduced context is still too large.

The report writer makes one normal structured model call. The response is checked locally for length, valid source references, known assumptions, substantive summary fields, a non-empty “what changes the view” list, and prohibited advice language. A bad draft is saved for inspection but is not exposed by the validated-report endpoint.

### Providers, prompts, metering, web shell, and operational files

Provider interfaces separate the application from its initial external implementations. One interface covers structured language-model responses, another covers search results, and the fetcher isolates page retrieval. The initial live implementations use Google’s Gemini service and native Google Search grounding. Model names remain settings, allowing fast, reasoning, and report roles to differ.

All ten analytical instructions live as versioned prompt files. They consistently describe retrieved text as untrusted data, insist on identities, separate fact from forecast and assumption, prohibit invented numbers and sources, and retain the Indian-equity objective. A thread-safe usage ledger counts external model/search calls, tokens, and elapsed time and blocks further calls when the configured call or time budget is exhausted.

The web shell provides the browser pages, public endpoints, background thread pool, progress stream, downloads, and application startup and shutdown. Templates and a small browser script handle submission, live progress, copying, and refresh. Styling, the package manifest, migration setup, sample exports, and environment template are peripheral operational support rather than analytical logic.

## 4. How a Typical Interaction Works

The most common journey begins on the home page. The user pastes one news address per line and submits. The browser turns those lines into a news batch and sends it to the application. Invalid addresses or a batch outside one to one hundred items are refused before a run begins. A valid request receives a run identity and a result-page address immediately.

The browser moves to that run page. While the analysis is active, the page shows the progress events already stored in SQLite and opens a live event stream for new ones. The background worker independently performs the research pipeline. Refreshing the page is safe because the event history and artifacts are not held only in the browser.

At the end, a successful page places the newsletter first. Beneath it are the central case, time horizon, direction, evidence status, the assumptions, and observations that would change the view. Next come the selected seed and any runners-up, then the active graph nodes and textual link mechanisms, estimates and formulas, material assumptions, and the complete artifact ledger. The user can copy the report, download validated Markdown, or export the full run as JSON.

If the report itself fails deterministic validation, the page clearly labels the draft as inspection-only and does not offer it through the validated report endpoint. If analysis fails earlier, the page shows the reason and links to the retained audit record. Older runs remain available on the home page in either case.

An upstream system can take the same journey through the API with richer news metadata. It submits a batch, polls the run-status endpoint or listens to the persisted event stream, then retrieves the final report, graph, audit ledger, or complete export. The API and browser use the same stored run and the same background pipeline.

## 5. How the System Makes Decisions

The first decision is whether an input item needs fetching. A sufficiently long supplied headline and summary are enough for discovery, so the system avoids unnecessary network work. Sparse items are fetched. A failed fetch does not remove the item; the supplied text and failure reason remain available.

Coverage is grouped only when lexical overlap crosses a conservative threshold. Within a group, the richest extract becomes the authoritative account for housekeeping purposes, while the factual state is chosen cautiously from all members. The system therefore prefers “proposal” over “decision” when the supplied coverage disagrees about whether the event is settled.

The model proposes candidates, but local code chooses the winner. Grounding and Indian-equity transmission are gates: either being low disqualifies a story. Eligible stories are then ordered by the combined grades across all seven dimensions. No eligible story means a fatal, explicit failure.

During research, the graph decides what to investigate. High-priority tasks come first and local settings truncate the list. Search and source counters decide when retrieval must stop. Each claimed quotation faces a binary local test: exact passage found means accepted; not found means rejected. A graph patch is similarly binary: a locally valid candidate becomes the next version; an invalid candidate gets one repair attempt and otherwise leaves the previous version in control.

The research loop ends when no tasks are returned, when a patch reports no gaps, or when the cycle ceiling is reached. Reaching the ceiling is not automatically fatal; the later graph and case checks determine whether the surviving hypothesis is usable.

At finalisation, a missing endpoint estimate triggers one extra quantification patch. Remaining graph errors are fatal. Challenge findings themselves do not change the graph. Only adjudication decisions beginning with an accepted action contribute operations. A central case is accepted only when it forms one coherent active chain and is not wholly unsupported. Alternative cases need a material assumption that genuinely changes the conclusion.

The report context either fits the budget, loses only non-load-bearing supporting background, or fails. The writer’s article is either published as validated output or stored only as a failed draft. Recoverable fetch failures and rejected quotations make an otherwise valid run “completed with warnings”; structural, budget, candidate, graph, case, context, or report problems fail closed.

## 6. How the Code Actually Flows — The Execution Journey

Execution normally begins when the web module is imported by the application server or launched through the installed `consequence-radar` command. Startup reads environment-backed settings, constructs the SQLite repository, creates the schema if necessary, stamps the initial migration, creates a bounded thread pool, mounts static files, and registers browser and API routes. It does not contact Gemini at startup, so the interface and offline tests work without credentials.

A submission enters through `POST /api/v1/runs`. Input validation happens before route logic. The repository creates a queued run and its first persisted event. The endpoint submits a small worker function to the thread pool and returns `202 Accepted`; the HTTP exchange is now complete while analysis continues elsewhere.

The worker constructs a fresh pipeline. This is the first point at which the default live model and search clients demand a Gemini or Google key. If construction fails, the worker marks the already-created run as failed. Otherwise the pipeline loads the batch and begins its synchronous sequence. Only separate submitted runs can execute in parallel, up to the worker limit. The stages inside one run execute one after another.

The original batch becomes a normalised batch and is stored. Pre-reading walks the items sequentially, optionally waits for each page fetch, and records every extract or failure. De-duplication runs locally. The candidate model call then waits for a structured response, after which local ranking names the seed. Another structured call waits for the initial graph. Local validation either accepts it, requests one repair and waits again, or ends the run.

The research loop asks for graph-gap tasks, stores them, and follows their search queries one by one. Each search call waits for Google’s grounded response. Each returned address is then fetched sequentially and converted into a source record. Claim extraction waits for a structured model response; local passage checks split it into accepted and rejected records. Tasks are rewritten with a completion, failure, or not-found status and all cycle artifacts are stored.

Next, graph patching waits for the reasoning model. A deep-copy application and validation happen locally. A valid patch creates a new graph and revision. An invalid patch is itself stored, then one repair request is made. After each cycle the pipeline either loops with the revised graph or hands that graph to finalisation.

Finalisation first validates concrete Indian outcomes. It may wait for a quantification patch, then waits for a whole-graph review and applies any changes. It waits once for the challenger and once for the adjudicator. Accepted adjudication changes produce another graph version. Final validation runs, then case selection waits for the model and faces local path rules.

The context compiler gathers the accepted state into one object and may deterministically trim background evidence. The newsletter call then waits for the report model. Local report checks run without another analytical model. The report, or the failed draft, validation result, and usage snapshot are persisted. Finally the run is marked completed, completed with warnings, report-validation-failed, or failed, and a terminal event is written.

Meanwhile, the browser’s event stream repeatedly checks SQLite. It sends any event newer than the client’s cursor, pauses briefly when there is nothing new, and closes after the terminal event has been delivered. The browser then reloads the result page, which reads the latest report, graph, cases, usage, events, and complete artifacts from storage.

Application shutdown stops accepting new background work and cancels work that has not begun. It does not delete database state. An interrupted active run is left with its last persisted stage and artifacts; there is currently no startup process that resumes it.

## 7. What the System Remembers

SQLite is long-term memory. A run row remembers the original batch, identity, lifecycle status, timestamps, error text, and a warning counter. The warning counter is present in storage but is not currently updated by the pipeline; warning meaning is carried mainly by terminal status and artifacts.

The event stream is the run’s diary. Every stage message has a per-run sequence number and timestamp. Because the browser reads this diary rather than process memory, refreshes and restarts do not erase completed progress.

The artifact ledger is the analytical memory. It retains normalised input, discovery extracts and inaccessible-page reasons, duplicate groups, candidate ranking, research tasks and their embedded queries, fetched sources and extracted text, accepted and rejected claims, graph versions, graph revisions, malformed patches, challenge findings, adjudication decisions, selected cases, compiled report context, report or invalid draft, validation result, model-call records, usage, and research failures contained in context. Cycle keys and graph versions let a reviewer reconstruct how the story changed.

Some state remains temporary. The active usage timer, call counter, search/source counters, accumulated in-memory source and claim lists, and current control position live inside the running pipeline. The durable copies preserve completed work, but losing the process loses the ability to continue from that exact point. The database can show where the run stopped, but the application will not restart it.

Corruption of the run row would make its artifacts difficult to reach through normal interfaces. Corruption or deletion of artifact records could break evidence lineage even if the final prose survived. The application relies on SQLite’s normal transactional guarantees but does not implement backup, integrity checking, retention policy, or artifact-level cryptographic verification.

## 8. What the System Talks To

The main external service is Google Gemini. Consequence Radar asks it for structured candidate, graph, task, claim, patch, challenge, case, and report objects. It also uses Gemini’s native Google Search grounding to obtain research source links. Missing credentials cause real submitted runs to fail clearly after queueing. Provider outages, malformed responses, or exhausted budgets also fail or become recorded research failures depending on the stage. There is no alternative production model or search implementation configured, although the interfaces and fake tests make replacement possible.

The application talks directly to public web servers to pre-read supplied items and fetch grounded research results. It receives readable page text and basic metadata. Unsafe, unavailable, paywalled, unsupported, oversized, or extraction-resistant pages produce explicit failures; the run may continue if its central analysis remains viable.

It talks to a SQLite file on local disk, under `data/` by default. Database failure prevents useful operation. It also reads prompt files, templates, styles, samples, and environment settings from the project. The browser optionally talks to Google Fonts; the interface falls back to local font families if that cosmetic request fails.

No calendars, brokers, exchanges, live market-data feeds, vector databases, user-account services, distributed queues, or What If Analyser runtime are connected.

## 9. What Is Currently Built vs. What Is Not Yet Built

The working MVP includes strict input and analytical models, safe URL handling, bounded pre-reading, conservative duplicate grouping, model-assisted candidate generation with local gating, a persistent versioned causal graph, targeted research tasks, native grounded search, guarded fetching, exact-passage claim verification, graph patch history, whole-graph review, one challenge and adjudication round, central-case rules, deterministic context compilation, one-call report generation, persistent API jobs, live progress events, browser inspection, Markdown and JSON exports, migrations, samples, and offline tests. The current suite contains 69 passing tests covering the main local invariants and mocked end-to-end paths. It emits one dependency-level deprecation warning because FastAPI's current `TestClient` imports Starlette's deprecated `httpx` compatibility layer.

The live path has not been smoke-tested with real credentials. The sample report and export are documentation artifacts, not proof that the current Gemini models successfully complete a production run. Current model defaults name particular Gemini versions through configuration; operators can change them without editing business logic.

Several features are present but narrower than the full product specification. The browser form accepts URLs only, although the API accepts richer metadata. The selector retains up to three candidates but does not guarantee a winner plus two runners-up; a mocked successful run uses only one candidate. Graph rendering is a sequence of node cards with link details below it, not a spatial connected graph. Restart-safe history is built, but restart recovery of an active job is not. The thread pool and SQLite design target one application process, not distributed workers.

Quantification is the largest analytical gap. Decimal range, currency, and sensitivity helpers exist and pass tests, but the main pipeline does not automatically search for base values and coefficients, perform formulas, or run sensitivity checks with those helpers. It asks the model for a graph patch and accepts directional-only estimates when numbers are unavailable. This preserves honesty, but it is less deterministic and less complete than the specification’s proposed quantification pass.

Report validation also covers less than the prose requirements imply. It rejects unknown citations, but it does not require at least one source marker, prove that every material factual sentence is cited, or require the marker set to match `source_ids_used`. It checks two narrative fields for substance but does not deterministically verify every required article section. The single schema/transport retry described in the specification is not implemented as a general report retry.

The challenge and frozen-date evaluation coverage are modest. The tests prove that challenge and adjudication objects can travel through a run, but they do not currently demonstrate a successful end-to-end case where counterevidence removes or branches a load-bearing edge and changes the central case. The five evaluation batches are checked for metadata shape and dates; they are not executed and scored through the pipeline. Prompt-injection tests verify that the prompts label input as untrusted, but they do not perform a live adversarial model evaluation.

Other smaller gaps are visible. Failed grounded-search model calls are not recorded with the same detailed call artifact as successful calls. The health endpoint reports application and configured-credential state but does not probe Gemini, search, or a fresh database query. Warning counts are not maintained. Source de-duplication is limited to each research cycle rather than the complete run. There is no automatic backup or cleanup policy.

Continuous crawling, trading instructions, portfolio recommendations, user accounts, feedback-loop reasoning, vector search, open-ended multi-agent behavior, precise share-price targets, and a distributed job queue are deliberately not built. This overview supersedes the version dated 2026-08-23. The update pass cross-checked its claims against the executable package, its colocated explanations, root configuration, migrations, and cross-component tests. The documentation map now states the exact coverage boundary instead of implying that generated artifacts and every cross-component test have their own companion file. The project directory is still not a Git repository, so file-level change history could not be used to independently confirm what, if anything, changed in the code between passes.

## 10. Known Issues

A close per-file read of the codebase, done to produce a companion explanatory document for every source file, turned up one structural bug worth fixing before relying on multi-cycle research runs, one piece of dead code, and one fragile test assumption.

`apply_patch()` **cannot add or update an assumption or an estimate.** The four branches in `graph/__init__.py` that handle the `add_assumption`, `update_assumption`, `add_estimate`, and `update_estimate` patch operations (lines 100, 103, 106, and 109) import the model classes with `from .models import Assumption` / `from .models import Estimate` — a relative import that looks for a `models` submodule inside the `graph` package itself. No such module exists; `Assumption` and `Estimate` live in `consequence_radar/models/__init__.py`, one level up (`..models`), which is already how every other model class in this same file is imported. The result is not a validation failure but an unrelated `ModuleNotFoundError`, raised the instant a proposed patch contains one of those four operations. Because `graph_patcher.md` explicitly asks the model to produce exactly these operations whenever an assumption or estimate needs adding or revising, and because `pipeline/__init__.py` wraps every `apply_patch` call in a broad exception handler that treats any failure as an ordinary invalid patch and retries once, the crash is currently invisible in the run record: it is logged as an `invalid_graph_patch` artifact, one repair call is attempted, and if the repair also touches an assumption or estimate it fails the same way and the research cycle quietly proceeds with the graph unchanged for that cycle. The practical effect is that the pipeline can grow a graph's nodes and edges from research, but currently cannot durably add or amend the assumptions or estimates attached to them through the patch path, and nothing in the stored artifacts distinguishes this from an ordinary model mistake. The fix is mechanical — change the four imports to `from ..models import Assumption` / `from ..models import Estimate` — but it has not been made as of this writing.

`revise_graph()` **is dead code.** The same file defines a `revise_graph()` convenience function that applies a patch and builds the matching `GraphRevision` audit record, but nothing in the codebase calls it — `pipeline/__init__.py` reimplements the identical `GraphRevision`-construction logic inline in its own `_save_revision` method instead. It is safe to remove, or, if it is kept as the intended public entry point, `_save_revision` should call it directly so the two copies cannot drift apart.

**A test’s file-discovery assumption is easy to break again.** `tests/evaluation/test_frozen_fixtures.py::test_prompt_injection_fixture_is_explicitly_untrusted` globs every `.md` file under `src/consequence_radar/` and asserts each one mentions “untrusted” or “input is data”, on the assumption that every `.md` file there is an LLM prompt. That assumption broke, and the test failed, the moment a companion `<name>.<ext>.explained.md` documentation file was added next to each source file (including the ten prompt files themselves) as part of this same documentation pass, since those companion files also match `*.md`. The glob has since been narrowed to exclude `*.explained.md`, and the full suite passes again (69 tests as of 2026-08-24). Any future non-prompt `.md` content placed directly under `src/consequence_radar/` will need the same exclusion, or this test will fail for a reason unrelated to prompt-injection safety.

## 11. The Current State of the Project

Consequence Radar is a credible first working MVP and architectural proof, not yet a production research service. Its strongest quality is traceability: strict schemas, exact-passage checks, append-oriented artifacts, graph versions, explicit challenge records, and fail-closed report handling make it unusually easy to inspect how an answer was assembled. The framework boundaries are also clean enough that model, search, web, and test implementations can be replaced independently.

Its most fragile quality is the distance between local correctness and real analytical quality. The offline test suite is fast and passes, but most end-to-end intelligence is supplied by scripted fake responses. Live model behavior, grounded source quality, multi-cycle evidence accumulation, hard news pages, prompt attacks, and real newsletter reliability remain unproven. Quantification in particular is more of a guarded model instruction plus helper toolkit than a fully automated calculation engine.

Someone picking up the project should first understand that the graph and SQLite artifact ledger are the source of truth; the final article is only a rendering of accepted state. They should preserve the framework-neutral pipeline and local validation boundaries. Before calling the MVP production-ready, they should run and retain a credentialed smoke test, strengthen report and challenge acceptance checks, execute the frozen evaluation batches rather than merely validating their metadata, and connect deterministic estimate and sensitivity functions into the actual research pipeline.
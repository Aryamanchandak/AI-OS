# What If Analyser — Codebase Overview

Last updated: 2026-08-19  (Asia/Kolkata)

## 1. What This Project Is

What If Analyser is a decision-support web application for exploring the likely consequences of a proposed change. A person can type a situation such as “RBI cuts the repo rate by 50 basis points,” and the system researches the topic, builds and challenges a map of cause and effect, then shows how important outcomes change across four plausible versions of the future. Its central promise is not certainty; it is an inspectable chain of reasoning that makes sources, assumptions, disagreements, and fragile links visible.

## 2. The Big Picture — How It All Fits Together

The easiest way to picture the system is as a compact analyst team working along a fixed assembly line. A user hands the team a one-paragraph question. The first analyst decides what evidence should be sought, including evidence that could undermine the proposed story. A research desk searches the public web, opens usable pages, removes duplicate or unsafe addresses, extracts readable text, and ranks the results. A second analyst turns those pages into a ledger of individual claims, each tied to an exact passage in a named source.

That evidence ledger goes to a model builder. The builder creates a small cause-and-effect map: one starting intervention, a group of intermediate effects, three to five outcomes that matter, and exactly two unresolved yes-or-no questions. The map is deliberately constrained to 8–15 items and at most three causal steps from the starting intervention, so it remains understandable on one screen. Every connection says whether the effect moves in the same or opposite direction, how strong it is believed to be, why it occurs, how long it may take, what conditions apply, and whether research supports it.

The first map is treated as a draft. The application selects one skeptical viewpoint using a transparent rule: policy questions receive a contrarian critic, numerical questions with evidence receive an evidence critic, and other questions receive a causal-logic critic. That critic gets one pass to identify material weaknesses. A separate adjudicator then gets one pass to accept, reject, or respond to those objections and produce the final map. The process stops there. It is a bounded editorial review, not an open-ended conversation among artificial agents, so its cost and duration remain reasonably predictable. The system also records exactly which connections changed between the draft and final maps.

The two unresolved questions act like two switches. Each switch can be on or off, producing four combinations. For each combination, the application resolves the map using local arithmetic rather than asking an AI model to invent the result. The starting intervention is treated as occurring, the two switches fix the direction of their associated factors, and effects are carried forward through the map. Stronger links have more influence than weaker ones, effects fade with causal distance, and opposing forces are marked as contested. This deterministic calculation is the project’s most important architectural choice: the same map and switch settings always give the same result, can be rerun instantly, and leave a readable trail of how each outcome was reached.

Before presenting the answer, the system stress-tests the map one connection at a time. It reverses each connection, reruns all four futures, and notices which reversals actually change an outcome. It then spends one evidence-checking model call only on up to six of these load-bearing connections. This distinguishes links that truly support the conclusion from plausible-looking details that do not affect it. Finally, four AI calls run at the same time to turn the already-calculated outcomes into short analyst notes. Those notes describe what happens, identify the largest driver, and state what observation would prove the scenario wrong; they do not decide the outcome directions themselves.

Around this engine is a current web interface and an older alternative interface. The current interface is a conventional browser page served by a small Python web server. Because a full run involves web searches and several model calls, submitting a question creates a background job rather than making the browser wait on one long request. The browser receives a stream of progress messages, then asks for the finished result. It displays a four-scenario comparison, short narratives, sources and claims, the critic’s findings, the before-and-after graph changes, a visual causal map, detailed audit tables, and the structural sensitivity check. The older Streamlit interface calls the same engine and remains available for comparison, but it is no longer the primary experience.

The application has no database, user accounts, or durable storage. Jobs and the most recent successful result live only in the running server’s memory. This keeps setup simple and ensures a failed new run does not erase the last good answer, but everything disappears when the server restarts and the design is intended for a trusted, single-process environment rather than a public multi-user service.

## 3. Every Component — What It Does and Why It Exists

### The shared vocabulary

`engine/schema.py` defines the shapes of everything passed through the application: research plans, sources, evidence claims, graph items and connections, uncertainties, criticisms, adjudication records, and graph differences. It also defines strict answer forms for Gemini, which means the model is asked to fill in named fields rather than return prose that the application must guess how to parse. This file contains almost no behavior, but every stage depends on its shared language; without it, the research, graph, calculation, and display layers could easily disagree about what an analysis contains.

### Research and evidence

`engine/research.py` is the research desk. Gemini first proposes a bounded set of searches, while local rules ensure skeptical searches are included. The application then uses DuckDuckGo’s public HTML results, fetches pages in parallel, refuses local or private network destinations, accepts only readable web text, strips page furniture, removes duplicates and tracking details, and ranks sources with simple, visible rules. Quick mode keeps up to 20 usable sources and Deep mode up to 40.

The same component sends sources to Gemini in groups of ten to produce the evidence ledger. Crucially, a claimed quotation is retained only if its passage can be found in the fetched source text after whitespace is normalized. This does not establish that every claim is true, but it prevents an invented quotation from quietly masquerading as source evidence. If research fails, the pipeline records the failure and continues from the user’s brief alone.

### Causal-map construction

`engine/extract.py` turns the brief and evidence ledger into the first causal map. Gemini builds the entire small map in one view, which helps it avoid duplicate concepts and disconnected fragments. The application then independently checks the map’s size, its single starting point, its leaf outcomes, all connection endpoints, direction values, absence of circular logic, maximum depth, and the usefulness of both uncertainties. If the first map violates those rules, Gemini receives the exact problems and gets one retry. If that also fails, the run ends rather than displaying a malformed model.

### Challenge, repair, and verification

`engine/debate.py` supplies the editorial challenge. It selects a critic, asks for specific objections to existing relationships, lets an adjudicator repair the map once, and validates the repaired map again. It also computes a plain record of added, removed, or altered relationships and checks the evidence behind the few connections that sensitivity testing says matter most. If criticism or adjudication fails, the original builder map remains visible with a warning. If evidence verification fails, all connection labels are reset to “unverified” so partial or inherited guesses are not presented as completed verification.

### Deterministic scenario engine

`engine/propagate.py` is the mathematical heart of the product. It copies the final graph for each scenario, applies the intervention and uncertainty settings, and walks forward only after all earlier causes have been resolved. Connection strength determines voting influence; causal distance reduces magnitude; equal or mixed opposing pushes become contested; and every item records the incoming mechanisms that produced its state. This part uses no model, network, or file access. Removing it would turn the product into four independent pieces of generated prose rather than four comparable results from one shared model.

`engine/sensitivity.py` repeatedly uses that inexpensive calculator to discover which exact links are load-bearing. `engine/synth.py` then converts each resolved scenario into a tightly constrained three-sentence explanation. The four explanations are generated concurrently, but only after the numerical directions and magnitudes have been fixed.

### Orchestration and presentation

`engine/pipeline.py` is the conductor. It validates the input, calls every stage in the fixed order, reports progress, distinguishes recoverable failures from fatal ones, and returns one complete package containing both intermediate evidence and final scenarios. It deliberately knows nothing about FastAPI or Streamlit, allowing either interface to use identical analysis behavior.

`engine/presentation.py` is a supporting translation layer. It creates the four switch combinations and readable scenario names, translates outcome states into arrows or a contested symbol, prepares sensitivity tables, and describes the causal map in a browser-renderable diagram format. Centralizing this work keeps the two interfaces visually consistent.

### Current and legacy interfaces

`web/app.py` is the current server. It exposes the page, starts analysis jobs, streams progress, and returns completed result fragments. A four-thread worker pool performs analyses, while a lock protects a small in-memory job register. The templates in `web/templates/` define the form and comprehensive results page. `web/static/app.js` submits jobs, follows their progress stream, swaps in the finished result, and invokes the bundled diagram renderer. The stylesheet provides a responsive two-panel design, accessible focus behavior, reduced-motion handling, and compact layouts for smaller screens.

`legacy/main.py` is a large older Streamlit presentation shell. It is still runnable and uses the same shared pipeline, but it duplicates a considerable amount of visual work and exists mainly as a fallback or comparison point. Tests exercise the deterministic calculation, cross-stage contracts, and failure behavior with local fixtures and fake model clients. The documents folder contains the original product specification, later release plans, UI plans, third-party notices, and a more technical workflow guide; these describe intent and history, but the running code is the source of truth.

## 4. How a Typical Interaction Works

A user opens the page, types one intervention or external change, chooses Quick or Deep research, and presses “Build scenario map.” The browser validates that something was entered and sends it to the server. The server validates it again, limits it to 4,000 characters, creates a unique job, and immediately returns the job identity. The previous completed analysis, if one exists, remains on screen in a faded state.

The browser opens a progress stream. Behind the scenes a worker plans research, searches and ranks sources, extracts traceable claims, builds the draft map, selects and runs a critic, adjudicates once, identifies and verifies consequential links, resolves the four futures, and requests four short narratives. Each stage adds a message to the job, and the browser adds those messages to the progress panel.

When every required stage succeeds, the job becomes complete and atomically replaces the server’s “last completed” result. The browser fetches the rendered analysis and shows the outcome matrix first, followed by scenario notes, evidence, debate, the causal map, and sensitivity details. If the new run fails during graph building or narrative writing, the browser reports the error and the earlier successful analysis remains available. Research, debate, and verification failures are handled inside a successful run with visible warnings and conservative fallbacks.

The legacy journey is similar, except Streamlit directly runs the synchronous pipeline and reports progress inside its own page session rather than using background HTTP jobs and a progress stream.

## 5. How the System Makes Decisions

Research depth controls bounded effort rather than a different reasoning method. Quick mode allows up to six search queries, 20 fetched sources, and normally two claim-extraction batches. Deep allows up to twelve queries, 40 sources, and normally four claim batches. Both use the same graph builder and exactly one critic.

During retrieval, addresses that do not point to a public web destination are rejected, unreadable or very short pages are discarded, duplicates are collapsed, and remaining pages are ranked by subject overlap, a small authority-domain list, and a publication date only when one is explicit in the address. No date is guessed from article prose. Claims survive only when they name a supplied source and include a passage actually present in its fetched text.

The brief’s language chooses the critic. Policy and regulatory terms choose a contrarian lens; a quantitative brief with retrieved claims chooses an evidence lens; everything else uses a causal-logic lens. Criticism is not automatically accepted: the adjudicator may accept, change, reject, or leave a concern unresolved, after which the process must stop.

Within a scenario, each non-fixed item receives signed pushes from its parents. Strong connections count more than medium or weak ones. A positive total means upward movement, a negative total means downward movement, and a tie means neutral; any real mixture of positive and negative pushes is also marked contested. Size is based on the strongest incoming connection and fades with each additional step from the intervention. Sensitivity testing chooses verification targets only when reversing a link changes at least one outcome, favoring links that affect more scenarios and more outcomes.

## 6. How the Code Actually Flows — The Execution Journey

The primary entry point is the web server command described in the README. Importing the web application loads local environment settings, locates its templates and static files, creates the web server object, initializes an empty job register, and creates four worker threads. It does not contact Gemini or the web at startup. The initial page request reads the latest completed in-memory result, if there is one, and renders the form.

An analysis begins at the submission endpoint. After input checks, control passes to a worker thread and the request finishes quickly. The worker calls the framework-neutral pipeline with a small progress callback. Research planning enters Gemini; the resulting queries fan out into concurrent DuckDuckGo searches, then concurrent page fetches. The streams rejoin into a ranked source list. Source batches fan out again into parallel claim-extraction calls and rejoin as one numbered ledger.

Control next passes serially through graph construction, local validation, critic selection, criticism, adjudication, and another validation. Local comparison records how adjudication changed the draft. The pipeline generates the four uncertainty assignments and repeatedly invokes the deterministic calculator while flipping one connection at a time. Those results rejoin as a ranked list of consequential links, which is sent in one batch for evidence checking.

The final graph then flows through the calculator four times, once per assignment. Each copy accumulates resolved states and traces without changing the shared graph. The four completed graphs fan out to four narrative requests and rejoin in the same stable order. The pipeline returns a single analysis package to the worker, which marks the job complete and stores it as both that job’s result and the server’s latest successful result.

Meanwhile, the browser’s progress connection repeatedly waits for new events in the job record, pausing briefly between checks. After the completion event, it requests the HTML result fragment. Server-side presentation helpers prepare tables and the causal-diagram description, the template safely renders model-generated text as content, and browser JavaScript converts the diagram description into a visual. If rendering fails, the raw diagram description remains available as a fallback.

On a clean server shutdown, queued worker work is cancelled where possible and worker threads are released without waiting indefinitely. No result is written to disk. Closing a browser’s progress stream does not cancel its running analysis; the server job continues until completion or failure.

A secondary entry point starts the legacy Streamlit page, which initializes a page session and directly calls the same pipeline when its button is pressed. A small command-line path in the graph builder can also create and print a map for one supplied situation, mainly as a developer smoke test. The three test files can run directly as offline self-check programs.

## 7. What the System Remembers

During a run, the system remembers the user’s brief, research mode, progress events, status, final result, and error message in a job record. It keeps at most roughly 20 finished job records while never trimming work that is still running. It also remembers one shared “last completed” analysis so a failed or in-progress replacement does not blank the screen. Access is guarded against simultaneous worker updates, but this memory belongs to one server process and vanishes on restart.

The completed analysis itself contains unusually rich temporary memory: the search plan, fetched sources and their cleaned text, the evidence ledger, the draft and repaired graphs, criticism and adjudication, graph differences, verification status, all four assignments and resolved graph copies, sensitivity impacts, and narratives. None is persisted. The browser separately remembers only the active progress connection and whatever result HTML is currently on the page; refreshing asks the server for its latest completed in-memory result.

Secrets are not part of an analysis. The Gemini key is read from environment settings or a locally ignored `.env` file. If it is missing, the page warns the user and model-dependent analysis cannot complete.

## 8. What the System Talks To

The main external dependency is Google’s Gemini service, currently using the Gemini 2.5 Flash model. It plans searches, extracts claims, builds the graph, critiques and adjudicates it, verifies consequential edges, and writes four narratives. A missing key, outage, quota problem, or invalid structured response may degrade research, debate, or verification, but graph construction and final narratives are required for a complete run.

The research layer talks to DuckDuckGo’s public HTML search page and then directly to the public pages returned by it. Search and fetch failures are tolerated when possible; if no usable sources remain, the graph is built from the brief alone and clearly marked as ungrounded. Because this is HTML retrieval rather than a contracted search API, page changes, bot protection, paywalls, and script-heavy sites can reduce reliability.

The browser downloads two Google-hosted fonts, so typography may fall back when that network request is unavailable. The causal diagram renderer itself is stored locally and requires no external content network or server-side Graphviz installation. The application otherwise talks to the local filesystem only to load environment settings, templates, JavaScript, CSS, and documentation. It has no database, calendar, cloud storage, messaging service, authentication provider, or analytics service.

## 9. What Is Currently Built vs. What Is Not Yet Built

The working product includes bounded web research, counterevidence planning, deterministic source ranking, exact-passage claim checks, evidence-aware graph construction, strong graph validation, one critic and one adjudication round, visible graph differences, exact-edge sensitivity, selective evidence verification, four deterministic scenarios, parallel narrative generation, a responsive FastAPI interface, streamed progress, graceful handling of several partial failures, and a retained legacy interface.

Offline checks are healthy: all 19 standalone checks across propagation, pipeline contracts, and failure behavior passed on this review. The web application also imports successfully and exposes its expected routes. The environment does not contain the optional `pytest` package, so the full suite could not be collected with that runner, and no live Gemini-and-web end-to-end run was attempted; external integration quality therefore remains unverified here.

Several ideas in the planning documents are not implemented. There is no saved analysis library, user identity or access control, cancellation, durable queue, version history, collaborative editing, conversational follow-up, direct graph editing, approval and rollback workflow, scheduled research refresh, notifications, uploaded-document research, multiple search providers, recommendations or action plans, monitoring thresholds, live uncertainty controls, downloadable board brief, or side-by-side version comparison. Time lags and conditions are displayed metadata but do not alter propagation. Quick and Deep change research breadth, not critic count or model quality. The larger “Scenario Intelligence,” “Interactive Analyst,” and “Living Intelligence” releases remain plans rather than current behavior.

No prior overview existed to reconcile on this run. The empty package marker files are intentional rather than unfinished features. `docs/notes.md` contains no meaningful content, while the larger planning files describe many deferred ambitions and should not be mistaken for a list of shipped capabilities.

## 10. The Current State of the Project

This is a strong functional prototype or early internal product, not merely a proof-of-concept script. Its best feature is the separation between AI judgment and deterministic calculation: models propose evidence, structure, criticism, and prose, while a small auditable engine resolves the scenarios and stress-tests the links. Its failure behavior is also unusually honest for this stage, preserving prior results and visibly downgrading claims rather than hiding missing research or verification.

The fragile side is production operation and empirical accuracy. Results depend on one external model and an unofficial HTML search path; source scoring is deliberately simple; AI-created causal maps can still be conceptually wrong even when structurally valid; and there is no saved history, access control, rate limiting, cancellation, or multi-process coordination. In-memory job limits do not prevent an unbounded queue of newly submitted work. A new maintainer should preserve the deterministic core and the one-round boundary, treat the planning documents as aspirations, and decide whether the next priority is evaluation of analytical quality or hardening for multi-user deployment before adding more intelligence features.

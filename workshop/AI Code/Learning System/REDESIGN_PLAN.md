# Study System — Clean Redesign Plan (v3)

**Written:** 2026-07-08 · **Revised:** 2026-07-09
**File history:** `REDESIGN_PLAN_v1_original.md` → `REDESIGN_PLAN_v1_annotated.md` → v2 (`REDESIGN_PLAN_v2_annotated.md`) → this file. Every prior open question is either DECIDED below or explicitly still OPEN — nothing is silently resolved.
**Companion doc:** `INTEGRATION_REQUIREMENTS.md` — everything that needs to change in `knowledge-graph` / `vector-db` / shared SQLite / `llm_gateway`. This file is study-system's own scope only.

[THE ISSUES I AM FACING WITH THIS CODE HAS MADE ONE THING VERY CLEAR O EM THE DATABSE FOLDER STURCTURE IS NOT IDEAL, INGESTION SHOULD LIVE IN A DIFFERENT FOLDER, THE RAW DATA IN A DIFFERENT FODLER, AND STORED OPTIMISED VERSION, THE SQL LITE TABLES KGS AND VECDB IN A SINGLE DIFFERENT FOLDER, WITH SUB FOLDER APPROPRAITELY NAMED./  

THIS INGESTION IN THE SAME FOLDER WHEE YOU ARE STORING IS NOT WORKING]


---

## 0. What study-system actually is, now that the fork is resolved

**Confirmed:** the KG and vector-db hold the source material and its relationships. study-system holds only what doesn't exist anywhere else — the testable card, its FSRS schedule, your review history, your mastery per topic. Nothing about the mechanism is CFA-specific; it happens to be used for CFA right now [study system own it and can only be written by study system, thats fine, but dont you think you should store in in the AI Code/Database folder in a specific folder ? as that can be the main root database ? and one backup stores all my info and all I need to do is pull info from the same place instead of having to remember this, other systems can also pull it accordingly.].

**Confirmed generation mechanism:** study-system does **not** run its own independent extraction pass over raw vault text. Per concept: pull its KG neighborhood (Cypher, via `kg_neighbors`/`kg_edges_for_node`) + relevant vector-db chunks (`vector_db_search`), one LLM call turns that into atomic facts + cards, result is **cached locally** so review stays cheap (the original "pay once, generate forever" principle — the "once" is now per-concept-from-retrieval, not per-file-from-raw-text).

**Confirmed topics-list mechanism:** study-system doesn't discover topics live via ad-hoc queries, and doesn't hardcode a syllabus either. Per your correction: after each ingest → KG-run → vector-run cycle, study-system calls the new `kg_list_concepts(domain=...)` (see `INTEGRATION_REQUIREMENTS.md` §1.2) and mirrors `{kg_node_id, name, domain}` into a small local table. That local mirror **is** the topics list — cheap, always on hand, no live Cypher needed just to know what exists.

[ARE WE HAVING A FILE THAT CHECKS IF A NODE ALREADY EXISTS, HOW DO WE MAKE SURE WE DONT END UP DUPLICATING THE NODE ? ANDI SI THIS REALLY THE BEST WAY TO GO ABOUT THIS ?? TO GO ABOUT TOPIC EXTRACTION ? WHEN I AM DOING TRIPLET EXTRACTION SHOUDL I NOT ALSO EXTRACT THE TOPIC OR DOMAIN THIS ALL FALLS UNDWER, BUT FOR THAT DONT YOU NEED A PRETTY EXTENSIVE LIST OF POSSIBLE DOMAINS AND SUB DOMAINS SO AI DOESNT OCME UP WITH ITS OWN DOMAIN ? CAN THIS BE FOUND ON THE WEB ? ]

**Confirmed physical storage location:** study-system's SQLite file lives at `Database/study-system/study_system.db` — **not** inside this repo. This repo is code only. (`INTEGRATION_REQUIREMENTS.md` §3.2.)

[NO IT SHOUD LIVE UNDER DATABASE/SQLLITE/STUDY_SYSTEM/STUDY_SYSTEM.DB] [[THIS BUILDS ON THE COMMENT I LEFT ABOVE]]

**Corrected scope — the concept-bridge/abbreviation UI is NOT study-system's.** It's an ingestion-time review tool (fix spelling, map "DUR"→"Duration") that sits on top of the KG + vector-db, used for every capture regardless of downstream project. Moved entirely to `INTEGRATION_REQUIREMENTS.md` §1.4. Removed from this plan. [IS A DIFFERENT COMPONENET, YOU DONJT NEED TO WORRY ABOUT IT, HOW WE INGEST IS NOT YOUR PROBLEM, YOU ARENT AN INGESTER NOR ARE YOU STORAGE, YOU ARE SIMPLY THE CODE WRAPPER YOU ARE WHAT WE COME TO FOR A FEYNMAN EXPLAINER, OR AN ARS REVIEW TO BE RUN AND STORED, AND WHOLE BUNCH OF OTHER REALLY IMPORTANT THINGS, DONT CONFLATE THE 2, AS THAT MAKES IT SOO MUCH HARDER TO WORK WITH]

**Corrected scope — Feynman/challenger UI.** A frontend already exists (FastAPI + HTML chat interface) that this connects to — study-system does not build UI for this. Only a clear interaction-contract list is needed (§4).[NO A UI EXISTS, BUT DOES IT EXIST FOR YOUR USE CASE THATS WHAT YOU SHOULD ANSWERR, WHEN YOU ARE USING A FEYNMAN OR A CHALLENGER OR STUDY SYSTEM IS CREATING FLASHCARD, DOES IT EXIST FOR THTA ? AND IF IT DOESNT THEN THATS WHAT WE NEED TO CREATE]

**Corrected scope — Planner/exam-priority.** Parked. The existing "Planner" project only sets calendar/reminder items today; the exam-focus behavior isn't built there yet, so there's nothing to integrate against right now. Not pursued until that exists. [YOU KNOW WHAT LETS PURSUE THIS AS ITS NEEDED AND VERY MUCH REQUIRED AND VERY MUCH THE NEED OF THE HOUR, LETS GET IT STARTED]

---

## 1. The mental model (current) [NOT READING THIS HAVE LEFT COMMENTS ABOVE DONT THINK ITS REPRESENTTATIVE OF THAT SO NOT GOING TO BOTHER]

```
┌───────────────────────────────────────────────────────────────┐
│  SHARED INFRASTRUCTURE (AI Code/) — used, never duplicated     │
│                                                                 │
│  llm_gateway      HTTP @ localhost:8107 — ALL LLM calls,        │
│                   usage logged to learning_systems_usage        │
│  Raw Data/ledger  capture() → immutable bronze + dedupe         │
│  knowledge-graph  Neo4j — triplets FROM bronze; domain tags;    │
│                   list-by-domain, read-by-source; ingestion     │
│                   review UI for abbreviations/spelling          │
│  vector-db        Chroma+Ollama — chunks/embeds FROM bronze     │
│                                                                 │
│  MCP surface: capture_raw_data, kg_search_concepts,             │
│  kg_neighbors, kg_reachable, kg_edges_for_node, kg_list_concepts│
│  (new), kg_concepts_for_source (new), vector_db_search/get      │
└───────────────────────────────────────────────────────────────┘
              ▲ capture bronze (+ domain metadata)   ▲ query per concept
              │                                       │
┌───────────────────────────────────────────────────────────────┐
│  STUDY SYSTEM (code only — data lives in Database/study-system/)│
│                                                                 │
│  Local mirror: concepts (kg_node_id, name, domain) — the        │
│    topics list, synced after each ingest cycle                  │
│  Generated + cached: atomic_facts, cards                        │
│  Learning state: FSRS, reviews, concept_mastery, calibration     │
│                                                                 │
│  Explicitly NOT here: triplets, embeddings, bronze, abbreviation │
│  correction, quiz/spend logging (→ shared DBs), any UI for       │
│  Feynman/challenger (→ existing chat frontend)                  │
└───────────────────────────────────────────────────────────────┘
```

---

## 2. Tomorrow, concretely: "live" = one generated HTML file

Unchanged from before, confirmed:

- **`study generate-deck`** — queries due cards, writes one self-contained `deck.html`. No server, no network dependency. [FOR THIS YOU NEED A SIMPLE I THINK ITS A .SH FILE, A FILE WHICH WHEN I PASTE IN THE TERMINAL CALL SOME HOW, WHATEVER WAY, ITS STARTS A SEQUENCE OF THINGS THATS GOES TICK TICK TICK TICK TICK, AND THEN I GET THE FLASHCARDS AUTOMAITCALLY IN THE OUTPUT FOLDER, FOR NOW THATS HOW IT SHOULD WORK. THE FLASHCARDS NEED TO BE STARTED AS T HE LEVEL OF 1-000 FLASHACRADS BEFORE SRS IS A LONG TIME AWAY. WHAT I IDEALLY WANT IS LIKE A FULL BLOWN APPLICATION WITH BUTTONS, I CLICK IT STUDY SYTEM IS A GO, BUT YOU WANT IT TO BE AGENTIC SO ITS ALWAYS ON THE READY OR THINGS LIKE FEYNMAN AND CHALLENGER AS THEY ARE YOU SAY THINGS THAT CAN BE CREATED A MCP TOOL OF, but there are soo many things like making flashcard, what if one day I want more than 5 flashcards, I should have the ability to click and generate more than 5 sets of flashcard, yes soon to make this fullye agentic I want to be able to do thsi with message s but for right now and always. has to also be possible via clickling a digital button]
- **New addition (your ask):** a **focus picker** in the deck-generation step — either a free-text vague focus area ("more on fixed income today") or a structured pick of topics/books/sources drawn from the local `concepts` mirror table's metadata, scoping which concepts get included in that day's deck. [YES WELL THATS THE THING, THIS SI WHERE SRS IS USEFUL AS I DONT WANT TO HAVE TO DECIDE THIS, YOU REMOVE HUMAN FRICTION DONT GIVE THEM A CHOICE TO DO THIS AT ALL, YOU GENERATE THE TOPICS YOURSELF, WITH AN EYE ON THE FUTURE AND THE CALENDER IDEALLY. I GUESS LETS STARTING WORKING TOWARDS THIS, MIGHT AS WELL WHATS THE HARM, THIS WILL TOUCH A LOT OF OTHER THINGS BUT WILL BE WORTH IT. THIS SHOULD HAPPEN AUTONOMSLY EVEN WHEN THE SRS IS NTOT WORKING THATS THE THING, THATS WHY I THINK THERES A BENEFIT TO HAVING SRS FROM 0 START EVERY TOPIC FROM 0 EVERYDAY PICK 5 AND GIVE ME 5 FLASHCARDS, THEN RANK THEM, HARDLY THINK YOU CAN GET LOWER THEN 0 THEN THE NEXT DAY PICK ANOTHER 5 AND ANOTHER 5 AND BUILD U- WHT ESCORES THSI WAY YOU WONT HAVE TO WAIT FOR A 1000 REVIEWS, YOU WILL CUT OUT MY FRICTION AND BY THE SIMPLE CURVE OF LEARNING, YOU WILL CONTINOUSLY HAVE LOTS OF TOPICS TO REVIEW, OF COURSE DELAY OF A TOPIC MIGHT NOT WORKL, A TOPIC WITH AN IMMEDIATE SCORE OF 80 WILL STRUGGLE TO BE RELEVANT AND MAY NOT BAE ASKED ABOUT, BUT AGAINT HTATS SOMETHING I CAN SOLVE FOR]
- **Tracking:** JS in the page captures taps (rating or MCQ choice) into an in-page array. **What it cannot do is silently write back to your Mac** — there's always one transport step.
  - **For now:** end-of-session "copy results" / `mailto:` blob → you send/paste it → `study import-results` on the Mac parses it through the same `scheduler.rate()`/`record_review()` code the CLI review already uses. Manual, on purpose — confirmed not to build Gmail-MCP auto-processing yet (§7 TODO). [WE CAN IF REQUIRED, I DONT SEE IT TAKING A LONF TIME.]
  - **Delivery direction (confirmed plan, not built yet):** drop `deck.html` into an iCloud-Drive-synced folder instead of emailing it — zero server, zero email, shows up in Files on your phone. Planned approach; §7 TODO for when we get to it. [AGAIN A GOOD IDEA BUT AS WITH THE GAMIL, YOU HAVE TO ABSOLUTELY HAVE TO HAVE A SANDBOX IN PLACE.]
- **Grounding check: confirmed important, build it.** Reuses `quality.py`'s existing pattern — cheap model (gpt-4o-mini), and batch multiple facts into one call rather than one call per fact.

- [ ] `study generate-deck` (+ focus picker)
- [ ] in-page session tracker + end-of-session export
- [ ] `study import-results`
- [ ] grounding check extended to atomic facts, batched, cheap model
- **Done when:** you generate a deck (optionally scoped to a focus topic), review 10 real cards on your phone, send the results blob, run `import-results`, and `reviews` + FSRS `next_due_at` update correctly.

---

## 3. Build phase

### 3.1 Foundation
- [ ] Symlink `AI Code/.env` into the repo. Add `LLM_GATEWAY_URL`.
- [ ] `core/clients.py` → thin wrapper over `llm_gateway.client.LLM`. Delete direct SDK calls.
- [ ] Fix migration path bug (`bootstrap_db.py`/`migrate.py`: `.parent` → `.parent.parent`); one command runs all migrations.
- [ ] `SQLITE_PATH` points at `Database/study-system/study_system.db`, not a path inside this repo.
- [ ] No cost-ceiling enforcement (confirmed not a near-term concern).

### 3.2 Local topics mirror + generation (replaces the old "extractor.py" design entirely)
- [ ] After each ingest cycle (capture → KG run → vector run), call `kg_list_concepts(domain=...)` and upsert into a local `concepts` table: `kg_node_id, name, domain, first_seen_at`.
- [ ] **New `concept_gen.py`**: given a concept from that local table, pull `kg_neighbors`/`kg_edges_for_node` + `vector_db_search(query=name, where={"domain": ...})`, one LLM call → atomic facts (+ optionally cards directly). Cache result in local `atomic_facts` / `cards` tables.
- [ ] `atomic_facts` table: `id, concept_id FK, kg_node_id, text, source_chunk_ref, created_at`. (No verbatim source duplication beyond the distilled claim — grounding provenance is a reference, not a copy, since vector-db already holds the verbatim chunk.)
- [ ] Grounding check on each atomic fact before it can spawn a card (§2).
- [ ] **Delete entirely** (not "kept thin"): `extraction/extractor.py`'s old per-file extraction, `kg/kg_store.py`, `vector/vector_store.py`, `ingestion/vault_manifest.py`'s semantic-hash machinery, any local triplet code.

### 3.3 Feed the shared KG + vector-db
- [ ] Capture each vault file as bronze: `capture_raw_data(source="note", content=<file text>, metadata={"domain": <your domain tag>})`.
- [ ] Chain the existing consumers: run `knowledge_graph.run` then `vector_db.run` (or in parallel) — you've already built both; this is a small orchestration script, not new integration code.

### 3.4 FSRS retraining
- [ ] Write the actual gradient-based FSRS-4.5 weight-fitting step now (minimize log-loss over `(stability, difficulty, elapsed_days, rating)` from `reviews`).
- [ ] Keep the existing trigger gate (1000 reviews / 8 months) — confirmed fine, you don't want it firing daily.

### 3.5 Smoke test
```
study ingest --vault-subset src/study_system/tests/fixtures/vault_small/
# (capture -> KG run -> vector run -> mirror concepts -> generate for one concept)
study generate-deck
# review on phone, send results back, study import-results
```

---

## 4. Feynman / challenger — interaction contract only, no UI

You already have a frontend (FastAPI + HTML chat) to connect this to. What study-system needs to hand it:

- **Feynman mode:** input = `{concept_id, your free-text explanation}`. Output = `{grading, gaps: [atomic_fact_ids not covered or misstated]}`, sourced from `feynman_evaluator_v1.md` against that concept's cached atomic facts. Feeds `concept_mastery`.
- **Challenger mode:** input = `{concept_id}`. Output = a generated edge-case question (`challenger_v1.md`) + your answer + grading, same shape as above.
- [ ] Write these as plain callable functions (`review/feynman.py`, `review/challenger.py`) with no I/O beyond the DB — the existing chat frontend calls them directly, or they become MCP tools later (§7).

---

## 5. Data contracts

| Data | Lives in | Notes |
|---|---|---|
| `concepts` (mirror) | `Database/study-system/` | `{kg_node_id, name, domain, first_seen_at}` — synced from `kg_list_concepts`, not independently extracted |
| `atomic_facts`, `cards` | `Database/study-system/` | generated per-concept from KG+vector retrieval, cached |
| FSRS state, `reviews` | `Database/study-system/` | the learning-engine state |
| `concept_mastery`, calibration | `Database/study-system/` | squarely this system's job |
| Quiz sessions/attempts | shared SQLite, `learning_systems_*` tables | `INTEGRATION_REQUIREMENTS.md` §3.1 |
| LLM spend/usage | `llm_gateway`'s own DB, `learning_systems_usage` | `INTEGRATION_REQUIREMENTS.md` §4.1 |
| Triplets | Neo4j | never touched directly by study-system |
| Embeddings/chunks | ChromaDB | never touched directly by study-system |
| Abbreviation/spelling corrections | KG/vector-db ingestion layer | not study-system's — `INTEGRATION_REQUIREMENTS.md` §1.4 |

---

## 6. Decisions confirmed

1. Env: symlink `AI Code/.env`.
2. No cost-ceiling enforcement.
3. Generation: query KG+vecdb per concept, one LLM call, cache locally. **Confirmed.**
4. Topics list: mirror `kg_list_concepts(domain)` output into local SQLite after each ingest cycle. **Confirmed.**
5. Phone: local-only, static HTML, manual email/paste sync for now; synced-folder delivery planned but not built yet.
6. Storage: all study-system data physically in `Database/study-system/`, not this repo.
7. Concept-bridge/abbreviation UI: not study-system's — belongs to the ingestion layer.
8. Feynman/challenger: interaction contract only; existing chat frontend handles UI.
9. Planner/exam-priority integration: parked (that project doesn't have the needed capability yet).
10. Gmail-MCP auto-processing of results: parked, not built now.

## 7. TODO — parked, with an owner

- **Gmail MCP auto-processing of `import-results`** — parked per your instruction; do the manual path first.
- **Synced-folder delivery of `deck.html`** — the agreed direction, just not built yet.
- **Source staleness detection** — real open problem, not solved. See `INTEGRATION_REQUIREMENTS.md` §5.
- **Feynman/challenger as MCP tools** — worth exploring once the interaction contract (§4) exists.
- **Planner exam-priority integration** — once that capability exists in the Planner project.
- **Real conversational chat**, **briefing mode + planner**, **feedback propagation**, **docs rewrite**, **stale top-level tests** — unchanged from before, still parked.

---

## The one-paragraph version

study-system is a thin learning engine: it mirrors which concepts exist from the KG (`kg_list_concepts`, domain-scoped), generates atomic facts + cards on demand per concept by querying the KG's neighborhood and vector-db's chunks in one LLM call, caches that result locally, and owns only what nothing else can hold — the card, its FSRS schedule, your review history, your mastery. All of it — including its own SQLite file — lives under `Database/study-system/`, not in this repo. Tomorrow's "live" is `study generate-deck`: one self-contained HTML file, tap-to-rate on your phone, one end-of-session export syncs ratings back via `study import-results` — no server. Everything ingestion-side (abbreviation correction, domain tagging, source-listing) is now `INTEGRATION_REQUIREMENTS.md`'s problem to hand to the other repos, not this plan's.

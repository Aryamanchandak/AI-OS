# Graphiti — Integration Plan

Oct 16, 2026 · Plan only, nothing here has been executed except Step 0.

This plan turns three earlier documents into ordered steps:

- the Graphiti Capabilities and Local Deployment Reference
- the Knowledge Layer Graphiti Migration Plan
- the Ingestion 2 Decision Register

Each step is one session and has its own definition of done (what "correct" looks like) and the list of files it touches. Claude asks for your definition of done at the start of each step and waits for your OK before running anything.

## Glossary (new terms only)


| Term             | Plain meaning                                                                             |
| ---------------- | ----------------------------------------------------------------------------------------- |
| Adapter          | One file that wraps a library, so nothing else in the code imports that library directly. |
| Spike            | A short, throwaway experiment that answers one question before you commit to building.    |
| Leaf project     | A separate folder with its own dependencies. Deleting it can't break the trunk.           |
| Plug-in (client) | A small class you hand to Graphiti so it calls *your* endpoint instead of OpenAI's.       |
| Pinned version   | The exact library version recorded in the lock file, so installs are repeatable.          |
| Telemetry        | Usage pings a library sends home. Graphiti sends one at start-up unless you turn it off.  |
| RRF              | Reciprocal Rank Fusion: merges several search result lists without calling an LLM.        |
| Go/no-go gate    | The point where results decide whether you continue or stop.                              |




## What we found while reading the code

1. **The gateway is not OpenAI-shaped.**
  - It serves `POST /api/llm/chat` and `POST /api/llm/embed`, using its own request format.
  - Chat already supports strict JSON-schema output, which Graphiti needs.
  - Embed returns 768 numbers per text, from `nomic-embed-text` in Ollama, and takes one text per call. [WHAT DOES GRAPHITI NEED VECTOR EMBEDDINGS??] 
  - There is no `/v1/chat/completions` route, so Graphiti's stock OpenAI client can't point at it. [OVERALL TELL ME WHAT IS REQUIRED HERE, I AM REMAKING A SIMPLIFIED GATEWAY, SO I WILL INCLUDE THIS THERE SO] 
  - This answers Decision Register D2, and the answer is "no".
2. **Chosen fix: Option A, a Graphiti adapter outside the gateway.** It plugs in three small classes (LLM, embedder, reranker) that call the gateway's existing routes. In CLAUDE.md's escalation order this is step 2, "official extension points", and it needs no trunk change. Rejected for now: [HERE GIVE ME ALL THE INFORMATION NEEDED FOR WHAT GRAPHITI EXXPECTS FROM THE GATEWAY, AND I CAN CHANGE THE GATEWAY] 
  - (B) adding an OpenAI-style route to the gateway [WHEN YOU SAY THIS WHAT IS IT THAT YOU MEAN ?] 
  - (C) a LiteLLM proxy [WE AR ENO LONGER USING LITELLM, WE WILLLL USE A SIMPLE IN HOUSE BUILT WRAPPER] 
3.  **There are two copies of the ingestion code.**
  - `gateway/src/gateway/ingestion/` is the live one. The gateway mounts it and it has tests.
  - `Ingestion 2/merged-ingestion/` is stale. It points to a missing `../../llm_gateway` and has no tests. [THIS IS THE CODE WE WILL EDIT, THE GATEWAY WILL BASICALLY BE DELETED AND REBUILT] 
  - Later steps touch only the live copy. *Confirm before Step 9.*
4. **Neo4j:** Homebrew 2026.06, Community edition, so only one database. The old graph has nothing worth saving (your decision), so Graphiti uses that database after a wipe. No second instance. [OK INTERESTING WHAT DO YOU MEAN ONLY OONE GRAPH, THE LIMITATION ARE THAT I CANT HAVE MORE THAN 1 GRAPH IF I WANT TO I MUST PAY FOR IT ? IF THATS THE CASE WHAT BENEFIT AM I GETTING FROM NEO4J ?] 
5. **Keys:** they live in `Documents/AI Code/.env`. The gateway only finds that file when started from inside a folder named `AI Code`, and it lives in `AI OS`. This needs a decision in Step 1. [DONT WORRY ABOUT THIS RIGHT NOW, THE KEYS ARENT REQUIRED FOR GRAPHITI INTEGRATIONS FOR TESTING YES BUT SINCE I AM ALSO REMAKING GATEWAY I WILL MOVE EVERYTHING AS REQUIRED BY IT] 
6. **Running state when checked:**
  - Ollama: running on 11434
  - Gateway: not running
  - Neo4j: not running
7. **Graphiti hasn't been chosen yet** (Decision D1). This plan builds up to a spike and stops at a go/no-go gate. Everything after the gate depends on the result. [IT HAS YOU CAN CLOSE THIS DECISION] 



## Overview


| Phase               | Steps                                                                | Signed off?        |
| ------------------- | -------------------------------------------------------------------- | ------------------ |
| 1. Set up           | 0 Baseline · 1 Gateway check · 2 Neo4j · 3 Spike project and install | Yes                |
| 2. Integrate        | 4 Adapter · 5 Summary bypass · 6 Hello world                         | No, needs approval |
| 3. Spike            | 7 Golden set comparison · 🚦 Go/no-go                                | No                 |
| 4. If Graphiti wins | 8 Provenance · 9 Consumer · 10 Retrieval · 11 Delete old code        | No                 |


---



## Phase 1: Set up



### Step 0: Baseline ✅ done

- **What:** run the gateway's full test suite before changing anything.
- **Result:** **892 passed, 5 skipped.** The skips are the live Discord, ElevenLabs and loopback tests, which skip when their keys or flags aren't set.
- **Files touched:** none.



### Step 1: Prove the gateway can do Graphiti's job

**Definition of done:** one structured-output chat call and one embedding call succeed through the gateway, and the model ID that answered is recorded.

1. **Decide how the gateway gets its keys.**
  - (a) Create `AI OS/.env` and make the gateway load it. This is a trunk change: tests first, smallest diff. **Recommended**, because the system now lives in `AI OS`. [THIS WILL BE MADE AND WILL BE MADE WITH MORE SECURITY] 
  - (b) Keep `AI Code/.env` and give the gateway the exact path in config. [REJECTING THIS PATH] 
2. **You** start the gateway. Claude doesn't start processes with your keys loaded. [AS IN ?]
  ```bash
   cd "/Users/aryamanchandak/Documents/AI OS/gateway"
   AI_OS_TOKEN=local-dev-token .venv/bin/python main.py   # starts the gateway on 127.0.0.1:8000
  ```
3. Send one `POST /api/llm/chat` request with: [FOR THIS WE REQUIRE A WORKING GATEWAY OR THAT I NEED TO KNOW YOUR ABOVE REQUIREMENTS AND I NEED TO DO SOME WORK IN SIMPLIFYING THE GATEWAY] 
  - a small JSON schema shaped like Graphiti's entity-extraction output
  - `temperature: 0`, because the gateway's default of 0.7 is too random for extraction
4. Check three things: [YES THESE CHECKS MUST BEDONE WHEN TESTING] 
  - the reply matches the schema
  - which provider and model answered
  - the call appears in `GET /api/llm/calls`
5. Send one `POST /api/llm/embed` request and confirm the vector has 768 numbers.
6. Pick the extraction model and record its exact ID.

**Files touched:** none if you choose 1(b). With 1(a): `AI OS/.env` (new) plus the gateway config loader. Named in that step's plan before any edit.

### Step 2: Neo4j ready for Graphiti

**Definition of done:** an empty Neo4j listening only on loopback (`127.0.0.1`), whose data survives a restart. [IF WE ARE GOING TO THIS LEVEL MIGHT AS WELL, DELETE THE GRAH AND REMAKE IT AS IT IS REQUIRED TO BE REMADE IN THIS FOLDER, THE RAW DATABASE AND THE BRONZE LAYER STRUCTURES WILL ALSO HAVE TO BE REMADE OR CAN BE RUSED, WHATEVER WORKS] 

1. Start Neo4j with `neo4j start` and confirm ports 7687 and 7474 listen on `127.0.0.1` only.
2. Show the current node count, then wipe the old graph with `MATCH (n) DETACH DELETE n` (deletes every node and its links). You've approved this.
3. Drop the old graph's indexes and constraints (lookup tables and uniqueness rules) so they can't clash with Graphiti's.
4. Write one test node, restart Neo4j, and confirm the node is still there. Then delete it.
5. Rerun the gateway tests. The `test_kg_*` tests use mocks, so they should still pass.

**Files touched:** none, database only.

### Step 3: Spike project and Graphiti install

**Definition of done:** `graphiti-core` is installed at a pinned version in its own folder, telemetry is off, and the source-reading notes are written.

1. Create the leaf project `AI OS/knowledge-spike/`, using Python 3.12 to match the gateway.
2. Run `uv add graphiti-core` and record the exact version that resolves. Don't assume 0.31.1 from the reference doc.
3. Create `AI OS/DEPENDENCIES.md` with Graphiti's entry: job, version, why chosen, exit plan.
4. Set `GRAPHITI_TELEMETRY_ENABLED=false` in the spike's settings.
5. Read the **installed** Graphiti source (not the online docs) and write down: [GIVE THIS TO ME A IN A DOCUMENT] 
  - the methods the LLM, embedder and cross-encoder plug-ins must implement
  - whether Graphiti silently builds an OpenAI client when no reranker is passed in
  - where entity summaries are generated, and whether an official hook skips them
  - where the 768 embedding size is set; it must be right before the first start creates indexes
  - Graphiti's retry behaviour, so it doesn't stack with the gateway's retries
  - how raw episode text is kept (keep that turned on)
6. No adapter code in this step.

**Files touched:**

- `knowledge-spike/pyproject.toml` (new)
- `knowledge-spike/uv.lock` (new)
- `knowledge-spike/README.md` (new; holds the source-reading notes)
- `DEPENDENCIES.md` (new)

---



## Phase 2: Integrate (needs your approval to start) [FEEDBACK FOR EVERY PART OF THIS PLAN, YOU HAVE SAID WHAT YOU WANT TO DO, BUT MADE NO MENTION TO WHAT PART OF THE CODE YOU WILL BE DELELTING AND REPLACING, THATS WHY WE ARE DOING THIS ENTIRE EXECISE ANYWAY]  



### Step 4: The adapter

**Definition of done:** you confirm this at the start of the step. Proposed tests, written before any code:

- Every model call goes to the gateway. Any attempt to reach `api.openai.com` fails the test. [ABSOLUTELY NO REACHING DIRECTLY] 
- If the gateway is down, ingestion fails with a clear error and never falls back to a provider directly.
- Embeddings are 768 long. Batches become a loop of single `/embed` calls.
- The gateway token comes from `.env` and never appears in logs.
- Extraction calls send `temperature: 0`.

**Files:**

- `knowledge-spike/graph_adapter.py` (new): the three plug-ins plus `build_graphiti()`. Hard limit under 200 lines.
- `knowledge-spike/tests/test_graph_adapter.py` (new)



### Step 5: Summary bypass

**Definition of done:** no summary prompt is ever sent. This is tested on: [WHAT DO YOU MEAN BY THIS AND WHY ARE WE NOT SENDING IT ?? AND WHAT DOES IT DO ? WHAT DOES THIS SUMMARY PLAN DO ?] 

- normal ingestion
- bulk ingestion
- a manually added fact (`add_triplet`)
- a repeat mention of the same entity

How: use the hook found in Step 3. If none exists, handle it in the adapter. Never edit installed library files, and never fake summary replies at the gateway.

**Files:** `graph_adapter.py` and its test file, or a separate file if the 200-line limit is hit (ask first).

### Step 6: Hello world

**Definition of done:** one real passage goes in, and a search returns a fact linked to that passage's episode. [IN THIS CASE A SENTENCE IS SENT ? AND THEN WE SEE A GRAPH WITH REGARDS TO IT ? WE NEED TO MAKE A WAY, THAT WE CAN REBUILD THE GRAPH IF REQUIRED FROM SCRATCH, I THINK THIS IS AN IMPORTANT DECOUPLING WE NEED TO DO, HWO THINGS GET TO THE RAW BRONZE LAYER SHOULD NOT BE THE PERVIEW OF THIS CODE]

1. Ingest one passage with `add_episode`, with communities off and the summary bypass on.
2. Search using RRF only; no LLM reranking.
3. Network check during start-up, ingest, search and shutdown: only `127.0.0.1:8000` (gateway) and `127.0.0.1:7687` (Neo4j) are contacted. No telemetry.
4. Restart Neo4j and confirm the fact is still there.

**Files:** `knowledge-spike/hello_world.py` (new).

---



## Phase 3: Spike (Decision D1)



### Step 7: Golden set comparison [DO WE HAVE ANY REASON TO BELIEVE THAT IT WONT BE CORRECT ?? DO WE HAVE ANOTHER CHOICE HERE ? I AM JUST TRYING TO UNDERSTAND HOW IT MAKES A DIFFERENCE]

- **Your job:** pick 10–15 real passages, including book highlights, short notes and one long note.
- Run the same passages through today's extractor and through Graphiti.
- Score every fact on three questions:
  - is it correct?
  - does it trace to the right passage?
  - would your character-offset check have caught it?
- Run the Migration Plan checklist:
  - "IBM", "IBM Corp." and "International Business Machines" become one entity
  - two different "ICICI" entities stay separate
  - a CEO handover closes the old fact on the right date
  - out-of-order news gives the right date ranges
  - "If A acquires B…" closes no real fact
  - zero JSON failures across all passages
- Record cost per passage and time per passage.

**Files:**

- `knowledge-spike/golden/` (your passages, plain Markdown)
- `knowledge-spike/spike_results.md`



### 🚦 Go/no-go gate [ITS BEEN GRAPHITI AND A HYBRID, MY OWN LAYER IS OUT OF THE PICTURE] 

You choose:

- **A:** Graphiti
- **B:** your own thinned knowledge layer
- **C:** hybrid

This also settles D3 (where human review sits) and D4 (character offsets or passage-level evidence). Update the Decision Register.

---



## Phase 4: Only if Graphiti wins [SO THIS IS ALL TO GET TO A POINT BEFORE WE START CHANGING CODE ?? THATS TOO LONG, I NEED TO KNOW ASAP WHICH AND WHY, I THOUGHT WE WERE GOING TO START INTEGRATION. LETS MOVE FROM THE ASSUMPTION THAT GRAPHITI IS THE BEST TH EONLY THING WE ARE TESTING IS HOW A HYBRID ARCHITECTURE WILL WORK, LETS SCOPE THAT OUT AND THEN LETS SEE BECAUSE I SEE NO WORLD IN WHICH THIS DOESNT WORK SO GIVEN THIS ITS A SIMPLE CASE OF WHERE WE PREFER HYBRID WHERE WE DONT IN WHICH CASE, DO WE NOT LOOK AT HYBRID AS AN IMPROVEMENT TO GRAPHITI A VERSION 2 IN WHICH CASE DO WE NOT TRY OT PUT IN GRAPHITII FIRST AND THEN WORRY ABOUT IMPROVING IT] 


| Step         | What                                                                                                                            | Main files (confirmed at the time)         |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------ |
| 8 Provenance | Map each Graphiti episode ID to the capture-ledger highlight or passage ID and its source range. Decide how big one episode is. | `gateway/src/gateway/ingestion/store.py`   |
| 9 Consumer   | New `graphiti_consumer.py` runs **next to** `kg_consumer.py` on the same inputs. Compare the outputs, then switch over.         | `gateway/src/gateway/ingestion/consumers/` |
| 10 Retrieval | Graphiti for facts, Chroma for full passages, results merged. Add a router only if cost or speed demands one.                   | New search module (named then)             |
| 11 Delete    | Remove `kg/*`, most of `extraction/*` and `kg_consumer.py`, plus the stale `merged-ingestion/` copy.                            | Deletions, listed for approval             |


As Graphiti moves toward the trunk, the adapter moves with it. It stays the only file that imports Graphiti.

## Deferred (not in this plan)

- Attaching CIN/ISIN/NSE/BSE IDs to entities, so the LLM never decides those identities
- Claims and scenarios (observed vs. forecast vs. hypothetical)
- Graphiti MCP server
- Communities and sagas (both summarise, which is currently not allowed)
- Custom ontology (entity and edge types)



## Rules carried through every step

- Tests first. Show the test output before calling a step done.
- Only touch the files named in the step. Stop and update the plan if another file needs changing.
- No new dependency or file without asking first.
- Keys only from `.env`, never printed or logged.
- Commit after every passing step.
- Claude writes the plan and waits; nothing runs until you say "run Step N".



## Open decisions


| #   | Question                                                      | Needed by     |
| --- | ------------------------------------------------------------- | ------------- |
| 1   | Keys: (a) `AI OS/.env` or (b) shared `AI Code/.env`?          | Step 1        |
| 2   | Extraction model and exact ID                                 | End of Step 1 |
| 3   | Is `gateway/src/gateway/ingestion/` definitely the live copy? | Step 8        |
| 4   | How big is one episode: whole document, section or chunk?     | Step 8        |



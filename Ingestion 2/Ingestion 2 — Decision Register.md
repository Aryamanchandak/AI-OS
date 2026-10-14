# Ingestion 2 — Decision Register

Oct 13, 2026 · @AC2

## How to read this

D1 (Graphiti or your own knowledge layer) is the keystone: seven of the other ten decisions wait on it, directly or through another. Decisions are numbered by how much they unblock, so work top-down. Nothing is rejected; every option says when it would win.

| # | Decision | Stage | Waits on | Unblocks |
| --- | --- | --- | --- | --- |
| D1 | Knowledge layer: Graphiti or your own | Spike needed | D2 (partly) | D3, D4, D5, D6, D8, D10 |
| D2 | LLM routing: your gateway or LiteLLM | Ready to start | none | D1 (Graphiti needs an OpenAI-style endpoint) |
| D3 | Where the human gate sits | Blocked | D1 | D6, D10 |
| D4 | Evidence: character offsets or passage-level | Blocked | D1 | D5 |
| D5 | Stores and persistence | Blocked | D1, D4 | D6 |
| D6 | Orchestration: Temporal, LangGraph, DBOS or plain ledger | Deferred | D1, D3, D5 | D9 |
| D7 | File intake: Docling | Ready to start | none | D8 |
| D8 | Chunking: Docling HybridChunker or Chonkie | Blocked | D1, D7 | none |
| D9 | Trigger: launchd, watcher or Temporal Schedule | Deferred | D6 | none |
| D10 | Review UI | Blocked | D3 | none |
| D11 | Observability: Langfuse / OpenTelemetry | Deferred | none | none |

Rules that hold for every choice: each borrowed tool sits behind one adapter file you own; Claude Code's plan names every file it touches; dependencies are judged by adoption, not release recency.

## Dependency map

&#91;embedded content: decision dependencies · 10 linked decisions\]

Only D2 and D7 can start today; everything right of D1 waits on the spike.

## D1 — Knowledge layer: Graphiti or your own (keystone)

A spike on 10–15 golden passages decides this; until then nothing downstream of extraction should be rebuilt. The choice sets how many stages, stores and review steps the pipeline has.

**Option A: Graphiti.** Zep's open-source temporal knowledge graph on Neo4j. You call `add_episode(text)` per passage; it extracts entities and relations, merges duplicates, and marks old facts superseded with validity dates. Your concept/claim/relation schema becomes Pydantic types passed in as custom entity and edge types. Each episode is a node linked to the entities it mentions, so every fact traces to its source passage. It also does hybrid search (embeddings + BM25 keyword + graph traversal).

- Replaces: `extraction/*`, `kg/*` (most), `consumers/kg_consumer.py`, identity proposals, temporal claims, much of `review_policy.py` and the envelope.
- Costs: provenance stops at the passage, not a character range; Graphiti writes straight to the graph, so proposal-level review before write goes away; it needs a model with reliable structured output (its docs name OpenAI and Gemini).
- Wins if: on your fixtures its facts are right, trace to the right passage, and your offset check would not have caught anything it let through.

**Option B: your own layer, thinned (Codex's path).** Keep extraction prompts, verbatim-quote evidence with character offsets, proposal review, identity and cycle rules. Swap your Neo4j wrapper for plain use of the official driver and delete unused helpers.

- Keeps: the strongest guarantee in the system, that every claim points at exact source characters, checked by code.
- Costs: the knowledge layer stays the biggest custom block; you keep owning identity, temporal and cycle logic.
- Wins if: the spike shows Graphiti inventing or misattributing facts that offset checking would have caught.

**Option C: hybrid.** Your extractor and evidence checks produce accepted claims; Graphiti is fed only accepted, evidenced text as episodes. Keeps the guarantee, borrows identity and temporal handling. Costs two extraction passes per passage, so roughly double LLM spend on extraction.

**The spike.** Same passages through today's extractor and through Graphiti with your types. Score each fact: correct, traceable to the right passage, would offset checking have caught it. Record misses and inventions on both sides. One afternoon of Claude Code work, plus your judgment on the results.

## D2 — LLM routing: your gateway or LiteLLM

This is a check, not a debate: can every tool, including Graphiti, call models through one audited endpoint? Do it before the D1 spike.

**Why it matters now.** Graphiti calls providers through its own clients. If it calls them directly, your gateway stops being the single chokepoint for logging and cost. The fix is pointing Graphiti's OpenAI-compatible client at your gateway, which only works if the gateway speaks the OpenAI chat-completions format.

**Option A: keep your gateway.** Already working (your note on the catalog). Wins if it already exposes an OpenAI-compatible endpoint, or adding one is a small change.

**Option B: LiteLLM proxy.** A self-hosted server with one OpenAI-compatible endpoint in front of Ollama, Anthropic, Gemini, OpenAI and others, with fallbacks, retries, budgets and logs. Your code asks for a name like `knowledge-extractor`; LiteLLM maps it to a provider. Wins if your gateway has no OpenAI-compatible endpoint, or you'd rather stop maintaining provider code.

**Option C: both.** Your gateway keeps its audit role and forwards to LiteLLM for provider handling. Only worth it if your gateway does something LiteLLM can't, such as your own audit schema.

**Check:** does the gateway accept a standard `POST /v1/chat/completions` with structured-output (JSON schema) requests? Yes → A. No → B is cheaper than adding it.

## D3 — Where the human gate sits

This falls out of D1: Graphiti pushes the gate to before extraction; your own layer can keep it after. It decides what the review UI (D10) shows you.

| Option | What you review | Fits D1 option | Cost |
| --- | --- | --- | --- |
| Gate the input | Passages before they are sent to extraction (photo OCR already works this way) | A or C | You never see the extracted claims before they land; errors are fixed after the fact |
| Gate the output | Each proposed concept, claim and relation before it is written | B | Most review effort per passage; needs proposal-level UI |
| Gate by exception | Nothing by default; only low-confidence or flagged items | A, B or C | Needs a trustworthy flagging rule; in A, flags come after the write |
| Post-hoc audit | Sample what landed weekly and correct it | A | Cheapest; bad facts are live until you catch them |

## D4 — Evidence: character offsets or passage-level

Also settled by the D1 spike. Character offsets mean every claim carries a verbatim quote and its exact character range, checked by code. Passage-level means a claim links to the passage it came from, and you read the passage to confirm.

- Passage-level is close to as good when passages are short, such as one book highlight or one chunk.
- Offsets matter more for long passages and for claims you will act on, such as financial or forensic facts.
- A split is possible: passage-level for general knowledge notes, offsets kept for a separate finance pipeline later.

## D5 — Stores and persistence

Count the stores after D1, then choose tooling; adding an ORM to five SQLite files that may become two is wasted work. Today: three downstream stores (SQLite content, Neo4j, Chroma) plus five SQLite ledgers.

| Piece | Options | Leaning, and what would change it |
| --- | --- | --- |
| `content.db` projection | Delete; or keep as a queryable relational copy | Delete unless something reads it. Keep if you want SQL queries over claims without Cypher |
| Chroma | Keep for passage search; or drop if Graphiti's hybrid search covers it | Keep at first. Graphiti searches facts and entities; whole-passage search is Chroma's job. Drop only if the spike shows Graphiti episode search is enough |
| Neo4j access | Graphiti owns it (D1-A); or official driver behind your thin adapter (D1-B) | Follows D1 |
| Five SQLite ledgers | Merge into one or two files; or keep separate | Merge `ingestion`, `processed`, `coordinator` once the orchestration choice (D6) is known; Temporal or LangGraph would bring their own state store |
| SQLAlchemy | Adopt for all SQLite access; or keep plain `sqlite3` | Worth it once tables settle; it handles SQLite transaction quirks for you |
| Alembic | Versioned schema migrations; or hand-written schema checks | Adopt alongside SQLAlchemy, after the schema stops churning |

The capture ledger (hashes, versions, raw text) stays yours under every option; see Settled.

## D6 — Orchestration: Temporal, LangGraph, DBOS or plain ledger

Choose after D1, D3 and D5, when the pipeline's final step list is known. All four options stay open; each is described as it would actually run for you.

### Temporal: what it is

A durable-execution engine. You write the pipeline as ordinary-looking Python; Temporal records every step's result, so a crash, a reboot or a five-day wait for your approval resumes exactly where it stopped, with nothing re-done.

Three parts:

- **Server.** Stores the history of every run and hands out work. Locally it is one binary (`brew install temporal`, then `temporal server start-dev`), with a web UI at localhost:8233. By default runs are lost when it stops; `--db-filename` keeps them in a SQLite file ([docs](https://docs.temporal.io/cli/server)). Temporal labels this dev server not for production use; for one user on a Mac Mini that label is about scale and hardening, but note it.
- **Workflow.** Your pipeline's order of steps and decisions. It must be deterministic: no file or network I/O, clock reads or random numbers directly inside it, because Temporal replays it from history to resume.
- **Activities.** Every real piece of work: run Docling, call the LLM, write to Neo4j. Each gets its own retry and timeout policy, and its result is saved once it succeeds.

### Temporal: how your pipeline would run

1. A trigger (D9) starts one workflow per dropped file or vault change.
2. Activity: convert the file with Docling.
3. If review is needed, the workflow waits for a signal. Your review UI sends approve, edit or reject; the wait can last days with no process holding it.
4. Activities: capture to ledger, chunk, extract (or Graphiti `add_episode`).
5. Second wait if D3 keeps an output gate.
6. Activities in parallel: write to Graphiti or Neo4j and Chroma; each retries alone, and finished ones are not repeated.

It would replace `coordinator/coordinator.py`, `state.py`, `stages.py`, the process lock, publication recovery, retry bookkeeping in `dispatch.py`, and most of `report.py` (the Temporal UI shows every run). Writes must still be safe to repeat; Temporal guarantees steps run, not that a store write is duplicate-free.

**Costs:** a server process always running; the determinism rule, which Claude Code can break in ways that only show on replay; a new mental model to learn. **Wins if:** the pipeline keeps several human waits and multi-store writes, or other AI OS agents (Mirfish, event-triggered agents on the Mac Mini) will also need durable runs, so one engine serves all of them.

### The alternatives

| Option | What it is | How it would run here | Wins if |
| --- | --- | --- | --- |
| LangGraph | Graph-of-steps framework for agents, with a checkpointer that saves state and `interrupt()` to pause for a human | Each stage is a graph node; review gates are interrupts; state saved to SQLite | Steps become agent-like loops (extract, critique, re-extract), or you already use it for agents |
| DBOS | A library, not a server: decorators make functions durable, state kept in your database | Same steps as Temporal, no separate server process | You want Temporal-style recovery without running a server. Not checked this session |
| Plain ledger | Each passage has a status column; every stage picks up rows in the right status and is safe to re-run | launchd runs the stages; review UI flips statuses | D1 picks Graphiti and the pipeline shrinks to about four steps; you mostly have this already |

One engine for the whole AI OS is worth more than the best engine per pipeline; weigh D6 against the orchestrator and event-triggered agents, not only ingestion.

## D7 — File intake: Docling

Ready to start now, in parallel with the D1 spike; nothing waits on it except chunking. Docling converts PDF (text and scanned), DOCX, PPTX, HTML, Markdown and images into one structured document, with OCR, tables and reading order. It can use Apple's Vision OCR (`OcrMacOptions`), the engine you use today.

- Replaces: `intake/extractors/pdf.py`, `word.py`, `markdown_passthrough.py`, the OCR fallback, much of `image.py`.
- Legacy .doc: Codex says Docling reads it through LibreOffice (not verified here). Options: that, or keep the `textutil` shim.
- Stays yours: the yellow-highlight detector and passage grouping. Docling reads the page; it does not know what you highlighted.
- Test: run 5 real files per format through both paths and compare the Markdown.

## D8 — Chunking: Docling HybridChunker or Chonkie

Wait for D1 (episode size) and D7 (Docling in place). The highlight stays the identity; chunks are only for retrieval or as Graphiti episodes.

| Option | How it splits | Wins if |
| --- | --- | --- |
| Docling HybridChunker | Document structure (headings, sections) within a token limit | Docling is already in; one fewer dependency |
| Chonkie | Many methods: sentence, recursive, semantic (embedding similarity), LLM-chosen boundaries | Plain Obsidian notes chunk badly by structure, or you want topic-shift splitting back |
| Keep phi4 topic segmentation | LLM judges where a new topic starts | Neither library matches its quality on your notes |

Either way, `parsing.py` segmentation and `vector/chunking.py` become one chunker behind one adapter.

## D9 — Trigger

Follows D6. Whatever runs the pipeline decides how it is started.

| Option | How it works | Fits D6 option |
| --- | --- | --- |
| launchd `WatchPaths` / `QueueDirectories` | macOS starts your script when the drop folder changes; no code of yours keeps running | Plain ledger, LangGraph, DBOS |
| `watchfiles` | A small always-on Python process that reacts to file events and starts a run | Any; needed if you want sub-second reaction |
| Temporal Schedule | Temporal starts a scanning workflow every N minutes | Temporal |

## D10 — Review UI

Follows D3: an input gate needs a passage approval screen; an output gate needs proposal-by-proposal review. The FastAPI cockpit router exists; a frontend and an app that mounts it do not. Options: build it inside the UI for AI OS project (phone-first), or use the Temporal UI only for run status, never for review. Mobility-first rules out a desktop-only review screen.

## D11 — Observability

Deferred until the pipeline runs daily. Langfuse records every LLM call (prompt, output, cost, time) and plugs into LiteLLM; OpenTelemetry is the general standard if you later want one trace across all agents. If D6 picks Temporal, its UI covers run-level status and Langfuse covers LLM calls.

## Settled: stays yours under every option

These encode your judgment or domain, so no D-decision changes them; Claude and Codex agree on all of them.

- Yellow-highlight detection and passage grouping (`sources/page_scanner/detect.py`, `photo_pipeline.py`).
- Abbreviation glossary and its review (`text_cleanup/abbreviations.py`, `store.py`).
- Capture ledger: hashes, versions, raw text, stable highlight IDs (`store.py`, `normalization.py`, `ids.py`). This is the bronze record contract.
- Pydantic contracts (`models.py`) as the boundary every borrowed tool adapts to.
- Book identification, thinned: delete the unwired `find_cover`.
- Obsidian publishing and archiving (`publish/vault_writer.py`).
- Entity types for your domain, whether written as Graphiti types or your own schema.

## Next actions

- [ ] D2 check: does the gateway accept OpenAI-style chat completions with JSON-schema output?
- [ ] Pick 10–15 golden passages: book highlights, short notes, one long note.
- [ ] D1 spike: same passages through today's extractor and Graphiti; score each fact.
- [ ] D7 in parallel: 5 files per format through Docling vs current extractors.
- [ ] After the spike: set D1, D3, D4 to Settled here, then unblock D5 and D8.

## Verification status

Checked against primary docs this session: Graphiti custom types, episodes and hybrid search; Docling formats and macOS Vision OCR; Temporal dev server and SQLite persistence. From prior knowledge only: LiteLLM, LangGraph `interrupt()`, launchd `WatchPaths`, Langfuse, SQLAlchemy and Alembic. Not checked: DBOS, Chonkie, Docling's legacy .doc support.

## Sources

- [Graphiti: custom entity and edge types](https://help.getzep.com/graphiti/core-concepts/custom-entity-and-edge-types)
- [Graphiti: adding episodes](https://help.getzep.com/graphiti/core-concepts/adding-episodes.md)
- [Graphiti README](https://github.com/getzep/graphiti)
- [Docling pipelines and OCR engines](https://docling-project.github.io/docling/examples/agent_skill/docling-document-intelligence/pipelines/)
- [Docling installation](https://docling-project.github.io/docling/installation)
- [Temporal CLI server reference](https://docs.temporal.io/cli/server)

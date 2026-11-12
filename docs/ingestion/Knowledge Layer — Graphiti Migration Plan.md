# Knowledge Layer — Graphiti Migration Plan

Oct 13, 2026 · @AC2

## How to read this doc

This doc replaces the GPT-drafted architecture note. It is organised as one card per module, so you can open your existing code for that module, read what it does, and decide how Graphiti takes over the same job. Nothing here asks for a big-bang rewrite.

Every card has the same five parts: what the module does in plain words, what your code does today (you fill this in when you open it), what Graphiti or another tool does instead, the reservations, and how to test before switching.

### Glossary

| Term | Plain meaning |
| --- | --- |
| Graphiti | An open-source Python library that reads text, pulls out people, companies and the links between them, and writes them into Neo4j. It also keeps track of when each link was true. |
| Neo4j | The graph database. It stores dots (entities) and lines (relationships). Graphiti writes to it; Neo4j does no thinking itself. |
| Episode | One piece of text you hand to Graphiti in one go: a note, a section of a PDF, a message. Graphiti remembers which episode every fact came from. |
| Entity / node | A thing: a person, company, security, idea. A dot in the graph. |
| Edge / fact | A link between two things, stored with a one-line sentence, e.g. "Sarah is CEO of Company X". A line in the graph. |
| Entity resolution | Deciding that "IBM", "IBM Corp." and "International Business Machines" are the same thing, so they become one dot, not three. |
| Invalidation | When new text contradicts an old fact, Graphiti marks the old fact as no longer true from a date, instead of deleting it. |
| Valid time | When something was true in the world ("Sarah became CEO on 1 March"). |
| Ingestion time | When your system learned it ("we read that on 13 October"). |
| group\_id | A label that splits the graph into separate compartments. Graphiti only compares and merges things inside the same compartment. |
| Claim | A fact plus how sure we are of it: observed, forecast, hypothetical, opinion. |
| Scenario | A named "what if" world, e.g. bull case or bear case, where facts can contradict another scenario without either being wrong. |
| Chunk | A short slice of a document, a few paragraphs long, stored in the vector database. |
| Embedding | A list of numbers that captures the meaning of a chunk, so similar text can be found by meaning rather than exact words. |
| Vector DB | The database that stores chunks and their embeddings. Yours is Chroma. |
| Structured output | Forcing a model to reply in an exact JSON shape. Graphiti depends on it; weak models break it. |
| ZDR | Zero data retention: the model provider does not keep your prompts. |
| Retrieval router | A small piece of logic that decides whether a question goes to the graph, the vector DB, or both. |
| Fusion / reranking | Merging results from several searches and re-sorting them by relevance. |

## The idea in plain English

Keep two stores side by side and link them: a graph for who-is-connected-to-what over time, and a vector DB for find-me-passages-that-mean-this. Neither replaces the other.

The graph answers questions like "who was CEO of X in May?" or "what is linked to Company A?". The vector DB answers "find passages about liquidity stress" even when those words never appear. Every fact in the graph should point back to the passage it came from, and every passage should point to the facts pulled out of it.

What changes: today you maintain the graph with your own code. Graphiti takes over the generic graph work — extracting entities, merging duplicates, and closing out facts that stop being true. Your own code stays for the parts that are specific to you: deterministic IDs (CIN, ISIN), claims and scenarios, linking graph to chunks, and deciding where a question goes.

The one rule underneath: the system stores what sources say, not what is true. A forecast, a hypothesis and an observed fact must be stored differently, or the graph will treat a bull-case guess as fact.

## Migration approach

Replace one module at a time, but run Graphiti next to the old code before switching, not in place of it. This is the right approach for a codebase you want to understand and keep thin.

One catch shapes everything: Graphiti owns its own layout inside Neo4j (its own node and edge labels, its own timestamps). It cannot write into your current graph schema piece by piece. So run it in a separate Neo4j database, feed both old and new the same inputs, compare, then cut over.

Per module:

1. Open the existing module and fill in "Today" on its card below.
2. Pick 20 of your own documents that exercise that module.
3. Run them through both the old module and Graphiti.
4. Compare outputs side by side; log every difference.
5. Switch only when Graphiti is as good or better, or the difference is one you accept.
6. Delete the old module's code. That deletion is the payoff.

Suggested order, foundations first:

1. Entity resolution — it is the surprise, and everything else depends on it.
2. Entity and fact extraction.
3. Time handling (closing out old facts).
4. Claims and scenarios.
5. Linking graph facts to vector chunks.
6. Retrieval and routing — last, because it reads from everything above.

## Module cards

Eleven modules. Graphiti takes over three of them outright (extraction, resolution, time handling); the rest stay yours or use other tools.

### 1. Source registry and ingestion

**Job:** Keep a list of every document you have, where it lives, its hash and version, and whether it has been processed.

**Today:** *Fill in when you open the module.*

**New:** Stays your own code, in SQL (SQLite is fine). Graphiti does not do this. Hashing and change detection live here too (see card 6).

**Reservation:** None. Small, boring, worth owning.

### 2. Entity and fact extraction

**Job:** Read text, pull out the things mentioned and the links between them.

**Today:** *Fill in when you open the module.*

**New:** Graphiti's `add_episode` does this. You can give it your own entity types (Company, Security, Person) as Pydantic models, so it extracts into your categories.

**Reservations:**

- Graphiti needs models that reliably reply in exact JSON. Its docs warn that smaller models emit malformed JSON, which shows up as failed ingestion. Moving from Sonnet to open-source ZDR models is the main risk in this whole migration. Test your chosen model on 20 documents before committing.
- Each episode triggers several model calls (extract, deduplicate, resolve facts, extract dates). Budget per document, not per call.
- Never use `add_episode_bulk` for live data: it skips invalidation entirely. Use it only to fill an empty graph.

### 3. Entity resolution

**Job:** Decide whether a newly mentioned thing is already in the graph.

**Today:** *Fill in when you open the module.* Also note what your entity-resolution MCP server does with CIN, ISIN, NSE and BSE codes.

**New, as far as I understand it (verify):** for each new entity, Graphiti searches existing entities in the same `group_id` by name, using both meaning and keywords, then asks the LLM whether any candidate is the same thing. It knows nothing about CIN or ISIN. Recent versions may run a cheap exact or fuzzy name match before calling the LLM; I could not confirm that from the docs. Check `graphiti_core/utils/maintenance/node_operations.py` (look for the resolve function) to see the real steps.

**Reservations:**

- LLM-judged merges can be wrong both ways: merging two different companies, or splitting one into two. Both silently damage the graph.
- Resolution only looks inside one `group_id`. If scenarios become separate groups, "Company A" becomes a separate dot in each.

**Plan:** your own ID resolver runs first. If a CIN or ISIN is known, attach it to the entity so identity never depends on the LLM. Graphiti's resolution handles only what has no ID.

### 4. Time handling

**Job:** When new text says a fact stopped being true, close the old fact at a date instead of deleting it. Handle news that arrives out of order.

**Today:** *Fill in when you open the module.*

**New:** Graphiti stores four timestamps per fact (when it became true, when it stopped, when the system learned it, when the system retired it) and closes old facts automatically.

**Reservation:** the decision to close a fact is made by the LLM, and so are the dates. It is not guaranteed. The CEO-succession and out-of-order examples in the old doc are what it is designed for, not what it always gets right. Test them (see the checklist).

### 5. Claims and scenarios

**Job:** Store whether a fact is observed, forecast, hypothetical or opinion, and which scenario it belongs to.

**Today:** *Fill in when you open the module.*

**New:** Mostly your own code. Graphiti has no built-in idea of a claim or a scenario. Its unit is a fact sentence between two entities.

**Reservations:**

- Two ways to add claim fields, each with a cost. Store claims as their own dots, and Graphiti's time handling no longer applies to them. Store them as extra fields on facts, and the LLM fills those fields in, so they are guesses.
- The only way to keep scenarios apart is `group_id`. Same group: a bear-case sentence can close out a bull-case fact. Separate groups: shared entities are duplicated.
- Hypothetical text in the main group ("if A acquires B…") can close out a real fact. You need a step before Graphiti that sorts text into observed, hypothetical and scenario, and sends each to the right group. That sorter is the real custom work.
- Drop the `confidence: 0.67` field. A model-written number is not a measured confidence. Derive it later from your source calibration ledger if needed.

### 6. Vector store and its upkeep

**Job:** Store chunks of source text with embeddings, so passages can be found by meaning. Keep it in sync as documents change.

**Today:** *Fill in when you open the module.* Chroma.

**New:** The vector DB stays — agreed, graph plus vector, not one alone. The open question is only who manages it. LlamaIndex IngestionPipeline handles hashing, change detection and re-chunking, but its default behaviour is replace-on-change: the old chunk is overwritten. You want old versions kept with an end date. Getting that from LlamaIndex means version-specific IDs, which defeats its change detection.

**Reservation:** LlamaIndex may cost more to bend than to skip. Hash-and-version logic is roughly 100 lines in the source registry. Decide when you open this module; Chroma stays either way unless a framework needs a different store.

### 7. Embeddings

**Job:** Turn chunks into numbers for meaning search.

**Today:** *Fill in when you open the module.*

**New:** A local model through Ollama for chunks. Record the model name, version and vector size with every index; switching models means re-embedding everything.

**Reservation:** Graphiti also embeds entity names and fact sentences with its own embedder, separately. Point that embedder at local Ollama as well, or extracted facts leave the machine even though chunks don't.

### 8. Linking graph to chunks

**Job:** From any fact, get back to the passage it came from; from any passage, get the facts pulled from it.

**Today:** *Fill in when you open the module.*

**New:** Graphiti records which episode each fact came from. Link episodes to chunk IDs yourself, through the source registry.

**Open:** what one episode should be (a whole document, a section, a chunk). Decide when you open this module. Whole documents make the link coarse; single chunks lose context during extraction.

### 9. LLM access

**Job:** Every model call goes through one gateway for routing, retries, logging and privacy.

**Today:** LLM Gateway V7. *Add details when you open the module.*

**New:** Graphiti talks to the gateway as if it were an OpenAI-style endpoint. Graphiti's generic OpenAI-compatible client injects the JSON shape into the prompt for providers that lack native structured output.

**Reservation:** check that your ZDR provider and model support strict JSON schema mode, not just "JSON mode". Pin the model version, since a silent model swap can break extraction.

### 10. Retrieval and routing

**Job:** Decide where a question goes (graph, vector, or both), then merge and rank the results.

**Today:** *Fill in when you open the module.*

**New:** Start without a router: send every question to both stores, merge, rerank. Graphiti's own search already mixes keyword, meaning and graph-distance search. Add a rule-based router only when cost or speed demands it, using simple signals (a date in the question, an exact ID, the word "similar").

### 11. Privacy settings

**Job:** Make sure nothing leaves the system unintentionally.

**New:** Set `GRAPHITI_TELEMETRY_ENABLED=false` in deployment config. Route Graphiti's LLM calls through the gateway and its embedder to local Ollama (card 7).

## Open decisions

Five decisions are deliberately left until you open the relevant module.

| Decision | Decide when | What settles it |
| --- | --- | --- |
| Does v1 need claims and scenarios at all? | Before card 5 | If the claims/disputes agent stays parked, v1 = observed facts only, and scenarios come later in their own groups. Settle it after cards 2–4 show how Graphiti behaves on your data. |
| What is one episode? | Card 8 | Test whole-document, section and chunk on the same 20 documents; compare extraction quality and how precise the source link is. |
| LlamaIndex or own hash-and-version code? | Card 6 | Whether LlamaIndex can keep old chunk versions with an end date without fighting its change detection. |
| Which open-source ZDR model for extraction? | Card 2 | Pass rate on the JSON and extraction tests below, then cost per document. |
| Keep Chroma or switch? | Card 6 | Only if the chosen lifecycle framework works materially better with another store. |

## Test checklist

Run these on a separate Neo4j database before trusting Graphiti with real data. Each one is a handful of short texts you write yourself.

**Entity resolution**

- [ ] "IBM", "IBM Corp." and "International Business Machines" end up as one entity.
- [ ] Two different companies with similar names (e.g. two "ICICI" entities) stay separate.
- [ ] An entity with a CIN or ISIN attached is never merged with a different ID.
- [ ] Read the resolution code path and write down its actual steps in card 3.

**Time handling**

- [ ] John is CEO from Jan 2024; then "Sarah replaced John on 1 March 2026" → John's fact closes on 1 March, Sarah's opens.
- [ ] Out of order: David became CEO in June is ingested first, then Sarah in March → Sarah runs March to June, David June onward.
- [ ] One text that changes four facts (a sale plus a role change) closes and opens all four.

**Hypotheticals and scenarios**

- [ ] "If Company A acquires Company B…" does not close any real fact.
- [ ] A bear-case statement does not close a bull-case fact when they sit in separate groups.

**Model and privacy**

- [ ] The chosen ZDR model completes 20 real documents with zero JSON failures.
- [ ] Network check: with telemetry off and the embedder local, no calls leave the machine except to the gateway.

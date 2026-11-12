# EAGV3 Session 7 — Codebase Overview Report

**Last updated:** 2026-06-23
**Project name:** eagv3-s7
**Entry point:** `agent7.py`

---

## 1. What This Project Is and What It Does

This project is an AI agent built as a learning exercise for Session 7 of the EAG V3 course. It takes a natural-language question as input — things like "What is the current time in Tokyo and Bangalore?" or "Find me the top articles about quantum computing and summarise them" — works through the question in a series of steps using external tools, and eventually produces a final answer.

The Session 7 version extends the prior session's agent in one important way: it adds a real memory layer with semantic search. The agent can now not only remember what it did in earlier iterations of the current run, it can also ingest external documents (files or web pages) and make their contents searchable using vector embeddings stored in a FAISS index. Two new tools — `index_document` and `search_knowledge` — surface this machinery to the model directly.

---

## 2. Overall System Purpose and Architecture

The agent follows a structured five-stage loop that runs up to 20 times per query. Each pass through the loop is one "iteration," and the agent keeps going until every goal it identified is satisfied. The five stages are:

1. **Memory Read** — Pull relevant past knowledge from persistent storage.
2. **Perception** — Inspect the current situation and decide what goals still need to be accomplished.
3. **Decision** — For the first unfinished goal, either answer it directly or pick one external tool to call.
4. **Action** — Execute that tool call and handle the result.
5. **Memory Write** — Save the outcome so it's available in future iterations and future runs.

The system sits on top of a separately running HTTP service called LLM Gateway V7 (in the `llm_gatewayV7/` subdirectory). The agent never calls an AI model directly — it always goes through the gateway. The gateway handles model selection, rate limiting across multiple providers (Gemini, Groq, GitHub, Ollama, etc.), and the new embedding endpoint.

The external tools available to the agent are served by a second Python process called the MCP server (`mcp_server.py`). The agent process communicates with the MCP server over standard input/output, following the Model Context Protocol (MCP) standard. This keeps the tool implementations isolated from the agent logic.

---

## 3. File-by-File Breakdown

### `schemas.py` — The Shared Type Contracts

This is the foundation that every other file imports from. It defines all the data structures that flow between layers, using Pydantic models for validation.

**Key types:**

- **`MemoryItem`** — One record in the agent's persistent memory. It has a `kind` (one of `fact`, `preference`, `tool_outcome`, or `scratchpad`), a short human-readable `descriptor`, a `keywords` list, a structured `value` dict, an optional `artifact_id` pointer, and crucially, an optional `embedding` field — a list of floating-point numbers that encodes the semantic meaning of the record for vector search. Scratchpad items skip embedding; the other three kinds get one at write time.
- **`Artifact`** — Metadata record for a stored file blob. The actual bytes are stored on disk; this record holds the handle, the file type, the size, and a short description.
- **`Goal`** — A single step the agent is working toward. Has a `text` describing what needs to happen, a `done` flag, and an optional `attach_artifact_id` — a pointer to a stored file that Perception has decided Decision needs to read.
- **`Observation`** — A list of Goals, with helper methods to check whether all goals are done and to find the next unfinished one.
- **`DecisionOutput`** — What the Decision layer produces: either an `answer` (plain text) or a `tool_call` (a tool name plus arguments). Exactly one of these is non-null on any given iteration.
- **`ToolCall`** — The name and arguments for an MCP tool call.

---

### `agent7.py` — The Orchestrator

This is the main entry point. Run it from the command line with a query string. It wires all five layers together into the iteration loop.

**What it does, step by step:**

1. Calls `ensure_gateway()` to start the LLM Gateway if it is not already running.
2. Generates a short random `run_id` to tag all memory writes from this session.
3. Calls `memory.remember()` to persist the user's original query so facts embedded in it (names, dates, preferences) survive into future runs.
4. Spawns the MCP server as a subprocess and establishes a client session with it over stdio.
5. Asks the MCP server for its full list of available tools and converts them into the format the gateway expects.
6. Enters the main loop (up to 20 iterations). Each iteration:
   - Calls `memory.read()` for relevant past knowledge.
   - Calls `perception.observe()` to get the current goal list.
   - If all goals are done, exits the loop.
   - Takes the first unfinished goal. If Perception flagged that goal as needing raw artifact bytes, loads them from the artifact store.
   - Calls `decision.next_step()`.
   - If the decision is an answer, records it in the run history and continues.
   - If the decision is a tool call, runs it through `action.execute()`, then calls `memory.record_outcome()` to save the result.
   - Appends a history entry either way.
7. Prints and returns the final answer.

The history list is in-memory only — it does not survive across runs. Durable information goes through the Memory service.

---

### `schemas.py` *(already covered above)*

---

### `perception.py` — Goal Planner and State Tracker

Perception is the only layer that maintains state between iterations. Every loop iteration, it receives the original query, the memory hits, the run history, and the prior goal list, and it emits an updated goal list.

**The key design decisions baked into Perception:**

Goals are identified by **position in the list, not by a string ID**. This prevents the model from accidentally renaming or reordering goals across iterations, which would break the progress-tracking logic. The rule is strict: prior goals keep their slot; new goals may only be appended to the end.

Perception decides whether a goal needs raw artifact bytes by inspecting its text for synthesis-type keywords (words like "summarise," "extract," "compare," "analyse"). If the goal involves working on content — not just fetching it — Perception sets the `attach_artifact_id` field on that goal, pointing to the most relevant stored artifact. Decision then receives the full text of that artifact as part of its prompt. There is also a safety net: if Perception forgot to set this flag but the goal text clearly calls for synthesis work and an artifact is available, the orchestrator forces the attachment.

A synthesis goal is not allowed to be marked done unless the run history contains an actual answer (more than 60 characters long) tied to that goal. This prevents the model from falsely declaring a question answered on the strength of a mere tool call.

**The Perception LLM call** uses temperature 1.0 and enforces structured JSON output via the gateway's `response_format` feature. The model is Gemini (provider `"g"`).

---

### `decision.py` — The Per-Turn Reasoner

Decision receives the first unfinished goal, the memory hits, the last six history entries, any attached artifact bytes, and the full tool list. It makes exactly one choice per iteration: either write a text answer or call one tool.

**Important implementation notes:**

- Temperature is set to 0 for deterministic tool selection.
- The system prompt forbids the model from using `art:...` handles as file paths or URLs (a hallucination pattern the model exhibits without this guard). If Action detects this error anyway, it returns a clear error message without wasting a tool call.
- When memory hits contain chunks from previously indexed documents (recognizable by descriptors starting with `[sandbox:` or `[art:`), the system prompt tells the model to answer directly from those chunks rather than re-fetching the original source.
- Attached artifact content is capped at 30,000 characters (20,000 from the head, 10,000 from the tail) with a truncation notice in between, to stay within model context limits.

The `next_step()` function is the single exported entry point. It calls `LLM().chat()` with tools enabled and `tool_choice="auto"`, then interprets the result.

---

### `action.py` — The MCP Dispatcher

Action is the simplest layer — it executes tool calls with no LLM involvement. Its one job is to call the MCP server tool, check if the result is large, and if so push the bytes to the artifact store.

Results larger than 4,096 bytes (roughly one page of text) go into the artifact store. Action returns a short descriptor string and the artifact ID handle. Smaller results are returned as plain text with no artifact created.

The threshold is intentional: large responses (a fetched web page, a long file) should not be pasted into every subsequent LLM prompt. Instead they live in the artifact store and are attached selectively by Perception only when a goal actually requires processing them.

The exported function is `execute(session, tool_call)`, which returns a tuple of `(descriptor_text, artifact_id_or_None)`.

---

### `memory.py` — The Persistent Memory Service

Memory is the agent's long-term storage. It persists to `state/memory.json` on disk and to a FAISS binary index at `state/index.faiss`. Reads go through vector search first, falling back to keyword overlap only when the vector path returns nothing.

**Four kinds of memory items:**

- **`fact`** — Used for world knowledge, user-stated facts, and indexed document chunks. Gets an embedding at write time.
- **`preference`** — User preferences extracted from queries (e.g., "I prefer metric units"). Gets an embedding.
- **`tool_outcome`** — The result of a tool call, written deterministically by the orchestrator after every Action. Gets an embedding.
- **`scratchpad`** — Run-scoped ephemeral notes. Does not get an embedding and is not stored in the vector index.

**Two write paths:**

1. `remember()` — Used for ambiguous free-form content like the user's raw query. Makes one LLM call to classify the content into a kind, extract keywords, and generate a structured `value` dict. Then computes an embedding. If the classifier fails, a deterministic fallback (`_fallback_remember`) handles it without LLM.
2. `record_outcome()` — Used after every tool call. Fully deterministic, no LLM. Builds the descriptor from the tool name and arguments, computes an embedding, and persists.

There is also `add_fact()`, a direct write path used by the `index_document` tool that skips the LLM classifier but still computes an embedding.

**Read path:** `read()` calls `_vector_search()` first. This embeds the query text (using task type `"retrieval_query"`) and searches the FAISS index for the nearest neighbors. If this returns nothing, `_keyword_search()` tokenizes the query and history and scores all items by word overlap.

---

### `artifacts.py` — The Binary Store

This module handles raw bytes (web pages, file contents). It uses content-addressable storage: each blob is keyed by the first 16 characters of its SHA-256 hash, so identical content is stored only once regardless of how many times it was fetched.

Each artifact gets two files under `state/artifacts/`:
- A `.bin` file containing the raw bytes.
- A `.json` file containing an `Artifact` metadata record (ID, type, size, source, descriptor).

The public interface is four functions: `put()` (write and get a handle), `get_bytes()` (read raw bytes by handle), `get_meta()` (read metadata), and `exists()` (check whether a handle is valid).

---

### `vector_index.py` — FAISS Index Wrapper

This wraps Facebook's FAISS library to provide a simple add/search/persist interface keyed by string IDs. FAISS internally stores vectors by integer position; this module maintains a parallel list of string IDs to map positions back to application-level `MemoryItem` identifiers.

The index uses inner product on L2-normalized vectors, which is mathematically equivalent to cosine similarity. The dimension of the index is inferred from the first vector added and fixed for all subsequent additions — this is why the embedding model must never change for the lifetime of an index.

Two files are persisted to `state/`: `index.faiss` (the FAISS binary format) and `index_ids.json` (the parallel ID list). On cold start, if either file is missing, the Memory service rebuilds the index by re-adding embeddings from `memory.json`.

The class is `VectorIndex`. Key methods: `add(item_id, embedding)`, `search(query_embedding, k)` → list of `(item_id, score)` pairs, `persist()`, `clear()`, and the `size` property.

---

### `gateway.py` — The LLM Gateway Bridge

This module is a thin adapter that bridges the agent to the LLM Gateway V7 service. It does three things:

1. **`ensure_gateway()`** — Checks whether the gateway is already running on port 8107. If not, launches it as a background subprocess and waits up to 45 seconds for it to come up.
2. **Imports the gateway's `client.py`** without polluting the Python module path (which would cause the gateway's own `schemas.py` to shadow the agent's `schemas.py`). It uses Python's `importlib` to load the file by direct path.
3. **`embed(text, task_type)`** — A module-level helper that calls the gateway's `POST /v1/embed` endpoint and returns the embedding vector.

**Important path issue:** The gateway directory is computed as two levels above the `gateway.py` file, which resolves to `/Users/aryamanchandak/Documents/llm_gatewayV7`. This path does not exist on disk. The actual gateway code lives at `Lecture 7/llm_gatewayV7/`. This means `ensure_gateway()` will raise a `RuntimeError` if the gateway is not already running — the auto-start path is broken unless the gateway directory is moved or the path in `gateway.py` is corrected. See Section 6 for details.

---

### `mcp_server.py` — The Tool Provider

This runs as a separate process and speaks the Model Context Protocol over stdio. It exposes eleven tools to the agent:

**Information retrieval:**
- `web_search(query, max_results)` — Searches the web. Uses the Tavily API as the primary backend (requires `TAVILY_API_KEY` in `.env`), with DuckDuckGo as an automatic fallback. Hard-capped at 5 results. Tracks monthly usage in `usage.json` and stops using Tavily above 950 calls/month.
- `fetch_url(url, timeout)` — Fetches a URL and returns clean Markdown via crawl4ai (a headless Chromium-based crawler). Large enough results become artifacts automatically via the Action layer.
- `get_time(timezone)` — Returns the current time in any IANA timezone (e.g., `"Asia/Kolkata"`). No network call needed.
- `currency_convert(amount, from_currency, to_currency)` — Converts between ISO currency codes using the free Frankfurter API.

**Sandbox file system:**
- `read_file(path)` — Reads a file from the `sandbox/` directory. Paths that would escape the sandbox are rejected.
- `list_dir(path)` — Lists a directory in the sandbox, returning a dict with `count`, `names`, and `entries`.
- `create_file(path, content)` — Creates a new file; errors if it already exists.
- `update_file(path, content)` — Overwrites an existing file; errors if it does not exist.
- `edit_file(path, find, replace, replace_all)` — Find-and-replace inside a sandbox file. Requires `replace_all=True` when the target string appears more than once.

**Knowledge base (Session 7 additions):**
- `index_document(path, chunk_size, overlap)` — Reads a sandbox file or artifact, splits it into overlapping word-based chunks (default 400 words with 80 words of overlap), and writes each chunk to Memory as a `fact` with an embedding. After indexing, the content becomes searchable via vector similarity across all future turns and runs. This is the right choice when content needs to survive; `read_file` is for one-time inspection.
- `search_knowledge(query, k)` — Performs a vector search over indexed `fact` chunks in Memory and returns up to `k` ranked results with their source and full chunk text.

**Sandbox isolation:** All file tools resolve paths against `./sandbox/` and reject any path that escapes it using a path traversal check.

---

### `llm_gatewayV7/` — The LLM Gateway Service

This is a separate FastAPI application that acts as a unified interface to multiple AI providers. The agent never calls Gemini, Groq, or any other provider directly — all LLM calls go to the gateway's `POST /v1/chat` endpoint at `http://localhost:8107`.

**What the gateway adds in V7 over V3:**
- A new `POST /v1/embed` endpoint that returns a vector embedding for a piece of text. This is what `gateway.embed()` calls and what the Memory layer uses for every vector write and read.
- The same multi-provider failover, rate limiting, structured output validation, and routing logic from V3.

The gateway's routing system classifies each request as TINY, LARGE, or HUGE based on estimated token count and content density, then selects the appropriate provider tier. HUGE requests (over 8,000 tokens) are rejected with a 503 — the Summarizer Agent that would handle them is described in the code as "not yet implemented."

The embedding backend is configured at the gateway level. Every FAISS index built against one embedding model is invalidated if the model changes, so the model is treated as a project-level constant.

---

## 4. How the Pieces Fit Together Architecturally

The overall architecture can be understood as three concentric rings:

**Innermost ring — the typed pipeline.** The five layers (`memory`, `perception`, `decision`, `action`, `memory`) communicate exclusively through the Pydantic types defined in `schemas.py`. No layer passes raw dicts or strings to another; every hand-off is a validated model. This makes the boundary between layers explicit and testable.

**Middle ring — the services.** Two stateful services back the pipeline. The Memory service manages `state/memory.json` and the FAISS index. The Artifact store manages binary blobs under `state/artifacts/`. These services are accessed directly by the pipeline layers as Python module imports, not over a network.

**Outer ring — the processes.** Two external processes communicate with the agent over defined protocols. The MCP server is a subprocess talking JSON-RPC over stdio; the gateway is a local HTTP service on port 8107. The agent spawns the MCP server fresh every run; the gateway is a long-running service.

**Key design principle — handles vs. bytes.** Large data (fetched web pages, file contents) never flows through the main reasoning chain. Action captures large results as binary blobs in the artifact store and records only a short descriptor plus handle in Memory. Perception decides which goal needs the actual bytes, and attaches them once for Decision to work on. This means a 200KB web page touches at most one LLM call instead of being re-injected into every iteration.

**Key design principle — goal stability.** Perception is stateful but carefully constrained. Goals are identified by position in the list. The LLM cannot rename, reorder, or drop a goal once it is set — only append new ones at the end. Synthesis-type goals have an additional guard: they cannot be declared done without a recorded answer of meaningful length. This prevents the common failure mode where a model confidently declares a task finished after a tool call without actually synthesising the result.

**Key design principle — two write paths.** Memory differentiates between uncertain knowledge (the user's raw query, where the model must classify what kind of memory item to create) and certain knowledge (tool call outcomes, which are deterministic). The deterministic path skips the classifier LLM entirely. This is both cheaper and more reliable — tool outcomes always go into memory even when the gateway is slow.

---

## 5. How a Typical Interaction Works

**Example: "What is the current time in Tokyo and Bangalore?"**

1. `agent7.py` calls `ensure_gateway()` to verify the gateway is up, then calls `memory.remember()` to save the query.
2. The MCP server process starts and reports 11 available tools.

**Iteration 1:**
- Memory returns no hits (this is the first run).
- Perception sees no prior goals and decomposes the query into three goals: "Look up the current time in Tokyo," "Look up the current time in Bangalore," and "Tell the user the time difference."
- The first unfinished goal is the Tokyo lookup. Decision calls `get_time("Asia/Tokyo")`.
- Action executes the tool call. The response is a small dict (under 4KB) so no artifact is created.
- Memory records the outcome as a `tool_outcome` item with an embedding.

**Iteration 2:**
- Memory retrieves the Tokyo outcome via vector similarity.
- Perception marks the Tokyo goal done, identifies Bangalore as next.
- Decision calls `get_time("Asia/Kolkata")`.
- Memory records the Bangalore outcome.

**Iteration 3:**
- Memory retrieves both time outcomes.
- Perception marks the Bangalore goal done. The third goal ("Tell the user the time difference") involves synthesis, so Perception would ordinarily try to attach an artifact — but the times are small and already in the memory hits, so no artifact attachment is needed. The synthesis goal is the first unfinished one.
- Decision sees both time values in the memory hits and answers directly in plain text.
- The orchestrator records this as an "answer" history entry.

**Iteration 4:**
- Perception marks the synthesis goal done. `all_done` is True. Loop exits.
- The final answer is returned.

---

## 6. Key Design Patterns and Architectural Choices

**Structured JSON at every layer boundary.** Instead of passing dicts between layers, the system uses Pydantic models (`Goal`, `Observation`, `DecisionOutput`, `MemoryItem`, `Artifact`, `ToolCall`). This means every layer can validate its inputs on arrival, and mistakes surface as validation errors rather than silent downstream failures.

**LLM calls at precisely defined moments.** Three LLM calls happen per full iteration in the common case: one in Perception (to update the goal list), one in Decision (to choose an action or produce an answer), and one in Memory's `remember()` path (to classify the user's initial query — but this only happens once at run start, not every iteration). Tool outcome writes and all artifact operations are LLM-free. The gateway's routing system makes additional smaller LLM calls to classify each request tier, but these are cheap and asynchronous from the agent's perspective.

**Zero-LLM deterministic fallbacks everywhere.** Every LLM-dependent path has a fallback: if the Memory classifier fails, `_fallback_remember()` takes over; if the gateway embedding endpoint fails, the item is persisted without a vector and stays reachable via keyword search; if all gateway providers are unavailable, `ensure_gateway()` raises early. The system degrades gracefully rather than crashing.

**Content-addressed deduplication for artifacts.** Storing blobs by SHA-256 hash means that if the same web page is fetched twice, only one copy exists on disk. The agent can call `fetch_url` on the same URL repeatedly without growing storage.

**Process isolation for tools.** Running the MCP server as a separate process means a crashing tool cannot take down the agent. It also means tools can run blocking or async operations independently. The MCP protocol over stdio is language-agnostic — the server could be replaced with one written in any language.

**Sliding-window chunking for document indexing.** When `index_document` is called, it splits the document into overlapping chunks (default 400 words with 80 words of overlap). The overlap ensures that context at the boundary between chunks is not lost. This is described explicitly in the code as a heuristic placeholder — semantic chunking (splitting at meaningful boundaries) is planned for Session 8.

---

## 7. How to Run and Extend the System

**Running the agent:**
```
uv run agent7.py "Your question here"
```

Requirements: a `.env` file in the `Lecture 7/` directory containing at least `TAVILY_API_KEY` for web search. The gateway must be running, or the path issue in `gateway.py` must be resolved (see Section 8).

**Running the tests:**
```
uv run pytest -v test_mcp_server.py
```

Tests marked `@pytest.mark.network` require internet access. Tests marked `@pytest.mark.embed` require the gateway to be running.

**Clearing memory between runs:**
Call `memory.clear()` to wipe `state/memory.json` and both FAISS index files. This is useful when testing with fresh state.

**Adding a new tool:**
1. Add a function decorated with `@mcp.tool()` in `mcp_server.py`. FastMCP handles registration automatically.
2. The new tool appears in the next `session.list_tools()` call and is immediately available to Decision without any changes to other layers.

**Adding a new memory kind:**
1. Add the new kind to the `MemoryKind` literal type in `schemas.py`.
2. Decide whether it should be embeddable. If yes, add it to `_EMBEDDABLE_KINDS` in `memory.py`.
3. Add a write path in `memory.py` — either extend `remember()`, add a new function, or use `add_fact()` as a template.

**Swapping the embedding model:**
This is a breaking change. Every item currently in `state/memory.json` that has an `embedding` field was computed by the current model. If you change the model at the gateway level, the old embeddings become meaningless. Run `memory.clear()` first, then re-index any documents that were previously indexed.

---

## 8. What Is Currently Built vs. What Is Not

**Fully working:**

- The five-layer pipeline loop (`memory.read` → `perception.observe` → `decision.next_step` → `action.execute` → `memory.record_outcome`)
- All 11 MCP tools: web search (Tavily/DuckDuckGo), URL fetching (crawl4ai), time lookup, currency conversion, sandbox file CRUD, `index_document`, `search_knowledge`
- Vector memory with FAISS (`VectorIndex`, `_vector_search`)
- Keyword search fallback (`_keyword_search`)
- Two write paths: LLM-classified writes and zero-LLM deterministic writes
- Content-addressed artifact store
- LLM Gateway V7 with the new `/v1/embed` endpoint
- The gateway's multi-provider failover, tiering, and rate limiting

**Present but broken or stale:**

- **Gateway auto-start path is broken.** `gateway.py` computes the gateway directory as `parents[2] / "llm_gatewayV7"`, which resolves to `/Users/aryamanchandak/Documents/llm_gatewayV7`. This path does not exist on disk. The actual gateway code lives at `Lecture 7/llm_gatewayV7/`. If the gateway is already running when the agent starts, this bug is invisible. If the gateway is not running, `ensure_gateway()` raises a `RuntimeError`. The fix is a one-line correction in `gateway.py`.

- **`test_list_dir` is stale.** The test at line 126 of `test_mcp_server.py` asserts that the result of `list_dir` is a `list`. But `list_dir` was changed (with a comment explaining why) to return a `dict` containing `count`, `names`, and `entries`. The test will fail if run. The fix is to update the assertion to expect a dict.

- **Tests do not cover `index_document` or `search_knowledge`.** The test file header says "S6 MCP server" — it was carried forward from the previous session but never extended to cover the two new S7 tools. These tools are exercised only through full agent runs, not via isolated unit tests.

**Explicitly deferred to future sessions:**

- **Hybrid retrieval with RRF.** The current system uses either vector search or keyword search, not both simultaneously. Reciprocal Rank Fusion (combining both result lists) is planned but not yet implemented — noted in `memory.py`.
- **Semantic chunking.** `index_document` currently splits by word count with a fixed overlap. Splitting at semantically meaningful boundaries (paragraph breaks, section headers) is noted in `mcp_server.py` as planned for Session 8.
- **Summarizer Agent for HUGE requests.** The gateway's router rejects any request estimated at over 8,000 tokens with a 503 and a message saying "Summarizer Agent (V7, not yet implemented)."

---

## 9. Current State Assessment

This is a mature course prototype. The core loop is coherent and the layered architecture is cleanly expressed — the Pydantic contracts between layers are the strongest design choice in the codebase, making each component independently testable and understandable. The Session 7 additions (FAISS vector memory, `index_document`, `search_knowledge`) are complete and integrated, though they sit on acknowledged heuristics (fixed-size chunking) with better versions planned.

The gateway path bug is the most consequential fragility for someone picking this up fresh — if the gateway is not already running, the agent fails at startup with an unhelpful error. The stale `test_list_dir` test is a low-impact issue but worth fixing before anyone uses the test suite to validate changes.

The absence of tests for the two new S7 tools is a genuine gap. A developer extending the knowledge-base features has no automated way to verify the indexing and search cycle works correctly end-to-end.

The explicit "future session" markers throughout the codebase (in docstrings and inline comments) are a good teaching pattern — they make the architecture's evolution legible without cluttering the current implementation.

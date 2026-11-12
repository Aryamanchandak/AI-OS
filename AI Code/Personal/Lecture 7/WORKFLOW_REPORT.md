# EAG V3 Session 7 Agent — Detailed Workflow Report

## High-Level Summary

The Session 7 agent is a multi-turn LLM agent that decomposes a user query into
goals, achieves each goal through LLM reasoning or tool calls, and persists
knowledge in a hybrid vector+keyword memory store. The execution is driven by a
`for` loop in `agent7.py` that cycles through five typed layers on every
iteration: **Memory Read → Perception → Decision → Action → Memory Write**.
Termination is NOT controlled by when Decision produces an answer; it is
controlled by when Perception declares all goals done.

Two separate Python processes share a common disk state:
- The **agent process** (agent7.py) runs the loop and LLM calls.
- The **MCP subprocess** (mcp_server.py) runs tool logic in a child process
  over a stdio JSON-RPC pipe. It imports `memory` and `artifacts` directly
  and writes to the same `state/` folder on disk.

---

## 1. Entry Point

**File:** `agent7.py:164-170`

```python
def main() -> None:
    query = " ".join(sys.argv[1:]) or "What is the current time in Asia/Tokyo ..."
    asyncio.run(run(query))

if __name__ == "__main__":
    main()
```

Invocation:
```
uv run agent7.py "What is the current time in Tokyo and Bangalore?"
```

`main()` takes the CLI arguments, collapses them into a single query string,
and hands it to Python's event loop via `asyncio.run(run(query))`. Everything
from this point runs inside a single `asyncio` event loop.

---

## 2. Startup and Gateway Boot (`run()` — agent7.py:60)

**Step 1 — Ensure the LLM Gateway is running.**

`ensure_gateway()` (`gateway.py:33`) sends a GET to `http://localhost:8107/v1/routers`.
If it gets a response, the gateway is already up. If not, it launches
`llm_gatewayV7/main.py` as a detached subprocess via `subprocess.Popen` and
polls in a 1-second loop for up to 45 seconds. The gateway is a FastAPI server
that wraps multiple LLM providers (Gemini, Groq, Nvidia, Cerebras, etc.) behind
a unified `/v1/chat` and `/v1/embed` endpoint.

```
gateway.py:33-54
  → _is_up()           GET /v1/routers (2s timeout)
  → if not up:
      subprocess.Popen(["uv", "run", "main.py"], cwd=GATEWAY_V7_DIR)
      polls every 1s up to 45s
```

**Step 2 — Classify and persist the user query in memory.**

```python
memory.remember(query, source="user_query", run_id=run_id)   # agent7.py:71
```

`memory.remember()` (`memory.py:223`) calls the LLM gateway's `/v1/chat` to
classify the raw query text into a `MemoryItem`:
- `kind` ∈ {fact, preference, tool_outcome, scratchpad}
- `descriptor` — a one-line human-readable summary
- `keywords` — 3-8 search tokens
- `value` — structured payload (falls back to `{"raw": query}` if classifier
  returns empty value — memory.py:246-249)

After classifying, it calls `gateway.embed()` (`memory.py:258-259`) which POSTs
to `/v1/embed`. The returned float vector is stored on the `MemoryItem` and the
item is appended to `state/memory.json` AND to the FAISS index at
`state/index.faiss` (memory.py:186-196).

This means when iter 1 starts and calls `memory.read(query)`, the query's own
memory item is already in the index and can be retrieved as a hit.

**Concrete data at this stage (example query):**
```json
{
  "id": "mem:a1b2c3d4",
  "kind": "fact",
  "keywords": ["tokyo", "bangalore", "time", "difference", "hours"],
  "descriptor": "User query: current time in Asia/Tokyo and Asia/Kolkata, difference in hours",
  "value": {"raw": "What is the current time in Asia/Tokyo and Asia/Kolkata?..."},
  "embedding": [0.032, -0.017, ...],   // 768 or 1536 floats
  "source": "user_query",
  "run_id": "a3f9b2e1"
}
```

**Step 3 — Launch the MCP subprocess and discover tools.**

```python
server_params = StdioServerParameters(command=sys.executable, args=[str(MCP_SERVER)])
async with stdio_client(server_params) as (read, write):
    async with ClientSession(read, write) as session:
        await session.initialize()
        mcp_tools = (await session.list_tools()).tools
```

`stdio_client` launches `mcp_server.py` as a child process and opens a
bidirectional stdio pipe. `session.initialize()` handshakes the MCP protocol.
`list_tools()` asks the server to enumerate all registered tools. The server
`mcp_server.py` registered 11 tools at module level using `@mcp.tool()`:

```
web_search, fetch_url, get_time, currency_convert,
read_file, list_dir, create_file, update_file, edit_file,
index_document, search_knowledge
```

`_mcp_tools_for_decision()` (agent7.py:48) converts these into the dict shape
the gateway's chat endpoint accepts as `tools`:
```json
[
  {
    "name": "get_time",
    "description": "Current time in a named IANA timezone...",
    "input_schema": {"type": "object", "properties": {"timezone": {"type": "string"}}}
  },
  ...
]
```

---

## 3. The Main Loop (`for it in range(1, MAX_ITERATIONS + 1)`)

Up to 20 iterations. The loop only exits early via two `break` statements
(goals all done, or no unfinished goal) or when `MAX_ITERATIONS` is reached.

```
agent7.py:87
```

```
ASCII Loop Diagram:
  ┌──────────────────────────────────────────────────────────┐
  │                    ITERATION START                       │
  │                                                          │
  │  Step A: memory.read(query, history)                     │
  │    │                                                     │
  │    ▼                                                     │
  │  Step B: perception.observe(...)  ─→ Observation         │
  │    │                                                     │
  │    ├─── all_done? ──YES──→ break (print FINAL)           │
  │    │                                                     │
  │    ├─── no unfinished? ──YES──→ break                    │
  │    │                                                     │
  │    ▼  goal = obs.next_unfinished()                       │
  │  Step C: (optional) load artifact bytes                  │
  │    │                                                     │
  │    ▼                                                     │
  │  Step D: decision.next_step(goal, hits, attached, ...)   │
  │    │                                                     │
  │    ├─── is_answer? ──YES──→ append history, continue ──┐ │
  │    │                                                   │ │
  │    ▼                                                   │ │
  │  Step E: action.execute(session, tool_call)            │ │
  │    │                                                   │ │
  │    ▼                                                   │ │
  │  Step F: memory.record_outcome(...)                    │ │
  │    │                                                   │ │
  │    ▼                                                   │ │
  │   append history ──────────────────────────────────────┘ │
  │                                                          │
  │              next iteration                              │
  └──────────────────────────────────────────────────────────┘
```

### Step A — Memory Read (`memory.read`)

**File:** `memory.py:161-172`

```python
def read(query, history=None, *, kinds=None, top_k=8):
    vec_hits = _vector_search(query, kinds=kinds, top_k=top_k)
    if vec_hits:
        return vec_hits
    return _keyword_search(query, history, kinds=kinds, top_k=top_k)
```

**Vector path:** Embeds the query via `/v1/embed` with `task_type="retrieval_query"`,
then calls `VectorIndex.search()` (vector_index.py:100). FAISS uses inner
product on L2-normalized vectors, which equals cosine similarity. Returns up to
`top_k * 2` matches then filters by kind. The FAISS index is reloaded from
`state/index.faiss` on every call to stay in sync with MCP subprocess writes
(memory.py:60-76).

**Keyword fallback:** Only used when the vector path returns nothing. Tokenizes
the query and recent history, strips stopwords, and scores each `MemoryItem` by
keyword overlap (memory.py:106-127).

**Concrete data returned (iter 1, Tokyo example):**
```python
[
  MemoryItem(
    kind="fact",
    descriptor="User query: current time in Asia/Tokyo and Asia/Kolkata...",
    keywords=["tokyo", "time", "kolkata", "difference"],
    value={"raw": "What is the current time ..."},
    artifact_id=None,
    embedding=[...]
  )
]
```

### Step B — Perception (`perception.observe`)

**File:** `perception.py:147-265`

This is the layer that **maintains goal state** across iterations. It makes one
LLM call per iteration.

```python
obs = perception.observe(query, hits, history, prior_goals, run_id)
prior_goals = obs.goals
```

**What the LLM sees:**
```
USER QUERY: What is the current time in Asia/Tokyo and Asia/Kolkata? ...
PRIOR GOALS: []          ← empty on iter 1
MEMORY HITS: [{"i": null, "kind": "fact", "descriptor": "...", "artifact_id": null}]
RUN HISTORY (last 10): []
```

The Perception system prompt (`perception.py:39-111`) instructs the LLM to:
1. On first call (PRIOR GOALS empty): decompose the query into ordered goals.
2. On subsequent calls: copy prior goal texts verbatim; mark done when RUN
   HISTORY shows completion; optionally append new goals; set `send_artifact`
   and `artifact_index` for goals that need raw bytes.

**Concrete output (iter 1, Tokyo example):**
```json
{
  "goals": [
    {"text": "Look up the current time in Asia/Tokyo", "done": false, "send_artifact": false, "artifact_index": null},
    {"text": "Look up the current time in Asia/Kolkata", "done": false, "send_artifact": false, "artifact_index": null},
    {"text": "Calculate and report the time difference in hours between Tokyo and Kolkata", "done": false, "send_artifact": false, "artifact_index": null}
  ]
}
```

The raw LLM output is validated against `_PerceptionOutput` (pydantic), then
converted to `Goal` objects with stable UUIDs (perception.py:220-249).

**The synthesis-done guard** (perception.py:231-242): If a goal's text contains
any synthesis keyword (answer, summarise, compare, tell, report, etc.) AND
`done: true` is proposed, Perception only accepts it if `history` contains a
matching `answer` event with `goal_id == gid` and text length > 60. This
prevents Perception from short-circuiting a synthesis goal on the strength of
a tool call alone. [THIS IS IMPORTANT AND SOMETHING THAT NEEDS A FURTHER LOOK]

**Artifact attachment** (perception.py:222-227, 255-264): If `send_artifact:
true` and the indexed artifact exists, `Goal.attach_artifact_id` is set.
There is also a safety net that force-attaches the most recent artifact to the
first unfinished synthesis goal if the model forgot to set `send_artifact`.

**Termination check** (agent7.py:102-109):
```python
if obs.all_done:
    break   # ALL goals done
goal = obs.next_unfinished()
if goal is None:
    break   # should not happen, defensive
```

### Step C — Artifact Attachment (optional)

**File:** `agent7.py:112-116`

```python
attached: list[tuple[str, bytes]] = []
if goal.attach_artifact_id and artifacts.exists(goal.attach_artifact_id):
    blob = artifacts.get_bytes(goal.attach_artifact_id)
    attached.append((goal.attach_artifact_id, blob))
```

`artifacts.get_bytes()` reads the binary from `state/artifacts/<sha256>.bin`.
The full bytes are passed to `decision.next_step` so the model can analyze them
without making another tool call.

### Step D — Decision (`decision.next_step`)

**File:** `decision.py:158-194`

One LLM call per iteration. The model sees:

```
GOAL:    Look up the current time in Asia/Tokyo

MEMORY HITS:
  - [fact] User query: current time in Asia/Tokyo ...
      raw: What is the current time in ...

RECENT HISTORY:
  (empty)

[ATTACHED ARTIFACTS section — only present if Perception attached bytes]
```

The call uses `temperature=0`, `tool_choice="auto"`, and passes the full tool
list. The `cache_system=True` flag hints to the gateway to cache the system
prompt across calls (Gemini's context caching).

The response from `/v1/chat` contains either:
- `tool_calls: [{"name": ..., "arguments": {...}}]` — model wants to call a tool
- `text: "..."` — model is answering directly

Decision returns a `DecisionOutput` (schemas.py:88):
```python
DecisionOutput(tool_call=ToolCall(name="get_time", arguments={"timezone": "Asia/Tokyo"}))
# or
DecisionOutput(answer="The time in Tokyo is 14:30 JST (+9h) ...")
```

**The answer-does-not-terminate rule** (agent7.py:121-130):
When `out.is_answer` is True, the answer is appended to history and `continue`
is called, NOT `break`. The loop continues to the next iteration where
Perception will read the history, find the answer event, and potentially mark
the synthesis goal done. This is the coupling between Decision and Perception's
done-gate.

```python
if out.is_answer:
    history.append({"iter": it, "kind": "answer", "goal_id": goal.id, "text": out.answer})
    final_answer = out.answer
    continue    # ← NOT break; Perception decides when done
```

### Step E — Action (`action.execute`)

**File:** `action.py:38-79`

Called only when Decision returned a tool call (not an answer).

```python
result_text, art_id = await action.execute(session, tc)
```

First, a safety check strips `art:...` handles from `path` or `url` arguments
(action.py:49-59) — Decision sometimes hallucinates artifact handles as file
paths.

Then the MCP call:
```python
result = await session.call_tool(tool_call.name, arguments=tool_call.arguments)
```

This sends a JSON-RPC message over the stdio pipe to the MCP subprocess. The
subprocess (`mcp_server.py`) executes the tool synchronously (most tools are
blocking) or asynchronously (`fetch_url` is `async def`) and returns the result
back over the pipe. The MCP library (FastMCP) handles serialization.

**Artifact threshold logic** (action.py:63-78):
If the raw result text exceeds 4096 bytes:
```python
art_id = artifacts.put(text.encode("utf-8"), content_type="text/plain",
                       source=f"mcp:{tool_call.name}", ...)
descriptor = f"[artifact {art_id}, {nbytes} bytes] preview: ..."
return descriptor, art_id
```

`artifacts.put()` (`artifacts.py:21`) SHA256-hashes the content and writes to
`state/artifacts/<hash16>.bin` plus a `<hash16>.json` metadata sidecar.
Deduplication is content-addressed.

If the result is under 4096 bytes, the full text is returned directly and
`art_id` is `None`.

**Concrete example (get_time call):**
```python
# Input tool call:
ToolCall(name="get_time", arguments={"timezone": "Asia/Tokyo"})

# MCP server returns:
{
  "iso": "2026-06-23T23:30:00+09:00",
  "human": "Tuesday, 23 June 2026 23:30:00 JST",
  "timezone": "Asia/Tokyo",
  "offset_hours": 9.0
}

# action.execute returns:
('{"iso": "2026-06-23T23:30:00+09:00", ...}', None)
# (under 4096 bytes, no artifact created)
```

### Step F — Memory Write (`memory.record_outcome`)

**File:** `memory.py:306-349`

Zero-LLM write — no classifier needed for tool outcomes since the kind is known.

```python
memory.record_outcome(
    tool_call=tc,
    result_text=result_text,
    artifact_id=art_id,
    run_id=run_id,
    goal_id=goal.id,
)
```

Builds keywords from the tool name + argument tokens (memory.py:317-323).
Builds a descriptor: `"get_time({"timezone": "Asia/Tokyo"}) -> {\"iso\": \"2026-06...\"}"`.
Embeds the descriptor via `/v1/embed`. Writes `MemoryItem` to `memory.json`
and FAISS index.

**History append** (agent7.py:148-156):
```python
history.append({
    "iter": it,
    "kind": "action",
    "goal_id": goal.id,
    "tool": tc.name,
    "arguments": tc.arguments,
    "result_descriptor": result_text[:300],
    "artifact_id": art_id,
})
```

The `history` list is in-memory only — it is NOT persisted across runs. The
FAISS-embedded `MemoryItem` records IS persistent.

---

## 4. The Full Loop — Tokyo/Kolkata Example Traced

```
ITER 1:
  memory.read: 1 hit (the user query item)
  perception: decompose → 3 goals:
    g:aaa "Look up time in Asia/Tokyo"       done=false
    g:bbb "Look up time in Asia/Kolkata"     done=false
    g:ccc "Calculate and report difference"  done=false
  decision (goal g:aaa): TOOL_CALL get_time({"timezone":"Asia/Tokyo"})
  action: → {"iso":"2026-06-23T23:30:00+09:00","offset_hours":9.0} (42 bytes < 4096)
  memory.record_outcome: writes tool_outcome MemoryItem for get_time call
  history: [{"iter":1, "kind":"action", "tool":"get_time", ...}]

ITER 2:
  memory.read: 2 hits (query item + get_time(Tokyo) outcome)
  perception: copy goals; mark g:aaa done (history has get_time Tokyo action)
    g:aaa done=true
    g:bbb done=false  ← next unfinished
    g:ccc done=false
  decision (goal g:bbb): TOOL_CALL get_time({"timezone":"Asia/Kolkata"})
  action: → {"iso":"2026-06-23T20:00:00+05:30","offset_hours":5.5}
  memory.record_outcome: writes MemoryItem for Kolkata get_time
  history: [iter1 action, iter2 action]

ITER 3:
  memory.read: 3-4 hits (query + both tool outcomes)
  perception: mark g:bbb done; g:ccc is synthesis keyword → not marked done
    unless history has answer for g:ccc with len>60
    g:aaa done=true
    g:bbb done=true
    g:ccc done=false  ← next unfinished
  decision (goal g:ccc): ANSWER
    "The current time in Tokyo is 23:30 JST (UTC+9) and in Bangalore it is
     20:00 IST (UTC+5:30). The difference is 3.5 hours — Tokyo is 3 hours
     30 minutes ahead of Bangalore."
  history.append({"kind":"answer", "goal_id":"g:ccc", "text":"The current time..."})
  continue (NOT break)

ITER 4:
  memory.read: hits include query + 2 tool outcomes + (maybe) indexed items
  perception: sees history has answer for g:ccc (goal_id matches, len>60)
    → marks g:ccc done=true
    → obs.all_done = True
  → break

FINAL: "The current time in Tokyo is 23:30 JST..."
```

---

## 5. How the MCP Server Fits In

```
agent7.py process                    mcp_server.py process
─────────────────                    ─────────────────────
asyncio event loop                   mcp.run(transport="stdio")

stdio_client spawns ──────────────→  sys.stdin / sys.stdout (JSON-RPC)
ClientSession.initialize() ◄──────── MCP handshake response
list_tools() ◄────────────────────── 11 tool descriptors
call_tool("get_time", ...) ────────→ get_time() executes
                           ◄──────── {"iso":"...", "offset_hours":9.0}

# For index_document / search_knowledge:
call_tool("index_document", ...) ──→ _chunk_text()
                                      _memory.add_fact() ←── writes memory.json
                                      → embeds each chunk via gateway.embed()
                                      → VectorIndex.add() + persist()
                           ◄──────── {"chunks_indexed": 5}

# SHARED STATE: both processes read/write the same files:
#   state/memory.json       ← MemoryItem records
#   state/index.faiss       ← FAISS vector index
#   state/index_ids.json    ← FAISS row→id mapping
#   state/artifacts/*.bin   ← artifact blobs
```

The MCP server imports `memory` and `artifacts` directly at module level
(`mcp_server.py:38-41`). It does NOT communicate with the agent over memory —
both processes use the disk files as the shared medium. This is why
`memory._index()` reloads from disk every call rather than caching in process.

**Tool categories and what they touch:**

| Tool             | Transport   | External System         | Writes to disk?         |
|------------------|-------------|-------------------------|-------------------------|
| web_search       | HTTP        | Tavily / DuckDuckGo API | usage.json only         |
| fetch_url        | HTTP+crawl4 | Target URL (headless)   | No                      |
| get_time         | None        | System clock + zoneinfo | No                      |
| currency_convert | HTTP        | frankfurter.dev API     | No                      |
| read_file        | Filesystem  | sandbox/                | No                      |
| list_dir         | Filesystem  | sandbox/                | No                      |
| create_file      | Filesystem  | sandbox/                | sandbox/ file           |
| update_file      | Filesystem  | sandbox/                | sandbox/ file           |
| edit_file        | Filesystem  | sandbox/                | sandbox/ file           |
| index_document   | Memory svc  | FAISS + memory.json     | state/index.faiss + .json |
| search_knowledge | Memory svc  | FAISS + memory.json     | No (read only)          |

---

## 6. The LLM Gateway Internals

All LLM calls in the agent process go through `LLM().chat()` or `embed()` which
POST to `http://localhost:8107/v1/chat` and `/v1/embed` respectively.

**`/v1/chat` flow** (main.py:268):
1. If `auto_route` is set (perception uses `"perception"`, decision uses
   `"decision"`, memory uses `"memory"`), a **router LLM** is called first with
   a stripped sample of the prompt. It outputs one of: `TINY`, `LARGE`, `HUGE`.
2. `HUGE` (>8000 estimated tokens) → 503 error (not yet supported).
3. `TINY` → prefer fast small providers: `[github, openrouter, groq, nvidia, cerebras, gemini, ollama]`.
4. `LARGE` → prefer long-context providers: `[gemini, groq, nvidia, cerebras, github, openrouter, ollama]`.
5. Failover across the tier's list until one provider succeeds.
6. If `response_format` specifies a JSON schema, the response text is validated
   against it via `Draft202012Validator` (main.py:259-265).
7. The structured parse result is returned as `reply["parsed"]`.

**Important:** `LLM().chat()` is blocking `httpx.post` (client.py:34). There is
no `await` on this call. So inside the `asyncio` event loop, every LLM call in
`perception.observe()`, `decision.next_step()`, and `memory.remember()` stalls
the event loop for the duration of the HTTP round trip. Only actual MCP I/O
(`session.call_tool()`) is properly awaited.

**`/v1/embed` flow** (main.py — embedders section):
Calls the configured embedding provider (e.g., `text-embedding-004` on Gemini)
and returns `{embedding: [...], dim: 768, model: "...", latency_ms: ...}`.

---

## 7. Data Schema at Each Boundary

### Query enters the system:
```
str  →  memory.remember()  →  MemoryItem (persisted in memory.json + FAISS)
```

### Memory read:
```
query: str, history: list[dict]  →  memory.read()  →  list[MemoryItem]
```

### Perception output:
```
Observation(goals=[
  Goal(id="g:aaa", text="...", done=bool, attach_artifact_id=str|None),
  ...
])
```

### Decision input:
```
goal: Goal
hits: list[MemoryItem]
attached: list[tuple[str, bytes]]   # (artifact_id, raw_bytes)
history: list[dict]
mcp_tools: list[dict]               # tool descriptors
```

### Decision output:
```
DecisionOutput(
  answer="..."       # XOR
  tool_call=ToolCall(name="get_time", arguments={"timezone":"Asia/Tokyo"})
)
```

### Action output:
```
(result_text: str, art_id: str|None)
# art_id is set when len(result_text.encode()) > 4096
```

### Memory write (tool outcome):
```
MemoryItem(
  kind="tool_outcome",
  descriptor="get_time({...}) -> {iso:...}",
  keywords=["get_time", "tokyo", "asia"],
  value={"tool": "get_time", "arguments": {...}, "result_preview": "..."},
  artifact_id=None | "art:abc...",
  embedding=[...],     # embedded from descriptor
)
```

### History entry (in-memory, not persisted):
```python
# Tool call iteration:
{"iter": 1, "kind": "action", "goal_id": "g:aaa",
 "tool": "get_time", "arguments": {"timezone": "Asia/Tokyo"},
 "result_descriptor": '{"iso": "2026-06-23T23:30..."}',
 "artifact_id": None}

# Answer iteration:
{"iter": 3, "kind": "answer", "goal_id": "g:ccc",
 "text": "The current time in Tokyo is 23:30 JST ..."}
```

---

## 8. Document Indexing and Knowledge Search (`index_document` / `search_knowledge`)

These two tools extend the agent with a persistent corpus:

**`index_document("notes/spec.md")`** (mcp_server.py:343):
1. Reads the file from `sandbox/` (or an artifact if path starts with `art:`).
2. Splits into sliding-window word chunks: default 400 words, 80-word overlap.
3. For each chunk, calls `_memory.add_fact()` which embeds the chunk's
   descriptor via `/v1/embed` and writes a `fact` MemoryItem to `memory.json`
   + FAISS.
4. Returns `{"chunks_indexed": N}`.

**`search_knowledge("authentication flow", k=5)`** (mcp_server.py:376):
Calls `_memory.read(query, kinds=["fact"], top_k=k)` — the same vector search
as the main loop's `memory.read`, but restricted to `fact` kind. Returns chunks
with provenance.

**Why separate from `read_file`?** `read_file` reads the file once and the
content stays in the MCP result, which is stored as a single large `tool_outcome`.
`index_document` chunks the content and embeds each chunk individually, making
the whole corpus semantically searchable in future iterations and future runs.

---

## 9. Async Pattern Notes

The agent uses `asyncio` (agent7.py:166) but the async usage is narrow:

| Call site                          | Awaited? | Reason                            |
|------------------------------------|----------|-----------------------------------|
| `stdio_client()`                   | Yes      | subprocess I/O async context mgr  |
| `ClientSession()`                  | Yes      | MCP async context mgr             |
| `session.initialize()`             | Yes      | MCP protocol async                |
| `session.list_tools()`             | Yes      | MCP async request                 |
| `action.execute()`                 | Yes      | wraps `session.call_tool()` await |
| `session.call_tool()`             | Yes      | MCP async tool dispatch           |
| `perception.observe()`             | NO       | calls blocking `httpx.post`       |
| `decision.next_step()`            | NO       | calls blocking `httpx.post`       |
| `memory.remember/read/record`      | NO       | calls blocking `httpx.post`       |

The MCP subprocess's `fetch_url` is an `async def` tool (`mcp_server.py:192`)
handled properly by FastMCP, but the agent side only sees a `call_tool()` await
regardless.

---

## 10. State Files — What Lives Where

```
state/
  memory.json          ← List of all MemoryItem records (facts, prefs, tool outcomes)
  index.faiss          ← FAISS IndexFlatIP binary (cosine similarity over embeddings)
  index_ids.json       ← Parallel list: FAISS row integer → MemoryItem id string
  artifacts/
    <sha256hex16>.bin  ← Raw bytes of large tool results (>4096 bytes)
    <sha256hex16>.json ← Artifact metadata (id, content_type, size, descriptor)

sandbox/
  (user-created files live here; scoped to this dir by _safe() in mcp_server.py)

usage.json             ← Monthly Tavily/DuckDuckGo call counters
```

---

## 11. Branches and Error Handling

### Gateway unavailable
`ensure_gateway()` raises `RuntimeError` if the gateway doesn't start within
45 seconds (gateway.py:53). This propagates up and kills the run.

### Memory classifier LLM fails
`memory.remember()` catches all exceptions from `_llm_classify()` and falls
back to `_fallback_remember()` (memory.py:238), which uses naive token
extraction instead of the LLM classifier. The item is still embedded and
persisted.

### Embedding fails
`_try_embed()` (memory.py:79-87) catches all exceptions and returns `None`.
Items with `embedding=None` are persisted to `memory.json` but never added to
the FAISS index, so they are only reachable via the keyword fallback path.

### Tool call with artifact handle as path/url
`action.execute()` intercepts this before calling the MCP server (action.py:49)
and returns an error message as `result_text` with `art_id=None`. This error
message enters history and Perception/Decision can correct on the next iteration.

### Decision returns neither answer nor tool call
`decision.py:185-194`: if `tool_calls` is empty and `text` is empty, the
`DecisionOutput(answer="")` would be treated as an answer with an empty string.
In practice the model always returns something; there is no explicit guard here.

### Perception emits no goals
`perception.py:187`: if `parsed.goals` is empty or the LLM call fails entirely,
falls back to `Observation(goals=[Goal(id=new_id("g"), text=query)])` — one
umbrella goal matching the original query.

### `index_document` on empty content
Returns `{"chunks_indexed": 0, "warning": "empty content"}` without writing
anything (mcp_server.py:347).

### File sandbox escape
`_safe(path)` (mcp_server.py:57-62) resolves the path and checks that it is
inside `SANDBOX`. Raises `ValueError` on escape attempt.

### Tavily quota
`_under_cap()` checks `usage.json` before each Tavily call. If over 950/month,
DuckDuckGo is used instead. DuckDuckGo tries three backends: "auto", "html",
"lite" in order (mcp_server.py:121-125).

---

## 12. Design Decisions Highlighted in the Code

1. **Goals by position, not by id in LLM output** (perception.py:24-28):
   `_GoalDelta` has no `id` field. IDs are assigned based on position in the
   output array, preserving goal identity across iterations without trusting
   the LLM to remember an opaque string.

2. **Artifact bytes never enter the Perception context** (perception.py:8-11):
   Perception sees handles and descriptors only. It sets `attach_artifact_id`
   to signal the outer loop to fetch the bytes, which then pass to Decision.
   This keeps the Perception prompt small.

3. **Content-addressed artifact storage** (artifacts.py:21-37):
   `artifacts.put()` SHA256-hashes content and skips the write if the hash
   already exists. Re-fetching the same URL twice produces one artifact.

4. **Zero-LLM tool outcome recording** (memory.py:306):
   Tool outcomes skip the classifier call because the kind is structurally
   known. Only the embedding costs a gateway call.

5. **Reload-from-disk FAISS** (memory.py:60-76):
   No cache between agent loop and MCP subprocess. Both write to the same files,
   so the index is always loaded fresh. At S7 scale this is fine; the comment
   flags this as a deliberate choice.

6. **Goal-count invariant** (perception.py:198-218):
   Prior goals are never dropped or reordered. New goals can only be appended.
   Duplicates in appended goals are deduplicated by lowercased text to prevent
   `temp=1.0` from adding the same discovery goal twice.

# 02 — Agent Database Read Access

Moved here from `To Do/Ingestion Pipeline to do/04-agent-facing-database-read-access.md`
(now a pointer stub), per Aryaman's comment: *"yes we need to make it, but
you can put the plan outside this folder."* It belongs with the AI Agent
because the AI Agent is the first real consumer.

**Status: detailed plan, ready to start** once Gateway Plan 07 is committed.
It does not depend on any ingestion Stage A item.

## The workflow that makes this concrete

The old scoping doc's Decision 1 was "name one real agent workflow that is
blocked on this". It is now answered:

**The AI Agent** (`AI Agent/src/agent/`) already queries a knowledge graph
and a vector store today, through the personal, out-of-repo
`~/Documents/AI Code/mcp_server` (copy in
`Original Code/AI Code/mcp_server/`):

| Old `mcp_server` tool | Function(s) | Store |
|---|---|---|
| `knowledge_graph/graph` | `kg_search_concepts(query, limit)`, `kg_get_concept(node_id)`, `kg_neighbors(node_id, direction, relation)`, `kg_reachable(node_id, direction, max_hops)`, `kg_edges_for_node(node_id, direction, relation)` | Neo4j |
| `vector_db/search` | `vector_db_search(...)`, `vector_db_get(...)` | Chroma |
| `documents/annual_report` | document Q&A | files |

`01-agent-under-gateway-plan.md` Decision 2, Option B, asks whether these
should become in-process calls into Gateway domains. **This plan is how
that happens.** It replaces those tools with ones backed by the AI OS
databases in `Database/neo4j`, `Database/chroma` and `Database/sqlite`,
which ingestion writes.

## What already exists to build on (verified 2026-09-27)

Ingestion's store classes already have read methods. This plan exposes them
and does not write new query logic:

- `gateway/src/gateway/ingestion/kg/kg_store.py`: `get_node`,
  `search_by_name`, `neighbors`, `reachable`, `edges_for_node`,
  `claims_for_identity`, `identity_expansion_terms`. These are a
  near-exact match for the old `kg_*` tools.
- `gateway/src/gateway/ingestion/vector/vector_store.py`: `search(collection,
  query, top_k, where)` (embeds the query through the Gateway embedding
  profile, so logging holds) and `get(collection, where=…)`.
- `gateway/src/gateway/ingestion/content_store.py`: only generic
  `rows(table)` / `count(table)` today. **New read queries are needed
  here** (source by id, highlights for a source, claims for a source,
  recent ingests).
- Every envelope carries an `access_policy.classification` of `private`,
  `shared` or `public` (`models.py:23`). This is useful for access scoping
  later.

## Decisions, with defaults now that the use case is known

### D1 — Query interface: named templates per store (no raw Cypher/SQL)

The old tools are already templates, and the agent works with them. So:

| New tool | Backed by | Notes |
|---|---|---|
| `kg_search` | `KGStore.search_by_name` | `limit` ≤ 50 |
| `kg_get` | `KGStore.get_node` | |
| `kg_neighbors` | `KGStore.neighbors` | optional `relation` filter |
| `kg_paths` | `KGStore.reachable` | `max_hops` capped at 4 (the old default of 10 is too expensive) |
| `kg_edges` | `KGStore.edges_for_node` | |
| `kg_claims` | `KGStore.claims_for_identity` | New capability the old tools lacked: claims with evidence |
| `vector_search` | `VectorStore.search` | `top_k` ≤ 20 |
| `vector_get` | `VectorStore.get` | |
| `content_source` | new `content_store` read | Source record + provenance |
| `content_highlights` | new `content_store` read | Highlights / evidence for a source |
| `content_recent` | new `content_store` read | "What did I ingest this week?" |

Every result includes provenance (source record id and origin) so the agent
can cite where a fact came from.

> **Aryaman's call:** _______________ (default: the templates above, no raw query)

### D2 — Read-only enforcement: both layers where the store allows it

- **Neo4j:** open sessions with `default_access_mode=READ` and use only
  `execute_read`. If the Neo4j edition supports roles (Enterprise/Aura), add
  a read-only user. **Check which edition runs in `Database/neo4j`**;
  Community has no role-based access control, so there the session mode
  plus templates are the enforcement.
- **SQLite content DB:** open a separate connection with
  `file:…?mode=ro` (URI), which enforces read-only at the database layer.
  Never reuse ingestion's write connection.
- **Chroma:** there is no read-only credential. Enforcement is at the
  application layer: the read module only calls `query` and `get`, and a
  test greps for `upsert|delete|add`.

> **Aryaman's call:** _______________

### D3 — Access boundaries: uniform for now, classification-aware later

Everything ingested today is Aryaman's own data, and the agent is Aryaman's
own agent, so start with **uniform access**. Include `classification` in
results, and leave a single filter hook (`allowed_classifications`,
defaulting to all) so scoping per agent is a config change later, not a
redesign.

> **Aryaman's call:** _______________

### D4 — Where it lives: a separate read domain inside Gateway

```text
gateway/src/gateway/knowledge/        # NEW read domain; imports nothing that writes
├── graph.py        # read-only wrappers over KGStore (READ sessions)
├── vectors.py      # read-only wrappers over VectorStore.search/get
├── content.py      # new read-only SQL over the content DB (mode=ro)
├── models.py       # typed results with provenance
└── limits.py       # caps, timeouts
gateway/src/gateway/mcp/tools/knowledge.py   # MCP tools (server from ingestion doc 03)
```

- It is **not inside `gateway/ingestion/`**. The different consumer and
  threat model argument from the old scoping doc still holds. It reuses the
  store *classes* but owns its own read-only connections.
- The MCP server is the one planned in
  `To Do/Ingestion Pipeline to do/03-mcp-surface.md`. That doc owns
  submits, this one owns reads, and they share one server and one
  transport.
- Optionally, `/api/knowledge/*` REST routes can be added under Gateway
  auth, so the shell can later get a "search my knowledge" screen for free.

> **Aryaman's call:** _______________

### D5 — Concurrency with ingestion runs

Reads can happen while ingestion is writing.
- Neo4j handles this natively.
- SQLite: enable WAL on the content DB so readers don't block the writer.
  This is a one-line pragma, but it touches ingestion's DB, so it needs
  confirming against the Plan 06 "preserve data semantics" rule.
- Chroma: a `PersistentClient` shared in-process is fine. Separate
  processes on the same directory are not. The read domain therefore runs
  inside the Gateway process, and the MCP tools are served over HTTP from
  that process (see `03-mcp-surface.md` Decision 2). stdio clients go
  through a thin bridge that opens no database. Once the agent is a Gateway
  domain, it calls `gateway.knowledge.*` in-process.

> **Aryaman's call on enabling WAL:** _______________

## Guardrails

- Result caps (above), a query timeout of 5 s, and `max_hops` ≤ 4.
- Every call is written to Gateway's audit log (tool, arguments,
  row count, duration).
- `vector_search` embeds through the Gateway embedding profile, so the
  "every LLM/embedding call is logged" invariant from Gateway Plan 04
  holds.

## Work packages

1. `gateway/knowledge/`: graph and vector wrappers, which are thin over the
   existing store methods.
2. `content.py`: the three new read queries, with tests against a fixture
   DB.
3. Read-only connection plumbing (Neo4j READ sessions, SQLite `mode=ro`),
   plus the Neo4j edition check.
4. `mcp/tools/knowledge.py`: register the tools on the shared MCP server.
5. **Confirm the data source first.** Check whether the old `mcp_server`
   `knowledge_graph` / `vector_db` tools read the same Neo4j database and
   Chroma directory that ingestion writes (`Database/neo4j`,
   `Database/chroma`), or a separate store. If they are different, the
   cut-over changes what the agent knows, so decide whether that data needs
   migrating or can be dropped. This hasn't been verified yet.
6. AI Agent cut-over (with `01-agent-under-gateway-plan.md` Phase 5): point
   `action.py` at the Gateway MCP server for knowledge tools. Retire the old
   `knowledge_graph`, `vector_db` and `documents` tool dependency.
7. Optional: `/api/knowledge/*` REST routes.

## Done when (checkable)

- `grep -rnE "execute_write|upsert|delete|INSERT|UPDATE" gateway/src/gateway/knowledge/`
  returns nothing.
- A test shows that a write attempted through the SQLite read connection
  raises `sqlite3.OperationalError: attempt to write a readonly database`.
- An MCP client test lists the knowledge tools. `kg_search` on a seeded
  fixture graph returns results with provenance.
- `grep -rn "AI Code" "AI Agent/src"` has no hits for `mcp_server`
  knowledge tools after the cut-over.
- Every read tool call appears in the audit log.

## Non-goals

- Any write path. Agents submit content via ingestion's `ingest_submit`
  (doc 03), never here.
- Natural-language-to-Cypher.
- The external `mcp_server` tools (finance, news, media, research,
  utility). Those are `01-agent-under-gateway-plan.md` Decision 2's call.

## Aryaman's comments


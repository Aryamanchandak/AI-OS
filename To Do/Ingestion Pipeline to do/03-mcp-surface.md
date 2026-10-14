# 03: Letting AI Agents Hand Content to Ingestion (MCP)

> **Status 2026-10-13: comes after the breakup (plan 01).** See the
> roadmap for the new order.

Stage A, item 4. **Start now.** This document is also the map of every
MCP-related piece of work in AI OS.

## What MCP is, in one paragraph

MCP is a standard way to give an AI agent a menu of "tools" it can
choose to call. Each tool is a named action with defined inputs. Your
AI Agent already works this way; it calls tools on an MCP server.

## Two different things an agent might want

| | What the agent does | Example | Main risk | Planned in |
|---|---|---|---|---|
| **Submit** | Hands ingestion new content | "Add this note from our conversation to my knowledge base" | A bad fact lands in the graph | **This document** |
| **Read** | Asks what's already stored | "What do I know about Keynes?" | Expensive queries, seeing too much | `To Do/AI Agent to do/02-agent-database-read-access.md` |

## How a submission works

1. The agent calls **"submit"** with some text and says where it came
   from.
2. Ingestion **only stores it** and replies "got it" with a tracking
   number. No LLM work happens at this point.
3. Later, with the next ingestion run, the submission is processed
   **together with everything else waiting**, in batches. That means fact
   extraction, the problem checker, the A1 clerk, and you if needed.
4. The agent can ask **"what happened to my submission?"** and gets back
   one of: waiting, in review, stored, or rejected.

**Why store first and process later:** your rule is that processing one
thing at a time is too expensive. That applies to agents exactly as it
applies to automatic triggers.

**Agents never write to the databases directly.** An agent is just one
more source, like Obsidian or the drop folder. Its content is always
flagged for review. The clerk can still clear it, but it never takes the
"no problems, auto-approve" shortcut.

## The tools ingestion offers

| Tool | What it does |
|---|---|
| Submit | Store some text for the next run; returns a tracking number |
| Status | Where is my submission? |
| Review queue | How many facts are waiting for Aryaman? Counts only, read-only. |

> **Decision 1: are these three tools the right set?** The old idea of
> six tools (a write and a read for each database) is withdrawn. The
> writes would have skipped review, and the reads belong to the agent
> read plan.
> **Aryaman's call:** _______________

### Safeguards

- Agent content is always flagged, so it always goes through review.
- There are limits on how much an agent can submit per call and per
  minute.
- Every submission records which agent sent it and when.

## Where the MCP server lives

There is **one MCP server for all of AI OS, run inside Gateway.** Both
ingestion's tools and the agent read tools are added to it. The tools are
thin: they pass the request to existing ingestion code and hold no logic
of their own. Every call goes through Gateway's login check and is
recorded in its audit log.

> **Decision 2: how do agents connect?** Recommended: over HTTP to Gateway
> only. The databases must only ever be opened by the Gateway process;
> two processes opening the same vector store is unsafe. For an agent
> that can only use the older "subprocess" style of MCP, add a tiny
> forwarder that passes calls on to Gateway and never opens a database
> itself. Once the AI Agent moves inside Gateway, it can call the tools
> directly.
> **Aryaman's call:** _______________

## Every MCP-related item in AI OS

| # | Work | Planned in | Status |
|---|---|---|---|
| 1 | Ingestion submit tools and the shared MCP server | This document | Stage A, start now |
| 2 | Agent read tools (graph, vector, content queries) | `To Do/AI Agent to do/02-agent-database-read-access.md` | Plugs into the same server |
| 3 | The AI Agent's reliance on your personal `mcp_server` | `To Do/AI Agent to do/01-agent-under-gateway-plan.md` | Its knowledge tools are replaced by #2; the rest (finance, news and so on) are decided in that plan |
| 4 | "Keep GLC parts swappable, as if behind MCP" | Gateway program roadmap and Plan 04 | A design rule, not work to build |
| 5 | "Every LLM call is logged", even through MCP | Gateway Plan 04; `Future Work/observability-and-data-views.md` | A rule the tools above must follow |
| 6 | Automatic triggers using the same submit path | `05-event-driven-ingestion.md` | Stage B |

## Done when

- An agent can see exactly the three ingestion tools.
- Submitting a sentence stores it and makes **zero** LLM calls.
- After the next run, that content is flagged and waiting for review. It
  is never auto-approved.
- The forwarder, if built, contains no database code.
- The submit tool has no path to any database.
- Every tool call appears in the audit log.
- All existing ingestion tests still pass.

## Not in scope

- Read and query tools (they're in the agent read plan).
- Lots of small, specific tools. Add them only when something real needs
  them.
- Automatic triggers (plan 05).

## Where in the code

- The AI Agent's current MCP client: `AI Agent/.../cognition/action.py`
  (`ClientSession`, `session.call_tool`).
- Submit wraps `UnifiedIngestionPipeline.capture()` in
  `gateway/src/gateway/ingestion/pipeline.py` (around line 168), with
  `source_type="agent"`. Later processing is `process_pending(limit)`
  (around line 697).
- The "always flagged" rule: add a `source_is_agent` signal in
  `pipeline.py` `_build_envelope()`, the same way `source_is_page_scanner`
  is added.
- Status: store lookups in `store.py`. Review queue:
  `store.pending_reviews()`, returning counts and summaries only.
- The new server package:
  - `gateway/src/gateway/mcp/server.py`
  - `gateway/src/gateway/mcp/transport.py` (HTTP, mounted in Gateway under
    its bearer auth)
  - `gateway/src/gateway/mcp/stdio_bridge.py` (the optional forwarder)
  - `gateway/src/gateway/mcp/tools/ingestion.py`
  - `gateway/src/gateway/mcp/tools/knowledge.py` (the read tools, owned by
    the AI Agent plan)
- Add the `mcp` package to `gateway/pyproject.toml`.
- Audit logging goes through `gateway/src/gateway/audit/`.
- Settings (the limits): `IngestionConfig` in `config.py`.
- Tests: `gateway/tests/test_mcp_ingestion.py`, using a counting fake
  `ChatClient` to prove submit makes no LLM calls. Checks:
  - `grep -rnE "sqlite3|chromadb|neo4j" .../stdio_bridge.py` returns
    nothing.
  - `grep -rn "kg_store\|vector_store\|content_store" .../tools/ingestion.py`
    returns nothing.

## Aryaman's comments


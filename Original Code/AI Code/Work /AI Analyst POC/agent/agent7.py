"""agent7.py — Session 7 agent orchestrator.

The loop layout is unchanged from Session 6. The only thing that changed
underneath is the Memory service: writes now compute an embedding via the
gateway's V7 embed endpoint and append to a FAISS index; reads use vector
similarity first and fall back to keyword search when the vector path is
empty. Two new MCP tools, index_document and search_knowledge, surface
the same machinery to the model so the agent can ingest external
documents on demand.

The four typed layers:

    memory.read -> perception.observe -> decision.next_step ->
    action.execute -> memory.record_outcome

Perception is the only layer that maintains goal state across iterations.
Memory is a typed service (read / write). The artifact store carries raw
bytes; Decision sees them only when Perception attached them to the
current goal.

Run from this folder:
    uv run agent7.py "What is the current time in Tokyo and Bangalore?"
"""

from __future__ import annotations

# Load .env before any module-level env reads (e.g. gateway._API_KEY).
import os as _os
_env_path = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", ".env")
if _os.path.exists(_env_path):
    try:
        from dotenv import load_dotenv as _load_dotenv
        _load_dotenv(_env_path)
    except ImportError:
        pass

import asyncio
import json
import logging
import sys
import time
import uuid
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import action
import artifacts
import decision
import memory
import perception
from gateway import embed as _gateway_embed
from schemas import Goal

MCP_SERVER = Path(__file__).parent.parent / "mcp_server" / "mcp_server.py"
MCP_SERVER_PYTHON = Path(__file__).parent.parent / ".venv" / "bin" / "python"
MAX_ITERATIONS = 20
ITER_SLEEP_SECONDS = 2.0   # sleep between iterations to avoid TPM rate limits
MAX_REPEATED_CALLS = 3     # break loop after this many identical tool calls


def _mcp_tools_for_decision(tools) -> list[dict]:
    """Convert MCP tool descriptors into the shape the gateway expects."""
    return [
        {
            "name": t.name,
            "description": t.description or "",
            "input_schema": t.inputSchema or {"type": "object", "properties": {}},
        }
        for t in tools
    ]


async def run(query: str) -> str:
    run_id = uuid.uuid4().hex[:8]
    run_start = time.perf_counter()
    print(f"\n{'═' * 78}")
    print(f"run {run_id}  ─  query: {query}")
    print(f"{'═' * 78}")

    # Cache the query embedding once so each iteration doesn't re-embed the
    # same string. Passed through to memory.read → _vector_search.
    query_vec: list[float] | None = None
    try:
        t0 = time.perf_counter()
        query_vec = list(_gateway_embed(query, task_type="retrieval_query")["embedding"])
        print(f"[init]  query embedded ({len(query_vec)}d) in {(time.perf_counter()-t0)*1000:.0f}ms — reusing each iteration")
    except Exception as e:
        print(f"[init]  query embedding FAILED: {e} — will embed per-iteration")

    # Durable memory: classify the user's query so facts/preferences in it
    # survive into future runs. Tool outcomes get recorded later by Action;
    # the query itself only gets a memory record if we put it there now.
    try:
        t0 = time.perf_counter()
        memory.remember(query, source="user_query", run_id=run_id)
        print(f"[init]  memory.remember done in {(time.perf_counter()-t0)*1000:.0f}ms")
    except Exception as e:
        print(f"[memory.remember] skipped: {e}")

    server_params = StdioServerParameters(command=str(MCP_SERVER_PYTHON), args=[str(MCP_SERVER)])
    history: list[dict] = []
    prior_goals: list[Goal] = []
    final_answer: str = ""
    # Track recent tool calls to detect stuck loops.
    recent_tool_calls: list[str] = []

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            t0 = time.perf_counter()
            await session.initialize()
            mcp_tools = (await session.list_tools()).tools
            tools_for_decision = _mcp_tools_for_decision(mcp_tools)
            print(f"[mcp]   loaded {len(mcp_tools)} tools in {(time.perf_counter()-t0)*1000:.0f}ms: {[t.name for t in mcp_tools]}")

            for it in range(1, MAX_ITERATIONS + 1):
                iter_start = time.perf_counter()
                print(f"\n─── iter {it}/{MAX_ITERATIONS} ─────────────────────────────────────────")

                # 1. MEMORY READ
                t0 = time.perf_counter()
                hits = memory.read(query, history, query_vec=query_vec)
                t_read = (time.perf_counter() - t0) * 1000
                print(f"[memory.read]   {len(hits)} hits  ({t_read:.0f}ms)")

                # 2. PERCEPTION
                t0 = time.perf_counter()
                obs = perception.observe(query, hits, history, prior_goals, run_id)
                t_perc = (time.perf_counter() - t0) * 1000
                prior_goals = obs.goals
                for g in obs.goals:
                    flag = "✓" if g.done else "○"
                    attach = f"  attach={g.attach_artifact_id}" if g.attach_artifact_id else ""
                    print(f"[perception]    {flag} {g.id} — {g.text}{attach}")
                print(f"[perception]    done in {t_perc:.0f}ms")

                if obs.all_done:
                    print(f"\n[done] all {len(obs.goals)} goals satisfied after {it} iterations  total={( time.perf_counter()-run_start)*1000:.0f}ms")
                    break

                goal = obs.next_unfinished()
                if goal is None:
                    print(f"\n[done] no unfinished goal — stopping  total={(time.perf_counter()-run_start)*1000:.0f}ms")
                    break

                # Perception decided whether to attach an artifact.
                attached: list[tuple[str, bytes]] = []
                if goal.attach_artifact_id and artifacts.exists(goal.attach_artifact_id):
                    blob = artifacts.get_bytes(goal.attach_artifact_id)
                    attached.append((goal.attach_artifact_id, blob))
                    print(f"[attach]        {goal.attach_artifact_id} ({len(blob)} bytes)")

                # 3. DECISION
                t0 = time.perf_counter()
                out = decision.next_step(goal, hits, attached, history, tools_for_decision)
                t_dec = (time.perf_counter() - t0) * 1000

                if out.is_answer:
                    print(f"[decision]      ANSWER ({t_dec:.0f}ms): {out.answer[:200]}{'...' if len(out.answer) > 200 else ''}")
                    history.append({
                        "iter": it,
                        "kind": "answer",
                        "goal_id": goal.id,
                        "text": out.answer,
                    })
                    final_answer = out.answer
                    t_iter = (time.perf_counter() - iter_start) * 1000
                    print(f"[timing]  iter {it}: read={t_read:.0f} perc={t_perc:.0f} dec={t_dec:.0f} act=0 write=0 total={t_iter:.0f}ms")
                    continue

                # 4. ACTION
                tc = out.tool_call
                call_key = f"{tc.name}({json.dumps(tc.arguments, sort_keys=True)[:80]})"
                dup_count = recent_tool_calls.count(call_key)
                if dup_count > 0:
                    print(f"[warn]  REPEATED TOOL CALL #{dup_count+1}: {call_key} — possible stuck loop")
                if dup_count >= MAX_REPEATED_CALLS - 1:
                    print(f"[forced-answer] same tool called {MAX_REPEATED_CALLS}x — forcing Decision to answer instead of retry")
                    forced = decision.next_step(goal, hits, attached, history, tools_for_decision, force_answer=True)
                    answer_text = forced.answer if forced.is_answer and forced.answer else (
                        f"Unable to complete '{goal.text}': tool `{tc.name}` failed {MAX_REPEATED_CALLS} times. "
                        "Check that the required API key (GEMINI_API_KEY or OPENAI_API_KEY) is set and the file exists."
                    )
                    print(f"[forced-answer] → {answer_text[:200]}")
                    history.append({"iter": it, "kind": "answer", "goal_id": goal.id, "text": answer_text})
                    final_answer = answer_text
                    recent_tool_calls.clear()
                    t_iter = (time.perf_counter() - iter_start) * 1000
                    print(f"[timing]  iter {it}: read={t_read:.0f} perc={t_perc:.0f} dec={t_dec:.0f} act=0 write=0 total={t_iter:.0f}ms")
                    continue
                recent_tool_calls.append(call_key)
                if len(recent_tool_calls) > 8:
                    recent_tool_calls.pop(0)

                print(f"[decision]      TOOL_CALL ({t_dec:.0f}ms): {tc.name}({json.dumps(tc.arguments)[:120]})")
                t0 = time.perf_counter()
                result_text, art_id = await action.execute(session, tc)
                t_act = (time.perf_counter() - t0) * 1000
                preview = result_text[:200].replace("\n", " ")
                print(f"[action]        ({t_act:.0f}ms) → {preview}{'...' if len(result_text) > 200 else ''}"
                      + (f"   +{art_id}" if art_id else ""))
                if result_text.startswith("ERROR:") or result_text.lower().startswith("error executing tool"):
                    print(f"[action] ERROR RESULT — decision should handle and not repeat this call")

                # 5. MEMORY WRITE (zero-LLM for tool outcomes)
                t0 = time.perf_counter()
                memory.record_outcome(
                    tool_call=tc,
                    result_text=result_text,
                    artifact_id=art_id,
                    run_id=run_id,
                    goal_id=goal.id,
                )
                t_write = (time.perf_counter() - t0) * 1000
                history.append({
                    "iter": it,
                    "kind": "action",
                    "goal_id": goal.id,
                    "tool": tc.name,
                    "arguments": tc.arguments,
                    "result_descriptor": result_text[:300],
                    "artifact_id": art_id,
                })
                t_iter = (time.perf_counter() - iter_start) * 1000
                print(f"[timing]  iter {it}: read={t_read:.0f} perc={t_perc:.0f} dec={t_dec:.0f} act={t_act:.0f} write={t_write:.0f} total={t_iter:.0f}ms")
                await asyncio.sleep(ITER_SLEEP_SECONDS)

    run_total_ms = (time.perf_counter() - run_start) * 1000
    if not final_answer:
        print(f"[warn]  hit MAX_ITERATIONS={MAX_ITERATIONS} without a final answer — consider narrowing the query or raising the limit")
        final_answer = (
            "I was unable to produce an answer within the allowed reasoning steps. "
            "Please try rephrasing your question or breaking it into smaller parts."
        )

    print(f"\n{'═' * 78}")
    print(f"FINAL ({run_total_ms:.0f}ms total): {final_answer}")
    print(f"{'═' * 78}\n")
    return final_answer


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")
    query = " ".join(sys.argv[1:]) or "What is the current time in Asia/Tokyo and Asia/Kolkata? Tell me the difference in hours."
    asyncio.run(run(query))


if __name__ == "__main__":
    main()

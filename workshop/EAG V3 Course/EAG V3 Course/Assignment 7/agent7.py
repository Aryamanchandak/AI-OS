"""agent7.py - the loop that wires the four layers together.

Loop shape:

    PLAN -> EXECUTE -> REVIEW -> (repeat) -> done

Perception owns PLAN and REVIEW. Decision owns execution authority for a whole
block, including synthesis. Action stays a pure MCP dispatcher. Memory records
tool outcomes at the loop boundary.

Run from the repo root:
    uv run python agent7.py "What is the current time in Tokyo and Bangalore?"
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
import time
import uuid

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

import decision
import memory
import perception
from paths import MCP_SERVER
from schemas import Block, GoalResult, Review

MAX_ROUNDS = 8
# tool_outcome deliberately excluded: prior-run tool outcomes are a
# cross-run bleed risk (self-conditioning) with no reconciliation mechanism
# in this architecture. Facts/preferences carry over by default; a goal
# that explicitly needs prior tool work should request it separately.
RUN_CONTEXT_MEMORY_KINDS = ["fact", "preference"]

# How many rounds the most recent run() used. Read by the live tests.
last_run_rounds = 0


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


def _goal_order(blocks: list[Block]) -> dict[str, int]:
    order: dict[str, int] = {}
    for block in blocks:
        for goal in block.goals:
            if goal.id not in order:
                order[goal.id] = len(order)
    return order


def compose_answer(results: list[GoalResult], blocks: list[Block]) -> str:
    order = _goal_order(blocks)
    syntheses = [
        r for r in results
        if r.kind == "synthesis" and r.status == "ok" and r.output_descriptor.strip()
    ]
    syntheses.sort(key=lambda r: order.get(r.goal_id, 10_000))

    parts = [r.output_descriptor.strip() for r in syntheses]
    problem_results = [
        r for r in results
        if r.status in {"error", "capability_gap"}
    ]
    if problem_results:
        notes = []
        for r in problem_results:
            msg = (r.message or r.output_descriptor or "No detail provided").strip()
            notes.append(f"- {r.status}: {msg[:300]}")
        parts.append("Notes:\n" + "\n".join(notes))

    if parts:
        return "\n\n".join(parts)

    ok_tools = [r for r in results if r.kind == "tool" and r.status == "ok"]
    if ok_tools:
        return "Done."
    return ""


def _log_block(block: Block) -> None:
    print(f"[block] round={block.round} goals={len(block.goals)} rationale={block.rationale}")
    for goal in block.goals:
        done = "done" if goal.done else "open"
        needs = f" artifacts={goal.needs_artifact_ids}" if goal.needs_artifact_ids else ""
        print(f"[block]   {goal.id} [{done}] {goal.text}{needs}")


def _log_result(result: GoalResult) -> None:
    tc = ""
    if result.tool_call:
        tc = f" tool={result.tool_call.name} args={json.dumps(result.tool_call.arguments)[:120]}"
    art = f" artifact={result.artifact_id}" if result.artifact_id else ""
    msg = f" message={result.message[:240]}" if result.message else ""
    desc = result.output_descriptor[:260].replace("\n", " ")
    print(f"[result] {result.goal_id} {result.kind}/{result.status}{tc}{art}{msg} -> {desc}")


def _log_review(review: Review) -> None:
    verdict = "finished" if review.finished else "next_block"
    print(f"[review] verdict={verdict} findings={len(review.findings)}")
    for finding in review.findings:
        goal = f" goal={finding.goal_id}" if finding.goal_id else ""
        prop = f" propose={finding.proposed_goal_text}" if finding.proposed_goal_text else ""
        print(f"[review]   {finding.check}{goal}: {finding.detail}{prop}")
    if review.next_block:
        _log_block(review.next_block)


def _history_from_results(results: list[GoalResult]) -> list[dict]:
    history = []
    for i, result in enumerate(results[-12:], start=1):
        item = {
            "iter": i,
            "kind": result.kind,
            "goal_id": result.goal_id,
            "status": result.status,
            "result_descriptor": result.output_descriptor[:300],
            "artifact_id": result.artifact_id,
            "message": result.message,
        }
        if result.tool_call:
            item["tool"] = result.tool_call.name
            item["arguments"] = result.tool_call.arguments
        history.append(item)
    return history


async def run(query: str) -> str:
    global last_run_rounds
    run_id = uuid.uuid4().hex[:8]
    run_start = time.perf_counter()
    print(f"\n{'=' * 78}")
    print(f"run {run_id}  -  query: {query}")
    print(f"{'=' * 78}")

    try:
        t0 = time.perf_counter()
        memory.remember(query, source="user_query", run_id=run_id)
        print(f"[init]  memory.remember done in {(time.perf_counter()-t0)*1000:.0f}ms")
    except Exception as e:
        print(f"[memory.remember] skipped: {e}")

    server_params = StdioServerParameters(command=sys.executable, args=[str(MCP_SERVER)])
    blocks_so_far: list[Block] = []
    results_so_far: list[GoalResult] = []
    recent_tool_calls: list[str] = []
    final_answer = ""

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            t0 = time.perf_counter()
            await session.initialize()
            mcp_tools = (await session.list_tools()).tools
            tools_for_decision = _mcp_tools_for_decision(mcp_tools)
            print(f"[mcp]   loaded {len(mcp_tools)} tools in {(time.perf_counter()-t0)*1000:.0f}ms: {[t.name for t in mcp_tools]}")

            block: Block | None = None
            for round_i in range(MAX_ROUNDS):
                round_start = time.perf_counter()
                last_run_rounds = round_i + 1
                print(f"\n--- round {round_i}/{MAX_ROUNDS - 1} ----------------------------------------")

                t0 = time.perf_counter()
                history = _history_from_results(results_so_far)
                context = memory.read(
                    query,
                    history,
                    kinds=RUN_CONTEXT_MEMORY_KINDS,
                )
                t_read = (time.perf_counter() - t0) * 1000
                print(f"[memory.read] {len(context)} hits ({t_read:.0f}ms)")

                if block is None:
                    t0 = time.perf_counter()
                    block = perception.plan(query, context)
                    print(f"[plan]        done in {(time.perf_counter()-t0)*1000:.0f}ms")
                    blocks_so_far.append(block)
                    _log_block(block)

                t0 = time.perf_counter()
                round_results = await decision.run_block(
                    block=block,
                    context=context,
                    tools=tools_for_decision,
                    session=session,
                    prior_results=results_so_far,
                    recent_tool_calls=recent_tool_calls,
                )
                t_exec = (time.perf_counter() - t0) * 1000
                results_so_far.extend(round_results)
                for result in round_results:
                    _log_result(result)

                ok_goal_ids = {r.goal_id for r in round_results if r.status == "ok"}
                for goal in block.goals:
                    if goal.id in ok_goal_ids:
                        goal.done = True

                t0 = time.perf_counter()
                write_count = 0
                for result in round_results:
                    if result.kind != "tool" or result.tool_call is None:
                        continue
                    memory.record_outcome(
                        tool_call=result.tool_call,
                        result_text=result.output_descriptor,
                        artifact_id=result.artifact_id,
                        run_id=run_id,
                        goal_id=result.goal_id,
                    )
                    write_count += 1
                t_write = (time.perf_counter() - t0) * 1000
                print(f"[memory.write] {write_count} tool outcomes ({t_write:.0f}ms)")

                t0 = time.perf_counter()
                review = perception.review(query, blocks_so_far, results_so_far, context=context)
                t_review = (time.perf_counter() - t0) * 1000
                _log_review(review)

                t_round = (time.perf_counter() - round_start) * 1000
                print(f"[timing] round {round_i}: read={t_read:.0f} exec={t_exec:.0f} write={t_write:.0f} review={t_review:.0f} total={t_round:.0f}ms")

                if review.finished:
                    final_answer = compose_answer(results_so_far, blocks_so_far)
                    print(f"\n[done] review finished after round {round_i} total={(time.perf_counter()-run_start)*1000:.0f}ms")
                    break

                if review.next_block is None:
                    final_answer = compose_answer(results_so_far, blocks_so_far)
                    print("[warn] review was not finished but returned no next block")
                    break

                block = review.next_block
                blocks_so_far.append(block)

    run_total_ms = (time.perf_counter() - run_start) * 1000
    if not final_answer:
        final_answer = compose_answer(results_so_far, blocks_so_far)
    if not final_answer:
        print(f"[warn] hit MAX_ROUNDS={MAX_ROUNDS} without a final answer")
        final_answer = (
            "I was unable to produce an answer within the allowed reasoning rounds. "
            "Please try rephrasing your question or breaking it into smaller parts."
        )

    print(f"\n{'=' * 78}")
    print(f"FINAL ({run_total_ms:.0f}ms total): {final_answer}")
    print(f"{'=' * 78}\n")
    return final_answer


def main() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s %(message)s")
    query = " ".join(sys.argv[1:]) or "What is the current time in Asia/Tokyo and Asia/Kolkata? Tell me the difference in hours."
    asyncio.run(run(query))


if __name__ == "__main__":
    main()

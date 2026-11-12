"""Decision: ground and run a whole block.

Decision owns execution authority in the block loop. For each goal it grounds
intent into either a real MCP tool call or a direct synthesis answer, dispatches
tools through Action, and returns one GoalResult per goal.
"""

from __future__ import annotations

import json
import time

from mcp import ClientSession

from agent.cognition import action
from agent.gateway import LLM, ensure_gateway
from agent.schemas import Block, Goal, GoalResult, MemoryItem, ToolCall
from agent.services import artifacts

SYSTEM = (
    "You are the Decision layer of an agent.\n"
    "Inputs you receive: ONE current goal, the relevant memory snippets,\n"
    "prior results, and optionally raw bytes of attached artifacts.\n\n"
    "Choose EXACTLY ONE response:\n"
    "  (a) Reply with the answer/result for this goal as plain text. If the\n"
    "      goal asks you to summarise, extract, compare, or transform attached\n"
    "      content, do that work inside your reply.\n"
    "  (b) Call exactly ONE tool from the available MCP tools when you need\n"
    "      external work (fetching, file ops, time, currency, web search).\n\n"
    "Rules:\n"
    "- Never narrate. Answer or call a tool, never both.\n"
    "- Never invent a tool that is not in the tool list.\n"
    "- If no available tool can satisfy the goal and the answer is not present\n"
    "  in memory/results/attached artifacts, answer with a short capability-gap\n"
    "  explanation starting with CAPABILITY_GAP:.\n"
    "- If the goal is already satisfied by the memory hits + prior results,\n"
    "  answer directly without calling a tool.\n"
    "- Artifact handles (strings starting with `art:`) are NOT file paths,\n"
    "  URLs, or tool arguments. NEVER pass an `art:...` value to read_file,\n"
    "  list_dir, fetch_url, or ANY other tool. If a goal needs artifact bytes,\n"
    "  those bytes will appear in ATTACHED ARTIFACTS; answer from that text.\n"
    "- read_file and list_dir operate on the local sandbox/ directory, not\n"
    "  artifacts. Only call them when the user has asked you to read/list a\n"
    "  real sandbox file by name.\n"
    "- Answer using whatever is in front of you: memory hits, prior results,\n"
    "  and any attached artifact bytes. Be substantive for extract/list/select/\n"
    "  compare goals.\n"
    "- For 'remember X', 'save X', 'set a reminder', 'note X' style goals,\n"
    "  call create_file (or update_file when re-saving) under the sandbox with\n"
    "  a filename describing the topic.\n"
    "- When the goal asks to make a file's or fetched content SEARCHABLE for\n"
    "  later turns or runs, call `index_document`.\n"
    "- When the goal asks to ANSWER a question and MEMORY HITS already contain\n"
    "  fact items whose descriptors begin with `[sandbox:` or `[art:`, call\n"
    "  `search_knowledge` against the question rather than re-fetching or\n"
    "  re-reading the source. If the relevant chunks are already shown inline,\n"
    "  synthesise directly from those previews.\n"
    "- For web_search, choose max_results based on query complexity.\n"
)

ATTACH_HEAD = 20_000
ATTACH_TAIL = 10_000
REPEATED_TOOL_CALL_LIMIT = 3  # rail R4 — docs/LOOP_RESTRUCTURE_PLAN.md §6


def _format_hits(hits: list[MemoryItem]) -> str:
    if not hits:
        return "  (none)"
    out = []
    for h in hits[:10]:
        line = f"  - [{h.kind}] {h.descriptor}"
        val = h.value or {}
        if val:
            raw = val.get("raw") or val.get("result_preview")
            chunk = val.get("chunk")
            if isinstance(raw, str) and raw.strip():
                raw_more = "..." if len(raw) > 2000 else ""
                line += f"\n      raw: {raw[:2000]}{raw_more}"
            elif isinstance(chunk, str) and chunk.strip():
                src = val.get("source") or ""
                preview = chunk[:2000].replace("\n", " ")
                more = "..." if len(chunk) > 2000 else ""
                line += f"\n      chunk ({src}): {preview}{more}"
            else:
                compact = {
                    k: v for k, v in val.items()
                    if k != "chunk" and not (isinstance(v, str) and len(v) > 200)
                }
                if compact:
                    line += f"\n      value: {json.dumps(compact)[:240]}"
        out.append(line)
    return "\n".join(out)


def _format_results(results: list[GoalResult]) -> str:
    if not results:
        return "  (empty)"
    lines = []
    for r in results[-12:]:
        tool = f" tool={r.tool_call.name}" if r.tool_call else ""
        art = f" artifact={r.artifact_id}" if r.artifact_id else ""
        msg = f" message={r.message[:180]}" if r.message else ""
        desc = r.output_descriptor[:500].replace("\n", " ")
        lines.append(f"  - {r.goal_id}: {r.kind}/{r.status}{tool}{art}{msg} -> {desc}")
    return "\n".join(lines)


def _format_attached(attached: list[tuple[str, bytes]]) -> str:
    if not attached:
        return ""
    parts = ["\n\nATTACHED ARTIFACTS:"]
    for art_id, data in attached:
        text = data.decode("utf-8", errors="replace")
        if len(text) > ATTACH_HEAD + ATTACH_TAIL + 50:
            text = (
                text[:ATTACH_HEAD]
                + f"\n\n...[truncated; full size {len(data)} bytes]...\n\n"
                + text[-ATTACH_TAIL:]
            )
        parts.append(f"--- {art_id} ---\n{text}")
    return "\n".join(parts)


def _resolve_attached(goal: Goal) -> list[tuple[str, bytes]]:
    attached: list[tuple[str, bytes]] = []
    for art_id in goal.needs_artifact_ids:
        if artifacts.exists(art_id):
            blob = artifacts.get_bytes(art_id)
            attached.append((art_id, blob))
            print(f"[attach]        {goal.id} {art_id} ({len(blob)} bytes)")
        else:
            print(f"[attach]        {goal.id} missing artifact {art_id}")
    return attached


def _tool_call_key(tool_call: ToolCall) -> str:
    return f"{tool_call.name}({json.dumps(tool_call.arguments, sort_keys=True)[:160]})"


def _synthesis_result(goal: Goal, text: str) -> GoalResult:
    stripped = text.strip()
    if stripped.upper().startswith("CAPABILITY_GAP:"):
        msg = stripped.split(":", 1)[1].strip() or "Decision reported a missing capability."
        return GoalResult(
            goal_id=goal.id,
            kind="capability_gap",
            output_descriptor=msg,
            status="capability_gap",
            message=msg,
        )
    if not stripped:
        return GoalResult(
            goal_id=goal.id,
            kind="synthesis",
            output_descriptor="",
            status="error",
            message="Decision returned an empty synthesis result.",
        )
    return GoalResult(
        goal_id=goal.id,
        kind="synthesis",
        output_descriptor=stripped,
        status="ok",
    )


async def _run_goal(
    goal: Goal,
    context: list[MemoryItem],
    prior_results: list[GoalResult],
    tools: list[dict],
    session: ClientSession,
    recent_tool_calls: list[str],
) -> GoalResult:
    ensure_gateway()
    attached = _resolve_attached(goal)
    prompt = (
        f"GOAL:\n  {goal.text}\n\n"
        f"MEMORY HITS:\n{_format_hits(context)}\n\n"
        f"PRIOR RESULTS:\n{_format_results(prior_results)}"
        f"{_format_attached(attached)}"
    )

    t0 = time.perf_counter()
    try:
        reply = LLM().chat(
            prompt=prompt,
            system=SYSTEM,
            cache_system=True,
            tools=tools,
            tool_choice="auto",
            temperature=0,
            max_tokens=2048,
        )
    except Exception as e:
        msg = f"Decision LLM call failed: {e}"
        print(f"[decision] LLM call FAILED after {(time.perf_counter()-t0)*1000:.0f}ms: {e}")
        return GoalResult(
            goal_id=goal.id,
            kind="synthesis",
            output_descriptor=msg,
            status="error",
            message=msg,
        )
    print(f"[decision] LLM call done in {(time.perf_counter()-t0)*1000:.0f}ms")

    tcs = reply.get("tool_calls") or []
    if not tcs:
        result = _synthesis_result(goal, reply.get("text") or "")
        print(f"[decision]      SYNTHESIS {goal.id} {result.status}: {result.output_descriptor[:200]}")
        return result

    tc = ToolCall(name=tcs[0]["name"], arguments=tcs[0].get("arguments") or {})
    tool_names = {t.get("name") for t in tools}
    if tc.name not in tool_names:
        msg = f"Decision requested unavailable tool {tc.name!r} for goal: {goal.text}"
        print(f"[decision]      CAPABILITY_GAP {goal.id}: {msg}")
        return GoalResult(
            goal_id=goal.id,
            kind="capability_gap",
            tool_call=tc,
            output_descriptor=msg,
            status="capability_gap",
            message=msg,
        )

    call_key = _tool_call_key(tc)
    dup_count = recent_tool_calls.count(call_key)
    if dup_count > 0:
        print(f"[warn]  REPEATED TOOL CALL #{dup_count + 1}: {call_key}")
    if dup_count + 1 >= REPEATED_TOOL_CALL_LIMIT:
        msg = f"Repeated identical tool call limit reached: {call_key}"
        print(f"[decision]      CAPABILITY_GAP {goal.id}: {msg}")
        return GoalResult(
            goal_id=goal.id,
            kind="capability_gap",
            tool_call=tc,
            output_descriptor=msg,
            status="capability_gap",
            message=msg,
        )
    recent_tool_calls.append(call_key)
    if len(recent_tool_calls) > 12:
        recent_tool_calls.pop(0)

    print(f"[decision]      TOOL_CALL {goal.id}: {tc.name}({json.dumps(tc.arguments)[:120]})")
    t0 = time.perf_counter()
    try:
        result_text, art_id = await action.execute(session, tc)
    except Exception as e:
        msg = f"Action failed while running {tc.name}: {e}"
        print(f"[action]        ERROR ({(time.perf_counter()-t0)*1000:.0f}ms) -> {msg}")
        return GoalResult(
            goal_id=goal.id,
            kind="tool",
            tool_call=tc,
            output_descriptor=msg,
            artifact_id=None,
            status="error",
            message=msg,
        )

    t_act = (time.perf_counter() - t0) * 1000
    preview = result_text[:220].replace("\n", " ")
    print(f"[action]        ({t_act:.0f}ms) -> {preview}{'...' if len(result_text) > 220 else ''}"
          + (f"   +{art_id}" if art_id else ""))

    status = "ok"
    message = ""
    if not result_text.strip():
        status = "error"
        message = "Tool returned an empty result."
    elif result_text.startswith("ERROR:"):
        status = "error"
        message = result_text

    return GoalResult(
        goal_id=goal.id,
        kind="tool",
        tool_call=tc,
        output_descriptor=result_text,
        artifact_id=art_id,
        status=status,  # type: ignore[arg-type]
        message=message,
    )


async def run_block(
    block: Block,
    context: list[MemoryItem],
    tools: list[dict],
    session: ClientSession,
    prior_results: list[GoalResult] | None = None,
    recent_tool_calls: list[str] | None = None,
) -> list[GoalResult]:
    prior_results = prior_results or []
    recent_tool_calls = recent_tool_calls if recent_tool_calls is not None else []
    results: list[GoalResult] = []
    for goal in block.goals:
        result = await _run_goal(
            goal=goal,
            context=context,
            prior_results=[*prior_results, *results],
            tools=tools,
            session=session,
            recent_tool_calls=recent_tool_calls,
        )
        results.append(result)
    return results

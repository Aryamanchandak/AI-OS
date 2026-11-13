"""Perception: PLAN and REVIEW.

Perception has no hands in the block loop. It never runs tools and never
authors the final answer. It plans a block of goals, then later reviews goals
against their results and either stops the run or emits the next block.
"""

from __future__ import annotations

import json
import time

from pydantic import BaseModel, Field

from gateway import LLM
from schemas import (
    Block,
    Goal,
    GoalResult,
    MemoryItem,
    Review,
    ReviewFinding,
    new_id,
)


SYNTHESIS_KW = (
    "evaluate", "select", "synthes", "compare", "decide", "recommend",
    "tell me which", "most appropriate", "analy", "pick", "choose",
    "summarise", "summarize", "answer", "identify", "find", "determine",
    "extract", "list", "report", "tell", "explain", "describe", "name",
)


class _PlanGoal(BaseModel):
    text: str = Field(max_length=240)
    artifact_indices: list[int] = Field(default_factory=list, max_length=5)


class _PlanOutput(BaseModel):
    rationale: str = Field(max_length=1000)
    goals: list[_PlanGoal] = Field(default_factory=list, max_length=10)


class _ReviewLLMFinding(BaseModel):
    check: str
    detail: str
    proposed_goal_text: str | None = None
    artifact_indices: list[int] = Field(default_factory=list, max_length=5)


class _ReviewLLMOutput(BaseModel):
    findings: list[_ReviewLLMFinding] = Field(default_factory=list, max_length=12)


PLAN_SYSTEM = (
    "You are the PLAN side of the Perception layer of an agent.\n"
    "You see the user's query and memory hits. Return ONE block of concrete\n"
    "goals that can be specified right now.\n\n"
    "You speak at the level of intent, not tool selection. Write each goal as\n"
    "a short imperative describing WHAT must happen, not WHICH tool will do it.\n"
    "Decision is the layer that maps intent to a tool.\n\n"
    "Decomposition rules:\n"
    "- If the query asks to read/fetch/process N concrete items, emit one goal\n"
    "  per item plus a final synthesis/answer goal.\n"
    "- If the query asks to ingest N concrete files so they can be searched\n"
    "  later, emit one goal per file expressing that its content should be made\n"
    "  searchable, plus a final report goal.\n"
    "- Do not plan work you cannot yet name. If concrete items are unknown until\n"
    "  a discovery action runs, emit the discovery goal and stop. REVIEW will\n"
    "  plan the concrete follow-up goals after the discovery result exists.\n"
    "- If MEMORY HITS already contain fact items whose descriptors start with\n"
    "  [sandbox: or [art:, the goal for questions about that material is to\n"
    "  query the existing knowledge base, paired with a final answer goal.\n"
    "- Whenever the user's query is a question rather than a pure action, the\n"
    "  last goal must be a synthesis/answer goal.\n\n"
    "Artifact routing:\n"
    "- You see memory hits as descriptors only. Entries with a numeric i have\n"
    "  artifact bytes available to Decision.\n"
    "- For a goal that must extract, summarise, analyse, compare, select, or\n"
    "  otherwise read stored content, include the relevant artifact index or\n"
    "  indices in artifact_indices.\n"
    "- For pure fetch/search/compute/open/time goals, leave artifact_indices\n"
    "  empty.\n"
)


REVIEW_SYSTEM = (
    "You are the REVIEW side of the Perception layer of an agent.\n"
    "You are a bounded gap detector, not an open-ended improver. You never\n"
    "write the final answer and never run tools.\n\n"
    "Mechanical checks for unaddressed goals, errors, and capability gaps have\n"
    "already been computed. Do not redo them. Only evaluate these three checks:\n"
    "discovery, insufficient, uncovered.\n\n"
    "For each check, return a finding. If the check passes, proposed_goal_text\n"
    "must be null and detail should briefly say it passed. If the check finds a\n"
    "real gap, propose exactly one concrete follow-up goal. Do not propose vague\n"
    "polish goals.\n\n"
    "Artifact routing follows the same rule as PLAN: use artifact_indices only\n"
    "when the follow-up goal needs stored artifact bytes shown in memory hits.\n"
)


def _snapshot_hits(hits: list[MemoryItem]) -> list[dict]:
    art_pos = 0
    out = []
    for h in hits[:12]:
        i = None
        if h.artifact_id:
            i = art_pos
            art_pos += 1
        item = {
            "i": i,
            "kind": h.kind,
            "descriptor": h.descriptor,
            "keywords": h.keywords,
            "artifact_id": h.artifact_id,
        }
        val = h.value or {}
        raw = val.get("raw")
        chunk = val.get("chunk")
        if isinstance(raw, str) and raw.strip():
            item["raw_preview"] = raw[:600]
        elif isinstance(chunk, str) and chunk.strip():
            item["chunk_preview"] = chunk[:600].replace("\n", " ")
        out.append(item)
    return out


def _artifact_ids_for_indices(hits: list[MemoryItem], indices: list[int]) -> list[str]:
    art_ids = [h.artifact_id for h in hits[:12] if h.artifact_id]
    out = []
    for i in indices:
        if 0 <= i < len(art_ids):
            art_id = art_ids[i]
            if art_id and art_id not in out:
                out.append(art_id)
    return out


def _artifact_ids_for_text(text: str, hits: list[MemoryItem]) -> list[str]:
    if not hits:
        return []
    text_lc = text.lower()
    matches = []
    for h in hits[:12]:
        if not h.artifact_id:
            continue
        haystack = " ".join([h.descriptor, *h.keywords]).lower()
        if any(tok for tok in text_lc.split() if len(tok) > 3 and tok in haystack):
            matches.append(h.artifact_id)
    if matches:
        return list(dict.fromkeys(matches))
    if any(kw in text_lc for kw in SYNTHESIS_KW):
        recent = next((h.artifact_id for h in reversed(hits[:12]) if h.artifact_id), None)
        return [recent] if recent else []
    return []


def _goals_from_plan(raw_goals: list[_PlanGoal], hits: list[MemoryItem]) -> list[Goal]:
    goals = []
    for raw in raw_goals:
        artifact_ids = _artifact_ids_for_indices(hits, raw.artifact_indices)
        if not artifact_ids:
            artifact_ids = _artifact_ids_for_text(raw.text, hits)
        goals.append(Goal(id=new_id("g"), text=raw.text, needs_artifact_ids=artifact_ids))
    return goals


def plan(query: str, context: list[MemoryItem]) -> Block:

    prompt = (
        f"USER QUERY:\n  {query}\n\n"
        "MEMORY HITS (handles + descriptors only, no raw bytes; `i` is the\n"
        "artifact index to include in artifact_indices when a goal needs it):\n"
        f"{json.dumps(_snapshot_hits(context), indent=2)}\n\n"
        "Return the initial block as JSON matching the schema."
    )

    t0 = time.perf_counter()
    try:
        reply = LLM().chat(
            prompt=prompt,
            system=PLAN_SYSTEM,
            response_format={
                "type": "json_schema",
                "schema": _PlanOutput.model_json_schema(),
                "name": "PlanOutput",
                "strict": True,
            },
            temperature=1.0,
        )
    except Exception as e:
        print(f"[perception.plan] LLM call FAILED after {(time.perf_counter()-t0)*1000:.0f}ms: {e} - falling back to single-goal")
        return Block(round=0, goals=[Goal(id=new_id("g"), text=query)], rationale="fallback: plan LLM failed")
    print(f"[perception.plan] LLM call done in {(time.perf_counter()-t0)*1000:.0f}ms")

    parsed = reply.get("parsed")
    if not parsed or not parsed.get("goals"):
        print(f"[perception.plan] WARNING: no goals returned (parsed={parsed!r}) - falling back to single-goal")
        return Block(round=0, goals=[Goal(id=new_id("g"), text=query)], rationale="fallback: no goals returned")

    out = _PlanOutput.model_validate(parsed)
    return Block(round=0, goals=_goals_from_plan(out.goals, context), rationale=out.rationale)


def _mechanical_findings(
    blocks_so_far: list[Block],
    results_so_far: list[GoalResult],
) -> list[ReviewFinding]:
    findings: list[ReviewFinding] = []
    all_goals = [goal for block in blocks_so_far for goal in block.goals]
    results_by_goal: dict[str, list[GoalResult]] = {}
    for result in results_so_far:
        results_by_goal.setdefault(result.goal_id, []).append(result)

    missing = [g for g in all_goals if not results_by_goal.get(g.id)]
    if missing:
        for goal in missing:
            findings.append(ReviewFinding(
                check="unaddressed",
                goal_id=goal.id,
                detail=f"No result was produced for goal: {goal.text}",
                proposed_goal_text=goal.text,
            ))
    else:
        findings.append(ReviewFinding(check="unaddressed", detail="pass: every goal has at least one result"))

    error_results = [
        r for r in results_so_far
        if r.status == "error" or (r.status == "ok" and not r.output_descriptor.strip())
    ]
    if error_results:
        goal_by_id = {g.id: g for g in all_goals}
        for result in error_results:
            goal = goal_by_id.get(result.goal_id)
            proposed = f"Retry: {goal.text}" if goal else None
            findings.append(ReviewFinding(
                check="error",
                goal_id=result.goal_id,
                detail=result.message or result.output_descriptor or "Result was empty or errored",
                proposed_goal_text=proposed,
            ))
    else:
        findings.append(ReviewFinding(check="error", detail="pass: no error or empty results"))

    gaps = [r for r in results_so_far if r.status == "capability_gap"]
    if gaps:
        for result in gaps:
            findings.append(ReviewFinding(
                check="capability_gap",
                goal_id=result.goal_id,
                detail=result.message or result.output_descriptor,
                proposed_goal_text=None,
            ))
    else:
        findings.append(ReviewFinding(check="capability_gap", detail="pass: no capability gaps"))

    return findings


def _review_prompt(
    query: str,
    context: list[MemoryItem],
    blocks_so_far: list[Block],
    results_so_far: list[GoalResult],
    mechanical: list[ReviewFinding],
) -> str:
    blocks = [b.model_dump() for b in blocks_so_far]
    results = [r.model_dump() for r in results_so_far]
    findings = [f.model_dump() for f in mechanical]
    return (
        f"USER QUERY:\n  {query}\n\n"
        f"BLOCKS SO FAR:\n{json.dumps(blocks, indent=2, default=str)}\n\n"
        f"RESULTS SO FAR:\n{json.dumps(results, indent=2, default=str)}\n\n"
        f"MECHANICAL FINDINGS ALREADY COMPUTED:\n{json.dumps(findings, indent=2)}\n\n"
        "MEMORY HITS (for artifact routing only; `i` is artifact index):\n"
        f"{json.dumps(_snapshot_hits(context), indent=2)}\n\n"
        "Return findings for discovery, insufficient, and uncovered only."
    )


def review(
    query: str,
    blocks_so_far: list[Block],
    results_so_far: list[GoalResult],
    context: list[MemoryItem] | None = None,
) -> Review:
    context = context or []
    mechanical = _mechanical_findings(blocks_so_far, results_so_far)

    t0 = time.perf_counter()
    llm_artifact_indices: dict[int, list[int]] = {}  # id(ReviewFinding) -> its artifact_indices
    try:
        reply = LLM().chat(
            prompt=_review_prompt(query, context, blocks_so_far, results_so_far, mechanical),
            system=REVIEW_SYSTEM,
            response_format={
                "type": "json_schema",
                "schema": _ReviewLLMOutput.model_json_schema(),
                "name": "ReviewLLMOutput",
                "strict": True,
            },
            temperature=1.0,
        )
    except Exception as e:
        print(f"[perception.review] LLM call FAILED after {(time.perf_counter()-t0)*1000:.0f}ms: {e} - using mechanical review only")
        llm_findings: list[ReviewFinding] = [
            ReviewFinding(check="discovery", detail="skipped: review LLM failed"),
            ReviewFinding(check="insufficient", detail="skipped: review LLM failed"),
            ReviewFinding(check="uncovered", detail="skipped: review LLM failed"),
        ]
    else:
        print(f"[perception.review] LLM call done in {(time.perf_counter()-t0)*1000:.0f}ms")
        parsed = _ReviewLLMOutput.model_validate(reply.get("parsed") or {})
        llm_findings = []
        seen = set()
        for raw in parsed.findings:
            if raw.check not in {"discovery", "insufficient", "uncovered"}:
                continue
            seen.add(raw.check)
            finding = ReviewFinding(
                check=raw.check,  # type: ignore[arg-type]
                detail=raw.detail,
                proposed_goal_text=raw.proposed_goal_text,
            )
            if raw.artifact_indices:
                llm_artifact_indices[id(finding)] = raw.artifact_indices
            llm_findings.append(finding)
        for check in ("discovery", "insufficient", "uncovered"):
            if check not in seen:
                llm_findings.append(ReviewFinding(
                    check=check,  # type: ignore[arg-type]
                    detail="pass: no finding returned",
                ))

    findings = mechanical + llm_findings
    proposed = [f for f in findings if f.proposed_goal_text and f.check != "capability_gap"]
    if not proposed:
        return Review(finished=True, findings=findings, next_block=None)

    goal_by_id = {g.id: g for block in blocks_so_far for g in block.goals}

    def _resolve_ids(f: ReviewFinding) -> list[str]:
        # A retry of an existing goal (unaddressed/error) carries forward that
        # goal's own routing instead of re-guessing it from proposed_goal_text.
        if f.goal_id:
            original = goal_by_id.get(f.goal_id)
            if original and original.needs_artifact_ids:
                return original.needs_artifact_ids
        # A genuinely new goal (discovery/insufficient/uncovered) uses the
        # indices the reviewer LLM was explicitly asked for, same as PLAN.
        indices = llm_artifact_indices.get(id(f))
        if indices:
            resolved = _artifact_ids_for_indices(context, indices)
            if resolved:
                return resolved
        # Fallback: keyword-overlap heuristic.
        return _artifact_ids_for_text(f.proposed_goal_text or "", context)

    next_round = (max((b.round for b in blocks_so_far), default=-1) + 1)
    goals = [
        Goal(
            id=new_id("g"),
            text=f.proposed_goal_text or "",
            needs_artifact_ids=_resolve_ids(f),
        )
        for f in proposed
    ]
    rationale = "; ".join(f"{f.check}: {f.detail}" for f in proposed)[:1000]
    return Review(
        finished=False,
        findings=findings,
        next_block=Block(round=next_round, goals=goals, rationale=rationale),
    )

"""Veritas pipeline orchestrator.

Claim pipeline:
  decompose -> search -> fetch -> extract (fan-out) -> grade -> synthesize -> verify -> compose
                  ^                                                              |
                  +---------------- needs_more_evidence --------------------------+

Topic pipeline (TopicExplorer, below):
  scope -> search -> fetch -> extract (fan-out) -> grade -> compose_topic
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import yaml

from citations import citation_violations, integrity_check
from llm import LLM, LLMError
from sources import Source, fetch_all

ROOT = Path(__file__).parent


class Trace:
    """Append-only run log. Written to disk so the README can cite real runs."""

    def __init__(self, claim: str, verbose: bool = True, mode: str = "claim",
                 on_log: Callable[[str], None] | None = None) -> None:
        self.claim = claim
        self.verbose = verbose
        self.mode = mode
        self.on_log = on_log
        self.started = time.time()
        self.steps: list[dict[str, Any]] = []

    def log(self, msg: str = "") -> None:
        if self.verbose:
            print(msg, flush=True)
        if self.on_log:
            self.on_log(msg)

    def record(self, skill: str, round_no: int, output: Any, seconds: float,
               reasoning: str = "") -> None:
        self.steps.append({
            "skill": skill,
            "round": round_no,
            "seconds": round(seconds, 2),
            "reasoning": reasoning,
            "output": output,
        })

    def save(self, result: dict[str, Any], usage: Any) -> Path:
        slug = re.sub(r"[^a-z0-9]+", "-", self.claim.lower())[:48].strip("-")
        path = ROOT / "runs" / f"{int(self.started)}-{self.mode}-{slug}.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({
            "mode": self.mode,
            "claim": self.claim,
            "wall_clock_seconds": round(time.time() - self.started, 1),
            "tokens": {
                "input": usage.input_tokens,
                "output": usage.output_tokens,
                "cache_read": usage.cache_read,
                "cache_write": usage.cache_write,
            },
            "steps": self.steps,
            "result": result,
        }, indent=2))
        return path


class Veritas:
    def __init__(self, verbose: bool = True,
                 on_log: Callable[[str], None] | None = None) -> None:
        self.cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
        self.llm = LLM(self.cfg["model"])
        self.verbose = verbose
        self.on_log = on_log
        self.master = _extract_master_prompt(ROOT.parent / "PROMPT.md")

    # ---------------------------------------------------------------- skills

    def _invoke(self, skill: str, payload: dict[str, Any], trace: Trace,
                round_no: int) -> dict[str, Any]:
        """One LLM skill call: master prompt + skill contract + typed payload."""
        spec = self.cfg["skills"][skill]
        contract = (ROOT / spec["prompt"]).read_text()
        # Two blocks, not one string: the master prompt is byte-identical across
        # every skill, so caching it separately means the prefix is a cache read
        # on every call after the first rather than only on repeats of the same
        # skill. See llm.complete().
        system = [self.master, contract]
        user = json.dumps({"ACTIVE_SKILL": skill, **payload}, indent=2, default=str)

        t0 = time.time()
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                parsed, _ = self.llm.complete(system, user)
                break
            except (LLMError, json.JSONDecodeError) as exc:
                last_error = exc
                user += (
                    f"\n\nYour previous response could not be parsed as JSON "
                    f"({exc}). Return the raw JSON object only."
                )
        else:
            raise LLMError(f"{skill} failed after retries: {last_error}")

        out = parsed.get("output", parsed)
        trace.record(skill, round_no, out, time.time() - t0,
                     parsed.get("reasoning", ""))
        return out

    # -------------------------------------------------------------- pipeline

    def run(self, claim: str) -> dict[str, Any]:
        trace = Trace(claim, self.verbose, mode="claim", on_log=self.on_log)
        max_rounds = self.cfg["pipeline"]["max_rounds"]
        log = trace.log

        log(f"\n  CLAIM  {claim}\n" + "  " + "-" * 68)

        # --- 1. decompose ----------------------------------------------------
        log("\n  [1/8] decompose")
        decomp = self._invoke("decompose", {"claim": claim}, trace, 1)
        if decomp.get("status") == "out_of_scope":
            log("        -> out of scope; halting")
            return self._finish(trace, {
                "verdict": "out_of_scope",
                "one_line_answer": decomp.get("notes", "Claim is not empirically checkable."),
            })

        sub_claims = decomp.get("sub_claims", [])
        log(f"        {len(sub_claims)} sub-claims | falsifier: "
            f"{decomp.get('falsifier','—')[:60]}")
        if decomp.get("status") == "ambiguous_claim":
            log(f"        ambiguous: {len(decomp.get('interpretations', []))} readings")

        seen_ids: set[str] = set()
        all_sources: list[Source] = []
        gaps: list[str] = []
        feedback = ""
        synthesis: dict[str, Any] = {}
        audit: dict[str, Any] = {}

        for round_no in range(1, max_rounds + 1):
            log(f"\n  ── round {round_no}/{max_rounds} ──")

            # --- 2. search ---------------------------------------------------
            log("\n  [2/8] search")
            search_out = self._invoke("search", {
                "claim": claim, "decomposition": decomp,
                "ROUND": round_no, "MAX_ROUNDS": max_rounds,
                "VERIFIER_FEEDBACK": feedback, "gaps_to_search": gaps,
            }, trace, round_no)
            queries = search_out.get("queries", [])
            stances = {q.get("stance") for q in queries}
            log(f"        {len(queries)} queries | stances: {', '.join(sorted(s for s in stances if s))}")

            # --- 3. fetch (deterministic) ------------------------------------
            log("\n  [3/8] fetch")
            new_sources, seen_ids = fetch_all(queries, self.cfg, seen_ids, log)
            all_sources += new_sources
            log(f"        +{len(new_sources)} sources ({len(all_sources)} total)")

            if not all_sources:
                log("        -> no sources retrieved")
                if round_no < max_rounds:
                    feedback = "No sources retrieved. Broaden the queries substantially."
                    continue
                return self._finish(trace, {
                    "verdict": "insufficient_evidence",
                    "confidence": "low",
                    "one_line_answer": "No published sources could be retrieved for this claim.",
                })

            # --- 4. extract (parallel fan-out over sub-claims) ---------------
            log("\n  [4/8] extract  (parallel fan-out)")
            findings, unusable = self._extract_parallel(
                claim, sub_claims, all_sources, trace, round_no, log
            )
            log(f"        {len(findings)} findings | {len(unusable)} unusable")
            dirs: dict[str, int] = {}
            for f in findings:
                dirs[f.get("direction", "?")] = dirs.get(f.get("direction", "?"), 0) + 1
            log(f"        directions: {dirs}")

            usable = [f for f in findings if f.get("direction") != "irrelevant"]
            if not usable:
                log("        -> every finding irrelevant")
                if round_no < max_rounds:
                    feedback = "All retrieved sources were irrelevant. Rewrite the queries."
                    continue
                return self._finish(trace, {
                    "verdict": "insufficient_evidence",
                    "confidence": "low",
                    "one_line_answer": "No relevant evidence could be extracted from the retrieved sources.",
                })

            # --- 5. grade ----------------------------------------------------
            log("\n  [5/8] grade")
            grade_out = self._invoke("grade", {
                "claim": claim, "findings": usable,
                "sources": [_slim(s) for s in all_sources],
            }, trace, round_no)
            grades = grade_out.get("grades", [])
            weights = [g.get("weight", 0) for g in grades] or [0]
            log(f"        {len(grades)} graded | weight max {max(weights)} "
                f"mean {round(sum(weights)/len(weights), 2)}")

            # --- 6. synthesize ----------------------------------------------
            log("\n  [6/8] synthesize")
            synthesis = self._invoke("synthesize", {
                "claim": claim, "decomposition": decomp,
                "findings": usable, "grades": grades,
                "ROUND": round_no, "MAX_ROUNDS": max_rounds,
            }, trace, round_no)
            log(f"        verdict: {synthesis.get('verdict')} "
                f"({synthesis.get('confidence')})")

            # --- 7. verify ---------------------------------------------------
            log("\n  [7/8] verify  (adversarial audit)")
            audit = self._invoke("verify", {
                "claim": claim, "decomposition": decomp,
                "synthesis": synthesis, "findings": usable, "grades": grades,
                "ROUND": round_no, "MAX_ROUNDS": max_rounds,
            }, trace, round_no)

            # Deterministic citation integrity — asserted in code, not judged by
            # a model. Prepended so it reads before the LLM's own checks, and it
            # overrides an `approved` verdict: a synthesis citing a source that
            # was never retrieved is not approvable whatever C1 concluded.
            fetched = {s.id for s in all_sources}
            bad = citation_violations(synthesis, fetched)
            audit["checks"] = [
                integrity_check("C0", "citation_integrity_deterministic", bad)
            ] + list(audit.get("checks", []))
            if bad:
                audit["verdict"] = "needs_more_evidence"
                audit["required_changes"] = list(audit.get("required_changes", [])) + [
                    f"Synthesis cites sources that were never retrieved: {', '.join(bad)}. "
                    "Cite only ids present in the evidence supplied to you."
                ]

            for chk in audit.get("checks", []):
                mark = "PASS" if chk.get("result") == "pass" else "FAIL"
                log(f"        [{mark}] {chk.get('id')} {chk.get('name')}"
                    f"{'' if mark == 'PASS' else ' — ' + str(chk.get('reason'))}")
            log(f"        -> {audit.get('verdict')}")
            log(f"        weakest link: {audit.get('weakest_link','—')}")

            if audit.get("verdict") == "approved" or round_no == max_rounds:
                break

            gaps = audit.get("gaps_to_search", [])
            feedback = "; ".join(audit.get("required_changes", []) + gaps) or "Insufficient evidence."
            log(f"\n        SPLICE: re-entering search with {len(gaps)} gaps")

        # --- 8. compose (essay, verdict folded in) ---------------------------
        log("\n  [8/8] compose")
        composed = self._invoke("compose", {
            "claim": claim, "decomposition": decomp,
            "synthesis": synthesis, "findings": usable, "grades": grades,
            "audit": audit,
        }, trace, round_no)
        log(f"        \"{composed.get('title', '')}\" ({len(str(composed.get('essay', '')).split())} words)")

        # The essay is prose citing ids, so it gets the same set-membership
        # assertion. Too late to re-route here — the loop is done — but the
        # failure ships attached to the output rather than going unnoticed.
        essay_bad = citation_violations(composed, {s.id for s in all_sources})
        audit["checks"] = list(audit.get("checks", [])) + [
            integrity_check("C0b", "citation_integrity_essay", essay_bad)
        ]
        if essay_bad:
            log(f"        ! essay cites unretrieved sources: {', '.join(essay_bad)}")

        result = dict(synthesis)
        result["audit"] = audit
        result["sources_examined"] = len(all_sources)
        result["sources"] = [s.to_dict() for s in all_sources]
        result["rounds"] = round_no
        result["essay"] = composed.get("essay", "")
        result["essay_title"] = composed.get("title", "")
        result["key_takeaway"] = composed.get("key_takeaway", "")
        return self._finish(trace, result)

    # ------------------------------------------------------------- internals

    def _extract_parallel(self, claim, sub_claims, sources, trace, round_no, log):
        """One extract call per sub-claim, concurrently. Failures degrade, not crash."""
        def one(sc):
            relevant = [s for s in sources
                        if not s.sub_claim_id or s.sub_claim_id == sc.get("id")]
            if not relevant:
                relevant = sources
            try:
                return self._invoke("extract", {
                    "claim": claim, "sub_claim": sc,
                    "sources": [_slim(s) for s in relevant],
                }, trace, round_no)
            except Exception as exc:  # one bad sub-claim must not kill the run
                log(f"        ! extract failed for {sc.get('id')}: {exc}")
                return {"findings": [], "unusable_sources": []}

        targets = sub_claims or [{"id": "SC1", "text": claim}]
        with ThreadPoolExecutor(max_workers=min(4, len(targets))) as pool:
            results = list(pool.map(one, targets))

        findings, unusable = [], []
        for r in results:
            findings += r.get("findings", [])
            unusable += r.get("unusable_sources", [])
        return findings, unusable

    def _finish(self, trace: Trace, result: dict[str, Any]) -> dict[str, Any]:
        path = trace.save(result, self.llm.usage)
        result["trace_path"] = str(path)
        result["tokens"] = {
            "input": self.llm.usage.input_tokens,
            "output": self.llm.usage.output_tokens,
            "cache_read": self.llm.usage.cache_read,
            "cache_write": self.llm.usage.cache_write,
        }
        return result


class TopicExplorer:
    """Topic pipeline: scope -> search -> fetch -> extract -> grade -> compose_topic.

    A separate pipeline from `Veritas` (no verdict, no verify/re-search
    loop, single pass) that reuses `Veritas` for the LLM plumbing shared
    with the claim pipeline — `_invoke`, `_extract_parallel`, `_finish` —
    rather than duplicating retry/parsing/trace-saving logic.
    """

    def __init__(self, verbose: bool = True,
                 on_log: Callable[[str], None] | None = None) -> None:
        self._v = Veritas(verbose, on_log)

    def run_topic(self, topic: str) -> dict[str, Any]:
        v = self._v
        trace = Trace(topic, v.verbose, mode="topic", on_log=v.on_log)
        log = trace.log

        log(f"\n  TOPIC  {topic}\n" + "  " + "-" * 68)

        # --- 1. scope ----------------------------------------------------
        log("\n  [1/6] scope")
        scope = v._invoke("scope", {"claim": topic}, trace, 1)
        if scope.get("status") == "out_of_scope":
            log("        -> out of scope; halting")
            return v._finish(trace, {
                "essay": "", "questions": [],
                "one_line_answer": scope.get("notes", "Not an empirical topic."),
            })

        questions = scope.get("questions", [])
        log(f"        {len(questions)} questions | topic: "
            f"{scope.get('normalized_topic', topic)[:60]}")
        if scope.get("status") == "too_broad":
            log(f"        narrowed: {scope.get('notes', '')[:80]}")

        # --- 2. search (reuses the claim-pipeline skill, single round) ---
        log("\n  [2/6] search")
        decomposition_like = {"sub_claims": questions}
        search_out = v._invoke("search", {
            "claim": topic, "decomposition": decomposition_like,
            "ROUND": 1, "MAX_ROUNDS": 1,
            "VERIFIER_FEEDBACK": "", "gaps_to_search": [],
        }, trace, 1)
        queries = search_out.get("queries", [])
        stances = {q.get("stance") for q in queries}
        log(f"        {len(queries)} queries | stances: {', '.join(sorted(s for s in stances if s))}")

        # --- 3. fetch (deterministic) -------------------------------------
        log("\n  [3/6] fetch")
        sources, _seen = fetch_all(queries, v.cfg, set(), log)
        log(f"        {len(sources)} sources")

        if not sources:
            log("        -> no sources retrieved")
            return v._finish(trace, {
                "essay": "", "questions": questions,
                "one_line_answer": "No published sources could be retrieved for this topic.",
            })

        # --- 4. extract (parallel fan-out over questions) -----------------
        log("\n  [4/6] extract  (parallel fan-out)")
        findings, unusable = v._extract_parallel(topic, questions, sources, trace, 1, log)
        usable = [f for f in findings if f.get("direction") != "irrelevant"]
        log(f"        {len(findings)} findings | {len(usable)} usable | {len(unusable)} unusable")

        if not usable:
            log("        -> every finding irrelevant")
            return v._finish(trace, {
                "essay": "", "questions": questions,
                "one_line_answer": "No relevant evidence could be extracted from the retrieved sources.",
            })

        # --- 5. grade -------------------------------------------------------
        log("\n  [5/6] grade")
        grade_out = v._invoke("grade", {
            "claim": topic, "findings": usable,
            "sources": [_slim(s) for s in sources],
        }, trace, 1)
        grades = grade_out.get("grades", [])

        # --- 6. compose_topic -------------------------------------------
        log("\n  [6/6] compose_topic")
        composed = v._invoke("compose_topic", {
            "topic": topic, "scope": scope, "questions": questions,
            "findings": usable, "grades": grades,
        }, trace, 1)
        log(f"        \"{composed.get('title', '')}\" ({len(str(composed.get('essay', '')).split())} words)")

        # Topic mode has no verify step, so this deterministic check is the only
        # thing standing between a hallucinated citation and the reader.
        essay_bad = citation_violations(composed, {s.id for s in sources})
        if essay_bad:
            log(f"        ! essay cites unretrieved sources: {', '.join(essay_bad)}")

        result = {
            "citation_check": integrity_check(
                "C0b", "citation_integrity_essay", essay_bad
            ),
            "essay": composed.get("essay", ""),
            "essay_title": composed.get("title", ""),
            "key_takeaway": composed.get("key_takeaway", ""),
            "open_questions": composed.get("open_questions", []),
            "questions": questions,
            "sources_examined": len(sources),
            "sources": [s.to_dict() for s in sources],
        }
        return v._finish(trace, result)


def _slim(s: Source) -> dict[str, Any]:
    """Trim a source to what the model needs — abstracts capped to control cost."""
    d = s.to_dict()
    d["abstract"] = d["abstract"][:2200]
    return d


def _extract_master_prompt(path: Path) -> str:
    """PROMPT.md holds the prompt inside the first ```text fence."""
    match = re.search(r"```text\s*(.*?)```", path.read_text(), re.DOTALL)
    if not match:
        raise RuntimeError(f"no ```text prompt block found in {path}")
    return match.group(1).strip()

"""Veritas pipeline orchestrator.

decompose -> search -> fetch -> extract (fan-out) -> grade -> synthesize -> verify
                ^                                                              |
                +---------------- needs_more_evidence --------------------------+
"""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import yaml

from llm import LLM, LLMError
from sources import Source, fetch_all

ROOT = Path(__file__).parent


class Trace:
    """Append-only run log. Written to disk so the README can cite real runs."""

    def __init__(self, claim: str, verbose: bool = True) -> None:
        self.claim = claim
        self.verbose = verbose
        self.started = time.time()
        self.steps: list[dict[str, Any]] = []

    def log(self, msg: str = "") -> None:
        if self.verbose:
            print(msg, flush=True)

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
        path = ROOT / "runs" / f"{int(self.started)}-{slug}.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps({
            "claim": self.claim,
            "wall_clock_seconds": round(time.time() - self.started, 1),
            "tokens": {"input": usage.input_tokens, "output": usage.output_tokens},
            "steps": self.steps,
            "result": result,
        }, indent=2))
        return path


class Veritas:
    def __init__(self, verbose: bool = True) -> None:
        self.cfg = yaml.safe_load((ROOT / "config.yaml").read_text())
        self.llm = LLM(self.cfg["model"])
        self.verbose = verbose
        self.master = _extract_master_prompt(ROOT.parent / "PROMPT.md")

    # ---------------------------------------------------------------- skills

    def _invoke(self, skill: str, payload: dict[str, Any], trace: Trace,
                round_no: int) -> dict[str, Any]:
        """One LLM skill call: master prompt + skill contract + typed payload."""
        spec = self.cfg["skills"][skill]
        contract = (ROOT / spec["prompt"]).read_text()
        system = f"{self.master}\n\n---\n\n{contract}"
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
        trace = Trace(claim, self.verbose)
        max_rounds = self.cfg["pipeline"]["max_rounds"]
        log = trace.log

        log(f"\n  CLAIM  {claim}\n" + "  " + "-" * 68)

        # --- 1. decompose ----------------------------------------------------
        log("\n  [1/7] decompose")
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
            log("\n  [2/7] search")
            search_out = self._invoke("search", {
                "claim": claim, "decomposition": decomp,
                "ROUND": round_no, "MAX_ROUNDS": max_rounds,
                "VERIFIER_FEEDBACK": feedback, "gaps_to_search": gaps,
            }, trace, round_no)
            queries = search_out.get("queries", [])
            stances = {q.get("stance") for q in queries}
            log(f"        {len(queries)} queries | stances: {', '.join(sorted(s for s in stances if s))}")

            # --- 3. fetch (deterministic) ------------------------------------
            log("\n  [3/7] fetch")
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
            log("\n  [4/7] extract  (parallel fan-out)")
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

            # --- 5. grade ----------------------------------------------------
            log("\n  [5/7] grade")
            grade_out = self._invoke("grade", {
                "claim": claim, "findings": usable,
                "sources": [_slim(s) for s in all_sources],
            }, trace, round_no)
            grades = grade_out.get("grades", [])
            weights = [g.get("weight", 0) for g in grades] or [0]
            log(f"        {len(grades)} graded | weight max {max(weights)} "
                f"mean {round(sum(weights)/len(weights), 2)}")

            # --- 6. synthesize ----------------------------------------------
            log("\n  [6/7] synthesize")
            synthesis = self._invoke("synthesize", {
                "claim": claim, "decomposition": decomp,
                "findings": usable, "grades": grades,
                "ROUND": round_no, "MAX_ROUNDS": max_rounds,
            }, trace, round_no)
            log(f"        verdict: {synthesis.get('verdict')} "
                f"({synthesis.get('confidence')})")

            # --- 7. verify ---------------------------------------------------
            log("\n  [7/7] verify  (adversarial audit)")
            audit = self._invoke("verify", {
                "claim": claim, "decomposition": decomp,
                "synthesis": synthesis, "findings": usable, "grades": grades,
                "ROUND": round_no, "MAX_ROUNDS": max_rounds,
            }, trace, round_no)
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

        result = dict(synthesis)
        result["audit"] = audit
        result["sources_examined"] = len(all_sources)
        result["rounds"] = round_no
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
        }
        return result


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

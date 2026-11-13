"""The citation gate is wired into the run loop, not just available as a helper.

Stubs the LLM and `fetch_all` so the whole claim pipeline runs offline. Proves
the two things the gate has to do: inject a check row the existing renderers
already know how to print, and override an `approved` audit so a bad citation
actually costs a round instead of being reported and ignored.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import orchestrator
from llm import Usage
from sources import Source


class StubLLM:
    def __init__(self, cfg=None):
        self.usage = Usage()


def make_source(sid: str) -> Source:
    return Source(id=sid, title=f"Title {sid}", abstract="An abstract.")


class GateTests(unittest.TestCase):
    def setUp(self):
        self.real_llm, self.real_fetch = orchestrator.LLM, orchestrator.fetch_all
        orchestrator.LLM = StubLLM
        orchestrator.fetch_all = lambda queries, cfg, seen, log: (
            [make_source("PMID:111"), make_source("PMID:222")], set(seen) | {"PMID:111", "PMID:222"}
        )

    def tearDown(self):
        orchestrator.LLM, orchestrator.fetch_all = self.real_llm, self.real_fetch

    def run_with(self, rationale: str):
        """Run the claim pipeline with every LLM skill stubbed out."""
        calls: list[str] = []

        def fake_invoke(self, skill, payload, trace, round_no):
            calls.append(skill)
            return {
                "decompose": {"sub_claims": [{"id": "SC1", "text": "c"}], "falsifier": "f"},
                "search": {"queries": [{"query": "q", "stance": "baseline"}]},
                "extract": {"findings": [{"source_id": "PMID:111", "direction": "supports"}],
                            "unusable_sources": []},
                "grade": {"grades": [{"source_id": "PMID:111", "weight": 2.0}]},
                "synthesize": {"verdict": "supported", "confidence": "high",
                               "verdict_rationale": rationale},
                "verify": {"verdict": "approved", "checks": [
                    {"id": "C1", "name": "citation_integrity", "result": "pass"}],
                    "weakest_link": "—"},
                "compose": {"title": "T", "essay": "Body citing PMID:111.",
                            "key_takeaway": "k"},
            }[skill]

        agent = orchestrator.Veritas.__new__(orchestrator.Veritas)
        agent.cfg = {"pipeline": {"max_rounds": 2}}
        agent.verbose = False
        agent.on_log = None
        agent.llm = StubLLM(None)
        agent.master = ""
        agent._invoke = fake_invoke.__get__(agent, orchestrator.Veritas)
        agent._finish = lambda trace, result: result

        return agent.run("a claim"), calls

    def test_clean_rationale_is_approved_in_one_round(self):
        result, calls = self.run_with("Supported by PMID:111 and PMID:222.")
        checks = {c["id"]: c for c in result["audit"]["checks"]}
        self.assertEqual(checks["C0"]["result"], "pass")
        self.assertEqual(checks["C0b"]["result"], "pass")
        self.assertEqual(result["audit"]["verdict"], "approved")
        self.assertEqual(result["rounds"], 1)

    def test_unretrieved_citation_overrides_approval_and_forces_a_retry(self):
        result, calls = self.run_with("Supported by PMID:999.")
        checks = {c["id"]: c for c in result["audit"]["checks"]}
        self.assertEqual(checks["C0"]["result"], "fail")
        self.assertIn("pmid:999", checks["C0"]["reason"])
        # The LLM auditor said `approved`; the deterministic check overruled it,
        # so the pipeline spent its second round instead of shipping the verdict.
        self.assertEqual(result["rounds"], 2)
        self.assertEqual(calls.count("search"), 2)
        self.assertTrue(any("PMID:999" in c or "pmid:999" in c
                            for c in result["audit"]["required_changes"]))

    def test_check_row_is_shaped_for_the_existing_renderers(self):
        result, _ = self.run_with("Supported by PMID:999.")
        # cli.py and app.py both count `result == "pass"` over audit["checks"].
        for row in result["audit"]["checks"]:
            self.assertIn("id", row)
            self.assertIn("name", row)
            self.assertIn(row["result"], {"pass", "fail"})

    def test_all_irrelevant_on_final_round_yields_insufficient_evidence(self):
        """Every finding irrelevant, out of rounds -> a verdict grounded in
        zero evidence must not ship. Mirrors the no-sources-retrieved branch."""
        calls: list[str] = []

        def fake_invoke(self, skill, payload, trace, round_no):
            calls.append(skill)
            return {
                "decompose": {"sub_claims": [{"id": "SC1", "text": "c"}], "falsifier": "f"},
                "search": {"queries": [{"query": "q", "stance": "baseline"}]},
                "extract": {"findings": [{"source_id": "PMID:111", "direction": "irrelevant"}],
                            "unusable_sources": []},
            }[skill]

        agent = orchestrator.Veritas.__new__(orchestrator.Veritas)
        agent.cfg = {"pipeline": {"max_rounds": 2}}
        agent.verbose = False
        agent.on_log = None
        agent.llm = StubLLM(None)
        agent.master = ""
        agent._invoke = fake_invoke.__get__(agent, orchestrator.Veritas)
        agent._finish = lambda trace, result: result

        result = agent.run("a claim")
        self.assertEqual(result["verdict"], "insufficient_evidence")
        self.assertEqual(calls.count("search"), 2)  # retried once, then bailed
        self.assertNotIn("grade", calls)
        self.assertNotIn("compose", calls)

    def test_topic_mode_all_irrelevant_yields_no_essay(self):
        """Topic mode has no retry loop, so this is the only guard it gets."""
        calls: list[str] = []

        def fake_invoke(self, skill, payload, trace, round_no):
            calls.append(skill)
            return {
                "scope": {"questions": [{"id": "Q1", "text": "q"}],
                          "normalized_topic": "t"},
                "search": {"queries": [{"query": "q", "stance": "baseline"}]},
                "extract": {"findings": [{"source_id": "PMID:111", "direction": "irrelevant"}],
                            "unusable_sources": []},
            }[skill]

        explorer = orchestrator.TopicExplorer.__new__(orchestrator.TopicExplorer)
        agent = orchestrator.Veritas.__new__(orchestrator.Veritas)
        agent.cfg = {"pipeline": {"max_rounds": 2}}
        agent.verbose = False
        agent.on_log = None
        agent.llm = StubLLM(None)
        agent.master = ""
        agent._invoke = fake_invoke.__get__(agent, orchestrator.Veritas)
        agent._finish = lambda trace, result: result
        explorer._v = agent

        result = explorer.run_topic("a topic")
        self.assertEqual(result["essay"], "")
        self.assertIn("extract", calls)  # pin past fetch, into the new guard
        self.assertNotIn("grade", calls)
        self.assertNotIn("compose_topic", calls)


if __name__ == "__main__":
    unittest.main()

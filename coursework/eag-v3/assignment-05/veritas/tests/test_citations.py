"""Deterministic citation-integrity tests. No API key, no network.

The headline case is a regression test against the real defect the README
documents: run 2 cited `PMID:4059230` in its prose `verdict_rationale` while
the retrieved set contained `PMID:9059230`, and the LLM verifier's C1 check
passed anyway.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from citations import citation_violations, cited_ids, integrity_check

RUNS = Path(__file__).resolve().parents[1] / "runs"
VITAMIN_C = "1784487163-vitamin-c-supplementation-prevents-the-common-co.json"


def load_trace(name: str) -> dict:
    return json.loads((RUNS / name).read_text())


def retrieved_ids(trace: dict) -> set[str]:
    """Ids the pipeline actually saw.

    These traces predate `result["sources"]` being persisted, so the retrieved
    set is reconstructed from the extract/grade steps — every id that reached
    those stages came out of `fetch`.
    """
    seen: set[str] = set()
    for step in trace["steps"]:
        out = step.get("output") or {}
        for item in (out.get("findings") or []) + (out.get("grades") or []):
            if isinstance(item, dict) and item.get("source_id"):
                seen.add(str(item["source_id"]))
    return seen


class CitationScanTests(unittest.TestCase):
    def test_finds_ids_in_prose_not_just_structured_fields(self):
        payload = {
            "verdict_rationale": "No effect on incidence (PMID:4059230).",
            "supporting_evidence": [{"source_id": "PMID:10796569"}],
        }
        self.assertEqual(
            cited_ids(payload), {"pmid:4059230", "pmid:10796569"}
        )

    def test_trailing_punctuation_and_case_are_normalised(self):
        payload = {"essay": "As shown in ARXIV: 2206.14521v2 and (PMID:9059230)."}
        self.assertEqual(
            citation_violations(payload, ["arXiv:2206.14521v2", "PMID:9059230"]), []
        )

    def test_odd_casing_does_not_hide_a_bad_id(self):
        """A clean-payload test can't tell 'normalised' from 'never extracted'.

        Both of these must be *caught*: if the scanner is case-sensitive the id
        is never extracted, never compared, and silently passes the check.
        """
        self.assertEqual(
            citation_violations({"essay": "see pmid:9999999"}, ["PMID:111"]),
            ["pmid:9999999"],
        )
        self.assertEqual(
            citation_violations({"essay": "see ARXIV:9999.99999"}, ["PMID:111"]),
            ["arxiv:9999.99999"],
        )

    def test_arxiv_version_suffix_is_not_a_violation(self):
        """The API mints `v2`; a citation may drop it. That is not a fabrication.

        A false positive here costs a whole retry round, so the comparison
        ignores the version suffix in both directions.
        """
        self.assertEqual(
            citation_violations({"essay": "see arXiv:2206.14521"},
                                ["arXiv:2206.14521v2"]), []
        )
        self.assertEqual(
            citation_violations({"essay": "see arXiv:2206.14521v3"},
                                ["arXiv:2206.14521"]), []
        )
        # ...but a genuinely different arXiv id still fails.
        self.assertEqual(
            citation_violations({"essay": "see arXiv:2206.99999v1"},
                                ["arXiv:2206.14521v2"]), ["arxiv:2206.99999"]
        )

    def test_clean_payload_has_no_violations(self):
        payload = {"rationale": "See PMID:9059230."}
        self.assertEqual(citation_violations(payload, ["PMID:9059230"]), [])

    def test_unretrieved_id_is_reported(self):
        payload = {"rationale": "See PMID:9059230 and PMID:1111111."}
        self.assertEqual(
            citation_violations(payload, ["PMID:9059230"]), ["pmid:1111111"]
        )

    def test_check_row_shape_matches_verify_checks(self):
        row = integrity_check("C0", "citation_integrity_deterministic", [])
        self.assertEqual(row["result"], "pass")
        self.assertEqual(
            integrity_check("C0", "n", ["pmid:1"])["result"], "fail"
        )


class RunTraceRegressionTests(unittest.TestCase):
    """The defect the README calls the top open item."""

    def test_vitamin_c_run_malformed_pmid_is_caught(self):
        trace = load_trace(VITAMIN_C)
        result = dict(trace["result"])
        result.pop("sources", None)

        violations = citation_violations(result, retrieved_ids(trace))

        self.assertIn("pmid:4059230", violations,
                      "the corrupted digit in verdict_rationale must be flagged")
        # It really is prose-only: it appears in no structured source_id field.
        structured = {
            e.get("source_id")
            for key in ("supporting_evidence", "contradicting_evidence")
            for e in (result.get(key) or [])
        }
        self.assertNotIn("PMID:4059230", structured)
        # And the LLM verifier passed it, which is the point of doing this in code.
        c1 = next(c for c in result["audit"]["checks"] if c["id"] == "C1")
        self.assertEqual(c1["result"], "pass")

    def test_creatine_run_is_clean(self):
        trace = load_trace(
            "1784487078-creatine-supplementation-improves-cognitive-perf.json"
        )
        result = dict(trace["result"])
        result.pop("sources", None)
        self.assertEqual(citation_violations(result, retrieved_ids(trace)), [])


if __name__ == "__main__":
    unittest.main()

"""The judge: the known answers decide, and the judge itself cannot be swapped out."""
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from ftb import workspace

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"
FEE_CASES = json.loads((ROOT / "examples" / "fees" / "cases.json").read_text())
REBALANCE_CASES = json.loads((ROOT / "examples" / "rebalance" / "cases.json").read_text())


@unittest.skipUnless(shutil.which("node") and shutil.which("git"), "needs node and git")
class CheckTool(unittest.TestCase):
    def setUp(self):
        self.root = Path(os.path.realpath(tempfile.mkdtemp())) / "workspace"
        self.addCleanup(shutil.rmtree, self.root.parent, ignore_errors=True)
        self.prints = workspace.prepare(self.root, spec_markdown="# spec\n", cases=FEE_CASES, previous_page=None)

    def check(self, page: str) -> dict:
        (self.root / "index.html").write_text(page)
        return workspace.verify(self.root, self.prints)

    def test_the_supplied_fee_answers_pass_on_a_correct_calculator(self):
        result = self.check((FIXTURES / "fee_right.html").read_text())
        self.assertTrue(result["passed"], result["output"])
        self.assertIn("examples passed: 3 of 3", result["output"])

    def test_a_calculator_that_applies_one_rate_to_the_whole_balance_fails_with_the_numbers(self):
        result = self.check((FIXTURES / "fee_wrong.html").read_text())
        self.assertFalse(result["passed"])
        self.assertEqual(result["exit_code"], 1)
        self.assertIn("result.quarterly_fee: expected 6250, got 5625", result["output"])

    def test_no_page_at_all_is_a_failure_with_a_reason(self):
        result = workspace.verify(self.root, self.prints)
        self.assertFalse(result["passed"])
        self.assertIn("did not produce index.html", result["reason"])

    def test_a_page_that_loads_an_outside_script_is_not_standalone(self):
        page = (FIXTURES / "fee_right.html").read_text().replace(
            "</head>", '<script src="https://cdn.example.invalid/x.js"></script></head>')
        self.assertIn("[standalone]", self.check(page)["output"])

    def test_arithmetic_that_reaches_into_the_page_breaks_the_contract(self):
        page = (FIXTURES / "fee_right.html").read_text().replace(
            "var aum = Math.max(0, Number(input.aum) || 0);",
            "var aum = Number(document.getElementById('aum').value);")
        result = self.check(page)
        self.assertFalse(result["passed"])
        self.assertIn("calculate threw", result["output"])

    def test_hard_coding_cannot_pass_by_rewriting_the_expected_answers(self):
        (self.root / "index.html").write_text((FIXTURES / "fee_wrong.html").read_text())
        (self.root / "checks" / "cases.json").write_text('{"cases": []}')
        result = workspace.verify(self.root, self.prints)
        self.assertFalse(result["passed"])
        self.assertIn("protected files changed", result["reason"])
        self.assertIn("checks/cases.json", result["reason"])

    def test_the_check_cannot_read_outside_the_workspace(self):
        outside = self.root.parent / "secret.txt"
        outside.write_text("S17_CONTROL_TOKEN=do-not-leak")
        (self.root / "checks" / "check_tool.js").write_text(
            f'console.log(require("fs").readFileSync({json.dumps(str(outside))}, "utf8"));')
        prints = workspace.fingerprints(self.root)       # as if this were the shipped judge
        (self.root / "index.html").write_text("<html></html>")
        result = workspace.verify(self.root, prints)
        self.assertFalse(result["passed"])
        self.assertNotIn("do-not-leak", result["output"])

    def test_a_folder_this_app_did_not_create_is_never_cleared(self):
        foreign = self.root.parent / "my-real-work"
        foreign.mkdir()
        (foreign / "thesis.txt").write_text("irreplaceable")
        with self.assertRaises(workspace.WorkspaceError):
            workspace.prepare(foreign, spec_markdown="x", cases=FEE_CASES, previous_page=None)
        self.assertEqual((foreign / "thesis.txt").read_text(), "irreplaceable")

    def test_the_workspace_is_its_own_repository(self):
        self.assertTrue((self.root / ".git").is_dir())


@unittest.skipUnless(shutil.which("node") and shutil.which("git"), "needs node and git")
class RebalanceAnswers(unittest.TestCase):
    """Route 1's supplied example, checked against a hand-written reference calculator."""

    def test_the_supplied_rebalance_answers_pass_on_the_reference_calculator(self):
        root = Path(os.path.realpath(tempfile.mkdtemp())) / "workspace"
        self.addCleanup(shutil.rmtree, root.parent, ignore_errors=True)
        prints = workspace.prepare(root, spec_markdown="# spec\n", cases=REBALANCE_CASES, previous_page=None)
        (root / "index.html").write_text((FIXTURES / "rebalance_right.html").read_text())
        result = workspace.verify(root, prints)
        self.assertTrue(result["passed"], result["output"])


if __name__ == "__main__":
    unittest.main()

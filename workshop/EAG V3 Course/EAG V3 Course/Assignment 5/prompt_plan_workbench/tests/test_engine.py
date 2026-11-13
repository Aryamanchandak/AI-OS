from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine import (
    CRITERIA,
    ModelSettings,
    WorkbenchError,
    apply_improvements,
    converse,
    evaluate_content,
    load_constructor_prompt,
    load_rubric,
)


def evaluation_fixture(status: str = "yes") -> dict:
    return {
        "summary": "Clear and testable.",
        "verdict": "Strong",
        "criteria": [
            {"key": key, "status": status, "evidence": f"Evidence for {label}.", "recommendation": "Improve it."}
            for key, label in CRITERIA
        ],
        "strengths": ["Good structure"],
        "improvements": [
            {"id": "add-fallback", "title": "Add fallback", "priority": "high", "why": "Avoid failure", "instruction": "Add a fallback", "preview": "If X fails…"}
        ],
    }


class EngineTests(unittest.TestCase):
    def test_canonical_rubric_is_loaded(self):
        rubric = load_rubric()
        self.assertIn("Prompt Evaluation Assistant", rubric)
        self.assertIn("Internal Self-Checks", rubric)

    def test_evaluation_computes_score_without_model_supplied_score(self):
        def fake_complete(system, user, settings):
            self.assertIn("Prompt Evaluation Assistant", system)
            self.assertIn("<context>", user)
            return evaluation_fixture("partial")

        result = evaluate_content("Do the task", "Used by analysts", "prompt", ModelSettings(), fake_complete)
        self.assertEqual(result["score"], 50)
        self.assertEqual(len(result["criteria"]), 9)

    def test_plan_contract_adapts_rubric_to_entire_process(self):
        observed = {}

        def fake_complete(system, user, settings):
            observed["system"] = system
            return evaluation_fixture()

        evaluate_content("Research, build, test, launch", "Small team", "plan", ModelSettings(), fake_complete)
        self.assertIn("full intended process", observed["system"])
        self.assertIn("review gates", observed["system"])

    def test_missing_criterion_is_rejected(self):
        broken = evaluation_fixture()
        broken["criteria"].pop()
        with self.assertRaisesRegex(WorkbenchError, "missing criterion"):
            evaluate_content("Something", "", "prompt", ModelSettings(), lambda *_: broken)

    def test_only_selected_improvements_are_sent_for_rewrite(self):
        observed = {}

        def fake_complete(system, user, settings):
            observed["user"] = user
            return {"revised_content": "Improved prompt", "applied": [{"id": "chosen"}], "preserved": ["Intent"]}

        selected = [{"id": "chosen", "title": "Chosen", "instruction": "Apply me"}]
        result = apply_improvements("Original", "Context", "prompt", selected, ModelSettings(), fake_complete)
        self.assertEqual(result["revised_content"], "Improved prompt")
        self.assertIn("chosen", observed["user"])

    def test_rewrite_requires_a_selection(self):
        with self.assertRaisesRegex(WorkbenchError, "Select at least one"):
            apply_improvements("Original", "Context", "prompt", [], ModelSettings())

    def test_constructor_prompt_is_loaded(self):
        prompt = load_constructor_prompt()
        self.assertIn("Prompt Constructor", prompt)
        self.assertIn("exactly one question", prompt)

    def test_constructor_prompt_missing_and_empty_files_are_rejected(self):
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(WorkbenchError, "Could not read constructor prompt"):
                load_constructor_prompt(root / "missing.md")
            empty = root / "empty.md"
            empty.write_text("  \n", encoding="utf-8")
            with self.assertRaisesRegex(WorkbenchError, "constructor prompt is empty"):
                load_constructor_prompt(empty)

    def test_converse_normalizes_a_question_turn(self):
        def fake_complete(system, messages, settings):
            self.assertIn("RUNTIME BOUND", system)
            self.assertEqual(messages[-1]["content"], "Help me make a research prompt")
            return '''{
                "question": "Should this be a prompt or a plan?",
                "notes": "Goal: support scientific research.",
                "ready": false,
                "draft_kind": null,
                "draft_content": "",
                "draft_context": ""
            }'''

        result = converse(
            [{"role": "user", "content": "Help me make a research prompt"}],
            ModelSettings(),
            fake_complete,
        )
        self.assertFalse(result["ready"])
        self.assertEqual(result["draft_kind"], None)
        self.assertIn("prompt or a plan", result["question"])

    def test_converse_normalizes_a_ready_draft(self):
        response = {
            "question": "",
            "notes": "Audience: analysts; format: cited brief.",
            "ready": True,
            "draft_kind": "prompt",
            "draft_content": "Research the topic and return a cited brief.",
            "draft_context": "Used by analysts; citations required.",
        }
        result = converse(
            [{"role": "user", "content": "Draft what you have"}],
            ModelSettings(),
            lambda *_: __import__("json").dumps(response),
        )
        self.assertTrue(result["ready"])
        self.assertEqual(result["draft_kind"], "prompt")

    def test_converse_rejects_missing_shape(self):
        with self.assertRaisesRegex(WorkbenchError, "missing"):
            converse(
                [{"role": "user", "content": "Build something"}],
                ModelSettings(),
                lambda *_: '{"question": "What kind?"}',
            )


if __name__ == "__main__":
    unittest.main()

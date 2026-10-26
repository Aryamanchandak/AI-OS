"""Claude replies must match the structures in prompts/question.md and prompts/evaluation.md."""
import copy
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]

CHART = {
    "kind": "bar", "title": "Revenue", "x_label": "Year", "y_label": "GBP m",
    "categories": ["2022", "2023"],
    "series": [{"name": "UK", "values": [10, 12.5]}, {"name": "US", "values": [8, 9]}],
    "source_note": "Illustrative data",
}
QUESTION = {
    "type": "chart", "question": "What stands out?", "context_note": "A retailer.",
    "chart": CHART, "assessing": ["insight"], "strong_answer_covers": ["UK grew 25%"],
    "common_mistakes": ["reading numbers out"],
}
GRADE = {
    "overall_score": 6, "verdict": "Average.", "retry_focus": "Lead with the answer.",
    "content_scores": [{"dimension": "Structure", "score": 5, "comment": "Loose."}],
    "what_worked": ["Clear example"],
    "top_fixes": [{"issue": "No result", "evidence": "'we shipped'", "fix": "Quantify it"}],
    "missed_points": ["Learning"],
    "delivery_feedback": [{"issue": "Fillers", "evidence": "0:12 um", "fix": "Pause instead"}],
    "model_answer": "In my last role...",
}


def load(module, name, extra=None):
    spec = importlib.util.spec_from_file_location(name, ROOT / module)
    mod = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, extra or {}):
        spec.loader.exec_module(mod)
    return mod


def edited(base, **changes):
    out = copy.deepcopy(base)
    for key, value in changes.items():
        if value is KeyError:
            del out[key]
        else:
            out[key] = value
    return out


class SchemaTests(unittest.TestCase):
    def setUp(self):
        self.schema = load("schema.py", "reply_schema")

    def bad_chart(self, **changes):
        return edited(QUESTION, chart=edited(CHART, **changes))

    def test_valid_replies_pass(self):
        self.schema.validate_question(QUESTION)
        self.schema.validate_question(edited(QUESTION, type="case", chart=None, context_note=""))
        self.schema.validate_question(edited(QUESTION, type=KeyError, context_note=KeyError, chart=None))
        self.schema.validate_grade(GRADE)
        self.schema.validate_grade(edited(GRADE, top_fixes=[], what_worked=[], missed_points=[]))

    def test_question_rejects_missing_or_wrong_fields(self):
        for bad in (
            {}, [], "text",
            edited(QUESTION, question=KeyError), edited(QUESTION, question="  "),
            edited(QUESTION, type="nonsense"), edited(QUESTION, context_note=5),
            edited(QUESTION, assessing="a string"), edited(QUESTION, assessing=[]),
            edited(QUESTION, strong_answer_covers=[1, 2]), edited(QUESTION, common_mistakes=KeyError),
            edited(QUESTION, chart=KeyError), edited(QUESTION, chart=None),  # chart type needs a chart
            edited(QUESTION, chart="bar chart"),
        ):
            with self.assertRaises(ValueError, msg=str(bad)[:80]):
                self.schema.validate_question(bad)

    def test_chart_must_be_consistent_and_finite(self):
        for bad in (
            self.bad_chart(kind="pie"), self.bad_chart(title=KeyError),
            self.bad_chart(categories=[]), self.bad_chart(categories="2022"),
            self.bad_chart(categories=[str(i) for i in range(9)]),
            self.bad_chart(series=[]), self.bad_chart(series=[CHART["series"][0]] * 5),
            self.bad_chart(series=[{"name": "UK", "values": [10]}]),  # too short
            self.bad_chart(series=[{"name": "UK", "values": [1, 2, 3]}]),  # too long
            self.bad_chart(series=[{"name": "UK", "values": [1, "2"]}]),
            self.bad_chart(series=[{"name": "UK", "values": [1, True]}]),
            self.bad_chart(series=[{"name": "UK", "values": [1, float("nan")]}]),
            self.bad_chart(series=[{"name": "UK", "values": [1, float("inf")]}]),
            self.bad_chart(series=[{"values": [1, 2]}]),
            self.bad_chart(y_label=3),
        ):
            with self.assertRaises(ValueError, msg=str(bad["chart"])[:80]):
                self.schema.validate_question(bad)

    def test_grade_rejects_missing_fields_and_wrong_types(self):
        for bad in (
            {}, [], {"overall_score": 99, "top_fixes": "wrong type"},
            edited(GRADE, overall_score=0), edited(GRADE, overall_score=11), edited(GRADE, overall_score=99),
            edited(GRADE, overall_score=7.5), edited(GRADE, overall_score="7"), edited(GRADE, overall_score=True),
            edited(GRADE, overall_score=KeyError), edited(GRADE, verdict=""), edited(GRADE, retry_focus=KeyError),
            edited(GRADE, top_fixes="wrong type"), edited(GRADE, top_fixes=["just text"]),
            edited(GRADE, top_fixes=[{"issue": "x"}]),
            edited(GRADE, what_worked="fine"), edited(GRADE, missed_points=[3]),
            edited(GRADE, delivery_feedback={"issue": "x"}),
            edited(GRADE, content_scores=[]), edited(GRADE, content_scores=[{"dimension": "A", "score": 11, "comment": "x"}]),
            edited(GRADE, content_scores=[{"dimension": "A", "score": "5", "comment": "x"}]),
            edited(GRADE, content_scores=[{"dimension": "A", "comment": "x"}]),
            edited(GRADE, model_answer=None), edited(GRADE, model_answer=KeyError),
        ):
            with self.assertRaises(ValueError, msg=str(bad)[:80]):
                self.schema.validate_grade(bad)


class LlmRetryTests(unittest.TestCase):
    """_json_call re-asks once on a malformed or invalid reply, then fails loudly."""

    def setUp(self):
        self.schema = load("schema.py", "schema")
        anthropic = types.ModuleType("anthropic")
        anthropic.Anthropic = Mock()
        self.llm = load("llm.py", "checked_llm", {"anthropic": anthropic, "schema": self.schema})
        self.create = Mock()
        fake = Mock()
        fake.messages.create = self.create
        self.llm._client = fake

    def reply(self, payload):
        text = payload if isinstance(payload, str) else json.dumps(payload)
        return types.SimpleNamespace(content=[types.SimpleNamespace(type="text", text=text)])

    def test_invalid_grade_twice_raises_instead_of_saving(self):
        self.create.side_effect = [self.reply({"overall_score": 99, "top_fixes": "wrong type"})] * 2
        with self.assertRaises(RuntimeError):
            self.llm.grade({"question": "Q"}, "", 30, 90, "answer", {})
        self.assertEqual(self.create.call_count, 2)

    def test_empty_object_question_raises(self):
        self.create.side_effect = [self.reply({})] * 2
        with self.assertRaises(RuntimeError):
            self.llm.generate_question("case", "", 30, 90, [])

    def test_one_invalid_reply_is_retried(self):
        self.create.side_effect = [self.reply({}), self.reply(GRADE)]
        self.assertEqual(self.llm.grade({"question": "Q"}, "", 30, 90, "a", {})["overall_score"], 6)

    def test_valid_question_still_works_and_non_chart_drops_chart(self):
        q = edited(QUESTION, type="case")
        self.create.side_effect = [self.reply(q)]
        out = self.llm.generate_question("case", "", 30, 90, [])
        self.assertIsNone(out["chart"])
        self.assertEqual(out["question"], "What stands out?")


if __name__ == "__main__":
    unittest.main()

"""Check the actual LLM adapter uses the selected instructions."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch


class PromptAdapterTests(unittest.TestCase):
    def setUp(self):
        anthropic = types.ModuleType('anthropic')
        anthropic.Anthropic = Mock()
        path = Path(__file__).resolve().parents[1] / 'llm.py'
        with patch.dict(sys.modules, {'anthropic': anthropic}):
            spec = importlib.util.spec_from_file_location('prompt_llm', path)
            self.llm = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.llm)
        self.llm._json_call = Mock(return_value={'type': 'case', 'question': 'Example'})

    def test_custom_question_prompt_keeps_context_and_timers(self):
        self.llm.generate_question('case', 'Engineering interview', 45, 120, [], system_prompt='Custom question rules')
        system, user, _ = self.llm._json_call.call_args.args
        self.assertEqual(system, 'Custom question rules')
        for value in ('Engineering interview', 'case', '45', '120'):
            self.assertIn(value, user)

    def test_custom_grading_prompt_keeps_answer_and_metrics(self):
        self.llm.grade({'question': 'Example'}, 'Engineering interview', 45, 120,
                       'My actual answer', {'pace_wpm': 140}, system_prompt='Custom evaluation rules')
        system, user, _ = self.llm._json_call.call_args.args
        self.assertEqual(system, 'Custom evaluation rules')
        for value in ('Engineering interview', 'My actual answer', '140', '45', '120'):
            self.assertIn(value, user)

    def test_default_prompts_remain_available(self):
        self.llm.generate_question('case', '', 30, 90, [])
        self.assertEqual(self.llm._json_call.call_args.args[0], self.llm.GEN_SYSTEM)
        self.llm.grade({}, '', 30, 90, '', {})
        self.assertEqual(self.llm._json_call.call_args.args[0], self.llm.GRADE_SYSTEM)

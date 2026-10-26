"""Prep/answer seconds are validated before Claude or the recording is touched."""
import importlib.util
import io
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class TimerSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        target = root / 'app.py'
        target.write_text((Path(__file__).resolve().parents[1] / 'app.py').read_text())
        self.analysis = types.ModuleType('analysis')
        self.analysis.BASELINE_PATH = root / 'baseline.json'
        self.analysis.analyse = Mock(return_value={
            'metrics': {'speech_detected': True}, 'transcript': 'x',
            'annotated_transcript': 'x', 'pauses': [], 'gaze_segments': []})
        self.llm = types.ModuleType('llm')
        self.llm.GEN_SYSTEM, self.llm.GRADE_SYSTEM = 'q', 'e'
        self.llm.generate_question = Mock(return_value={'type': 'case', 'question': 'A case', 'chart': None})
        self.llm.grade = Mock(return_value={'overall_score': 7})
        with patch.dict(sys.modules, {'analysis': self.analysis, 'llm': self.llm,
                                     'charts': types.ModuleType('charts')}):
            spec = importlib.util.spec_from_file_location('timer_app', target)
            self.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.module)
        self.module.app.config['TESTING'] = True
        self.client = self.module.app.test_client()
        (self.module.QDIR / 'q1.json').write_text(json.dumps(
            {'type': 'case', 'question': 'Q', 'chart': None}))

    def ask(self, prep, answer):
        return self.client.post('/api/question', json={'type': 'case', 'prep': prep, 'answer': answer})

    def submit(self, prep, answer):
        return self.client.post('/api/answer', data={
            'qid': 'q1', 'prep': prep, 'answer': answer,
            'video': (io.BytesIO(b'video'), 'answer.webm', 'video/webm')})

    def test_boundaries_pass(self):
        for prep, answer in ((0, 15), (300, 600), (30, 90), ('0', '15'), ('300', '600')):
            self.assertEqual(self.ask(prep, answer).status_code, 200, (prep, answer))
            self.assertEqual(self.submit(prep, answer).status_code, 200, (prep, answer))
        self.assertEqual(self.llm.generate_question.call_args.args[2:4], (300, 600))

    def test_default_when_not_sent(self):
        self.assertEqual(self.client.post('/api/question', json={'type': 'case'}).status_code, 200)
        self.assertEqual(self.llm.generate_question.call_args.args[2:4], (30, 90))

    def test_bad_values_are_400_and_do_nothing(self):
        bad = [(-1, 90), (30, 99999), (301, 90), (30, 14), (30, 601), (1.5, 90), (30, 90.5),
               ('abc', 90), (30, 'abc'), ('', 90), (30, ' '), (None, 90), (30, None),
               ('1.5', 90), ('-1', 90), ('+5', 90), (' 30', 90), (True, 90), ([], 90), (30, 1e9)]
        for prep, answer in bad:
            response = self.ask(prep, answer)
            self.assertEqual(response.status_code, 400, (prep, answer))
            self.assertIn('seconds', response.get_json()['error'])
        self.llm.generate_question.assert_not_called()
        for prep, answer in [p for p in bad if all(isinstance(v, (str, int)) and not isinstance(v, bool)
                                                   or v is None for v in p) and None not in p]:
            self.assertEqual(self.submit(prep, answer).status_code, 400, (prep, answer))
        self.assertEqual(list(self.module.ADIR.iterdir()), [])  # nothing saved
        self.analysis.analyse.assert_not_called()
        self.llm.grade.assert_not_called()

    def test_non_object_question_body_is_400(self):
        self.assertEqual(self.client.post('/api/question', json=[1, 2]).status_code, 400)


if __name__ == '__main__':
    unittest.main()

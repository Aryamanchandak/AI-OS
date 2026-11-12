"""Recovery checks with fake analysis and grading; no camera or API calls."""
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch


class GradingRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        source = Path(__file__).resolve().parents[1] / 'app.py'
        target = root / 'app.py'
        target.write_text(source.read_text())
        self.analysis = types.ModuleType('analysis')
        self.analysis.BASELINE_PATH = root / 'baseline.json'
        self.analysis.analyse = Mock(return_value={
            'metrics': {'speech_detected': True}, 'transcript': 'My answer',
            'annotated_transcript': '[0:00] My answer', 'pauses': [], 'gaze_segments': [],
        })
        self.llm = types.ModuleType('llm')
        self.llm.GEN_SYSTEM = 'Default question instructions'
        self.llm.GRADE_SYSTEM = 'Default evaluation instructions'
        self.llm.grade = Mock(return_value={'overall_score': 7, 'verdict': 'Good'})
        with patch.dict(sys.modules, {'analysis': self.analysis, 'llm': self.llm,
                                     'charts': types.ModuleType('charts')}):
            spec = importlib.util.spec_from_file_location('recovery_app', target)
            self.module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.module)
        self.module.app.config['TESTING'] = True
        self.client = self.module.app.test_client()
        self.module.CONTEXT_FILE.write_text('Original context')
        (self.module.QDIR / 'q1.json').write_text(json.dumps({
            'type': 'competency', 'question': 'Tell me about a project.', 'chart': None,
        }))

    def upload(self):
        return self.client.post('/api/answer', data={
            'qid': 'q1', 'prep': '30', 'answer': '90',
            'video': (io.BytesIO(b'recorded-video'), 'answer.webm', 'video/webm'),
        })

    def test_grading_failure_preserves_video_transcript_and_history(self):
        self.llm.grade.side_effect = RuntimeError('API unavailable')
        response = self.upload()
        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        self.assertEqual(result['status'], 'grading_failed')
        self.assertEqual(result['transcript'], 'My answer')
        self.assertIsNone(result['feedback'].get('overall_score'))
        folder = self.module.ADIR / result['id']
        self.assertEqual((folder / 'answer.webm').read_bytes(), b'recorded-video')
        self.assertEqual(json.loads((folder / 'result.json').read_text())['status'], 'grading_failed')
        self.assertEqual(self.client.get('/api/history').get_json()[0]['id'], result['id'])

    def test_retry_uses_saved_analysis_and_original_context(self):
        self.llm.grade.side_effect = RuntimeError('API unavailable')
        result = self.upload().get_json()
        self.module.CONTEXT_FILE.write_text('Different context')
        self.llm.grade.side_effect = None
        response = self.client.post('/api/attempt/' + result['id'] + '/retry')
        self.assertEqual(response.status_code, 200)
        result = response.get_json()
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['feedback']['overall_score'], 7)
        self.assertEqual(self.analysis.analyse.call_count, 1)
        self.assertEqual(self.llm.grade.call_args.args[1], 'Original context')
        self.assertNotIn('assessment_error', result)
        self.assertEqual(self.client.get('/api/attempt/' + result['id']).get_json()['status'], 'complete')
        self.client.post('/api/attempt/' + result['id'] + '/retry')
        self.assertEqual(self.llm.grade.call_count, 2)

    def test_analysis_failure_can_retry_saved_recording(self):
        self.analysis.analyse.side_effect = RuntimeError('Decode failed')
        result = self.upload().get_json()
        self.assertEqual(result['status'], 'analysis_failed')
        self.assertEqual(len(self.client.get('/api/history').get_json()), 1)
        self.llm.grade.assert_not_called()
        self.analysis.analyse.side_effect = None
        result = self.client.post('/api/attempt/' + result['id'] + '/retry').get_json()
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(self.analysis.analyse.call_count, 2)

    def test_repeated_grading_failure_remains_recoverable(self):
        self.llm.grade.side_effect = RuntimeError('API unavailable')
        result = self.upload().get_json()
        response = self.client.post('/api/attempt/' + result['id'] + '/retry')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['status'], 'grading_failed')
        self.assertEqual(response.get_json()['transcript'], 'My answer')

    def test_no_speech_does_not_call_grader(self):
        self.analysis.analyse.return_value['metrics']['speech_detected'] = False
        result = self.upload().get_json()
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['feedback']['overall_score'], 1)
        self.llm.grade.assert_not_called()


    def test_prompts_default_save_reload_and_reset(self):
        defaults = self.client.get('/api/prompts').get_json()
        self.assertEqual(defaults, {'question': self.llm.GEN_SYSTEM, 'evaluation': self.llm.GRADE_SYSTEM})
        custom = {'question': 'Ask about leadership.', 'evaluation': 'Assess clarity and evidence.'}
        self.assertEqual(self.client.post('/api/prompts', json=custom).get_json(), custom)
        self.assertEqual(self.client.get('/api/prompts').get_json(), custom)
        self.assertEqual((self.module.DATA / 'prompts' / 'question.md').read_text(), custom['question'])
        self.assertEqual(self.client.post('/api/prompts', json={'reset': True}).get_json(), defaults)
        self.assertEqual(self.client.get('/api/prompts').get_json(), defaults)

    def test_blank_or_invalid_prompts_do_not_overwrite_saved_prompts(self):
        custom = {'question': 'Ask about leadership.', 'evaluation': 'Assess clarity.'}
        self.client.post('/api/prompts', json=custom)
        for payload in ({'question': ' ', 'evaluation': 'Good'},
                        {'question': 'Good', 'evaluation': 10}, [], {}):
            self.assertEqual(self.client.post('/api/prompts', json=payload).status_code, 400)
            self.assertEqual(self.client.get('/api/prompts').get_json(), custom)

    def test_question_generation_receives_saved_prompt(self):
        self.llm.generate_question = Mock(return_value={'type': 'case', 'question': 'A case', 'chart': None})
        self.client.post('/api/prompts', json={'question': 'Custom questions', 'evaluation': 'Custom grading'})
        response = self.client.post('/api/question', json={'type': 'case', 'prep': 45, 'answer': 120})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.llm.generate_question.call_args.kwargs['system_prompt'], 'Custom questions')
        self.assertEqual(self.llm.generate_question.call_args.args[1:4], ('Original context', 45, 120))

    def test_retry_keeps_original_evaluation_prompt_after_edit(self):
        self.client.post('/api/prompts', json={'question': 'Custom questions', 'evaluation': 'Original rubric'})
        self.llm.grade.side_effect = RuntimeError('API unavailable')
        result = self.upload().get_json()
        self.assertEqual(self.llm.grade.call_args.kwargs['system_prompt'], 'Original rubric')
        self.client.post('/api/prompts', json={'question': 'New questions', 'evaluation': 'Changed rubric'})
        self.llm.grade.side_effect = None
        self.client.post('/api/attempt/' + result['id'] + '/retry')
        self.assertEqual(self.llm.grade.call_args.kwargs['system_prompt'], 'Original rubric')

    def test_missing_attempt_retry_is_404(self):
        self.assertEqual(self.client.post('/api/attempt/missing/retry').status_code, 404)


if __name__ == '__main__':
    unittest.main()

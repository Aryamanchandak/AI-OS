"""Exercise the user commands and answer a persisted question in a fresh process."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CommandTests(unittest.TestCase):
    def run_cli(self, state, *arguments):
        return subprocess.run([sys.executable, '-m', 'watchlist', '--state', str(state), *arguments],
                              cwd=ROOT, text=True, capture_output=True)

    def test_demo_then_resume_and_report_in_separate_processes(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / 'demo'
            result = self.run_cli(state, 'demo')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('SIMULATED', result.stdout)
            self.assertIn('pending', result.stdout)
            result = self.run_cli(state, 'answer', '4', '--decision', 'finding',
                                  '--answer', 'Yes, evaluate the preview locally.')
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('Completed item 4', result.stdout)
            result = self.run_cli(state, 'report')
            self.assertEqual(result.returncode, 0, result.stderr)
            brief = (state / 'brief.md').read_text()
            for fragment in ['Python 3.14.1', 'Repeated announcement', 'No new statement matched',
                             'Capture failed', 'Yes, evaluate the preview locally.', 'SIMULATED']:
                self.assertIn(fragment, brief)
            result = self.run_cli(state, 'demo')
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('empty state', result.stderr)
            result = self.run_cli(state, 'check')
            self.assertEqual(result.returncode, 2)
            self.assertIn('simulated demo', result.stderr)

    def test_answer_validation_returns_a_clear_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            result = self.run_cli(folder, 'answer', '999', '--decision', 'ignored', '--answer', 'No')
            self.assertEqual(result.returncode, 2)
            self.assertIn('No pending question', result.stderr)


if __name__ == '__main__':
    unittest.main()

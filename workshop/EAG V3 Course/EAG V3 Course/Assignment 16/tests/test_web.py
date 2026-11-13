"""Exercise the local dashboard HTTP boundary and persistent user answers."""

import json
import contextlib
import io
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from watchlist.config import load_watch
from watchlist.demo import run_demo
from watchlist.store import Store
from watchlist.web import create_server


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state = Path(self.temp.name)
        self.watch = load_watch(Path(__file__).resolve().parents[1] / 'watch.toml')
        self.server = create_server(self.watch, self.state, port=0)
        self.origin = f'http://127.0.0.1:{self.server.server_port}'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.thread.join()
        self.server.server_close()
        self.temp.cleanup()

    def request(self, path, body=None, headers=None):
        request = Request(self.origin + path, data=json.dumps(body).encode() if body is not None else None,
                          headers=headers or {})
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, response.headers, response.read().decode()
        except HTTPError as response:
            return response.code, response.headers, response.read().decode()

    def authority(self):
        return {'Origin': self.origin, 'Content-Type': 'application/json',
                'X-Watchlist-Token': self.server.token}

    def demo(self):
        store = Store(self.state / 'watch.db', self.watch)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                run_demo(self.watch, store, self.state)
        finally:
            store.close()

    def test_serves_dashboard_and_only_known_assets(self):
        status, headers, body = self.request('/')
        self.assertEqual(status, 200)
        self.assertIn('Personal Watchlist', body)
        self.assertIn("default-src 'self'", headers['Content-Security-Policy'])
        for asset in ['/app.js', '/styles.css']:
            self.assertEqual(self.request(asset)[0], 200)
        for path in ['/watch.db', '/watch.toml', '/../../.env', '/api/items/999']:
            self.assertEqual(self.request(path)[0], 404)

    def test_empty_state_shows_limits_and_never_successful_sources(self):
        status, _, body = self.request('/api/state')
        self.assertEqual(status, 200)
        data = json.loads(body)
        self.assertEqual(data['watch']['spending_ceiling_usd'], 0)
        self.assertEqual(data['counts']['finding'], 0)
        self.assertEqual(data['sources'][0]['health'], 'never')
        self.assertEqual(data['token'], self.server.token)

    def test_cross_origin_and_missing_token_cannot_change_anything(self):
        self.demo()
        body = {'item_id': 4, 'decision': 'finding', 'answer': 'Please include previews.'}
        for headers in [{}, {'Origin': 'https://untrusted.example', 'Content-Type': 'application/json'},
                        {'Origin': self.origin, 'Content-Type': 'application/json'},
                        {**self.authority(), 'Host': 'untrusted.example'}]:
            self.assertEqual(self.request('/api/answer', body, headers)[0], 403)
        self.assertEqual(json.loads(self.request('/api/state')[2])['counts']['pending'], 1)

    def test_answer_completes_same_item_and_brief_is_downloadable(self):
        self.demo()
        item = json.loads(self.request('/api/items/4')[2])
        self.assertIn('Python 3.15.0rc1', item['after_text'])
        status, _, body = self.request('/api/answer',
            {'item_id': 4, 'decision': 'finding', 'answer': 'Please include this preview.'}, self.authority())
        self.assertEqual(status, 200, body)
        item = json.loads(self.request('/api/items/4')[2])
        self.assertEqual(item['id'], 4)
        self.assertEqual(item['answer'], 'Please include this preview.')
        self.assertEqual(item['status'], 'finding')
        status, headers, brief = self.request('/brief.md')
        self.assertEqual(status, 200)
        self.assertIn('attachment', headers['Content-Disposition'])
        self.assertIn('SIMULATED', brief)
        self.assertIn('Please include this preview.', brief)

    def test_invalid_answers_and_simulated_live_checks_are_refused(self):
        self.demo()
        for body in [{'item_id': 4, 'decision': 'finding', 'answer': ''},
                     {'item_id': '4', 'decision': 'finding', 'answer': 'Yes'},
                     {'item_id': 4, 'decision': 'send', 'answer': 'Yes'}]:
            self.assertEqual(self.request('/api/answer', body, self.authority())[0], 400)
        self.assertEqual(self.request('/api/check', {}, self.authority())[0], 409)

    def test_live_check_uses_monitor_and_saves_the_brief(self):
        with patch('watchlist.web.Monitor.check', return_value=[{'url': self.watch.urls[0], 'status': 'not_due'}]) as check:
            status, _, body = self.request('/api/check', {}, self.authority())
        self.assertEqual(status, 200, body)
        check.assert_called_once()
        self.assertEqual(json.loads(body)['results'][0]['status'], 'not_due')
        self.assertTrue((self.state / 'brief.md').exists())


if __name__ == '__main__':
    unittest.main()

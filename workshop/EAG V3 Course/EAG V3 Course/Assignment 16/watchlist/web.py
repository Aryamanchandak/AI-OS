"""Serve the dashboard on loopback with same-origin, token-protected local mutations."""

import json
import secrets
import sqlite3
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from .dashboard import snapshot
from .monitor import Monitor
from .report import brief_text, save_brief
from .relevance import changed_lines
from .store import Store

ASSETS = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'),
          '/styles.css': ('styles.css', 'text/css')}


def create_server(watch, state, port=8765):
    state = Path(state)
    with_store = Store(state / 'watch.db', watch)
    with_store.close()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, body, content_type='application/json', download=False):
            raw = json.dumps(body).encode() if content_type == 'application/json' else body.encode()
            self.send_response(status)
            self.send_header('Content-Type', content_type + '; charset=utf-8')
            self.send_header('Content-Length', str(len(raw)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            if download:
                self.send_header('Content-Disposition', 'attachment; filename="watchlist-brief.md"')
            self.end_headers()
            self.wfile.write(raw)

        def allowed(self, mutate=False):
            origin = f'http://127.0.0.1:{self.server.server_port}'
            allowed = self.headers.get('Host') == origin.removeprefix('http://')
            if self.headers.get('Origin'):
                allowed = allowed and self.headers['Origin'] == origin
            if mutate:
                allowed = (allowed and self.headers.get('Origin') == origin and
                           secrets.compare_digest(self.headers.get('X-Watchlist-Token', ''), self.server.token))
            if not allowed:
                self.reply(403, {'error': 'Open this dashboard from its local address to use this action.'})
            return allowed

        def do_GET(self):
            if not self.allowed():
                return
            path = urlsplit(self.path).path
            if path in ASSETS:
                asset, mime = ASSETS[path]
                self.reply(200, (Path(__file__).parent / 'ui' / asset).read_text(), mime)
                return
            store = None
            try:
                store = Store(state / 'watch.db', watch)
                if path == '/api/state':
                    self.reply(200, {**snapshot(watch, store, state), 'token': self.server.token})
                elif path == '/brief.md':
                    self.reply(200, brief_text(state, Monitor(watch, store)), 'text/markdown', download=True)
                elif path.startswith('/api/items/') and path.removeprefix('/api/items/').isdigit():
                    item = store.decision(int(path.rsplit('/', 1)[1]))
                    if item:
                        removed, added = changed_lines(item['before_text'], item['after_text'])
                        self.reply(200, {**item, 'removed_text': removed, 'added_text': added})
                    else:
                        self.reply(404, {'error': 'Item not found.'})
                else:
                    self.reply(404, {'error': 'Page not found.'})
            except (OSError, sqlite3.Error, ValueError):
                self.reply(500, {'error': 'Could not read local watch data. Check the state folder and try again.'})
            finally:
                if store:
                    store.close()

        def do_POST(self):
            if not self.allowed(mutate=True):
                return
            store = None
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 1 <= size <= 8192 or self.headers.get('Content-Type') != 'application/json':
                    raise ValueError('Send a JSON request smaller than 8 KB.')
                body = json.loads(self.rfile.read(size))
                if not isinstance(body, dict):
                    raise ValueError('Request must contain an object.')
                store = Store(state / 'watch.db', watch)
                monitor = Monitor(watch, store)
                path = urlsplit(self.path).path
                if path == '/api/check':
                    if (state / '.simulated').exists():
                        self.reply(409, {'error': 'Demo evidence is simulated. Start a separate real watch to fetch live pages.'})
                        return
                    results = monitor.check()
                    save_brief(state, monitor)
                    self.reply(200, {'results': results})
                elif path == '/api/answer':
                    if (type(body.get('item_id')) is not int or not isinstance(body.get('answer'), str)
                            or len(body['answer']) > 2000 or body.get('decision') not in ('finding', 'ignored')):
                        raise ValueError('Choose a decision and enter an answer of up to 2,000 characters.')
                    store.answer(body['item_id'], body['decision'], body['answer'], datetime.now(timezone.utc))
                    save_brief(state, monitor)
                    self.reply(200, {'ok': True, 'item_id': body['item_id']})
                else:
                    self.reply(404, {'error': 'Action not found.'})
            except (ValueError, TypeError, KeyError, UnicodeError) as exc:
                self.reply(400, {'error': str(exc)})
            except RuntimeError as exc:
                self.reply(409, {'error': str(exc)})
            except (OSError, sqlite3.Error):
                self.reply(500, {'error': 'Could not save local watch data. No external action was taken.'})
            finally:
                if store:
                    store.close()

    server = HTTPServer(('127.0.0.1', port), Handler)
    server.token = secrets.token_urlsafe(32)
    return server

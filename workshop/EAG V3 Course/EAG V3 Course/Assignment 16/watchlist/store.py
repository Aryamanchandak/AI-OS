"""Persist captures, decisions and attempts in SQLite; serialize local writers with a file lock."""

import fcntl
import hashlib
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path


def timestamp(now):
    if now.tzinfo is None:
        raise ValueError('Observation times must include a timezone')
    return now.astimezone(timezone.utc).isoformat()


class Store:
    def __init__(self, path, watch):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.watch = watch
        self.db = sqlite3.connect(self.path, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS subscription (fingerprint TEXT PRIMARY KEY);
            CREATE TABLE IF NOT EXISTS sources (
                url TEXT PRIMARY KEY, head INTEGER, last_attempt TEXT, last_success TEXT
            );
            CREATE TABLE IF NOT EXISTS versions (
                id INTEGER PRIMARY KEY, url TEXT NOT NULL REFERENCES sources(url),
                hash TEXT NOT NULL, text TEXT NOT NULL, observed_at TEXT NOT NULL,
                UNIQUE(url, hash)
            );
            CREATE TABLE IF NOT EXISTS attempts (
                id INTEGER PRIMARY KEY, url TEXT NOT NULL REFERENCES sources(url),
                started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL,
                error TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY, version_id INTEGER NOT NULL UNIQUE REFERENCES versions(id),
                previous_id INTEGER NOT NULL REFERENCES versions(id),
                before_at TEXT NOT NULL, after_at TEXT NOT NULL,
                status TEXT NOT NULL, importance INTEGER NOT NULL,
                reason TEXT NOT NULL, interpretation TEXT NOT NULL, suggestion TEXT NOT NULL,
                question TEXT NOT NULL, answer TEXT NOT NULL DEFAULT '', answered_at TEXT
            );
            CREATE TABLE IF NOT EXISTS facts (key TEXT PRIMARY KEY, version_id INTEGER REFERENCES versions(id));
        ''')
        existing = self.db.execute('SELECT fingerprint FROM subscription').fetchone()
        if existing and existing[0] != watch.fingerprint:
            self.db.close()
            raise ValueError('Subscription changed. Use a separate --state directory to establish a new baseline.')
        with self.db:
            self.db.execute('INSERT OR IGNORE INTO subscription VALUES (?)', (watch.fingerprint,))
            self.db.executemany('INSERT OR IGNORE INTO sources(url) VALUES (?)', [(url,) for url in watch.urls])

    def close(self):
        self.db.close()

    @contextmanager
    def exclusive(self):
        with self.path.with_suffix('.lock').open('a') as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError('Another watchlist writer is running; try after it finishes') from exc
            try:
                yield
            finally:
                fcntl.flock(handle, fcntl.LOCK_UN)

    def recover_interrupted(self, now):
        with self.db:
            self.db.execute("UPDATE attempts SET status='failed', finished_at=?, error='Process interrupted; outcome unknown. Attempt still counts toward limits.' WHERE status='running'",
                            (timestamp(now),))

    def reserve(self, url, now):
        """Commit the attempt before fetching so crashes cannot refund the ceiling."""
        at = timestamp(now)
        with self.db:
            row = self.db.execute('SELECT * FROM sources WHERE url=?', (url,)).fetchone()
            if row is None:
                raise ValueError('URL was not selected in the subscription')
            if row['last_attempt'] and datetime.fromisoformat(row['last_attempt']) + timedelta(hours=self.watch.interval_hours) > now:
                return {'url': url, 'status': 'not_due'}
            used = self.db.execute('SELECT COUNT(*) FROM attempts WHERE started_at >= ? AND started_at < ?',
                                   (at[:10], (now.astimezone(timezone.utc) + timedelta(days=1)).date().isoformat())).fetchone()[0]
            if used >= self.watch.max_checks_per_day:
                return {'url': url, 'status': 'limit'}
            attempt = self.db.execute("INSERT INTO attempts(url, started_at, status) VALUES (?, ?, 'running')", (url, at))
            self.db.execute('UPDATE sources SET last_attempt=? WHERE url=?', (at, url))
            return {'url': url, 'status': 'running', 'attempt_id': attempt.lastrowid}

    def previous(self, url):
        row = self.db.execute('SELECT v.*, s.last_success FROM sources s JOIN versions v ON s.head=v.id WHERE s.url=?', (url,)).fetchone()
        return dict(row) if row else None

    def known_facts(self):
        return {row[0] for row in self.db.execute('SELECT key FROM facts')}

    def find_version(self, url, text):
        digest = hashlib.sha256(text.encode()).hexdigest()
        row = self.db.execute('SELECT * FROM versions WHERE url=? AND hash=?', (url, digest)).fetchone()
        return dict(row) if row else None

    def complete(self, attempt_id, url, text, assessment, fact_keys, now):
        at = timestamp(now)
        previous = self.previous(url)
        existing = self.find_version(url, text)
        with self.db:
            if existing:
                version_id = existing['id']
                status = 'unchanged' if previous and previous['id'] == version_id else 'seen'
            else:
                result = self.db.execute('INSERT INTO versions(url, hash, text, observed_at) VALUES (?, ?, ?, ?)',
                                         (url, hashlib.sha256(text.encode()).hexdigest(), text, at))
                version_id = result.lastrowid
                status = assessment.status if assessment else 'baseline'
                if assessment:
                    self.db.execute('''INSERT INTO decisions
                        (version_id, previous_id, before_at, after_at, status, importance, reason,
                         interpretation, suggestion, question) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                        (version_id, previous['id'], previous['last_success'], at, status,
                         assessment.importance, assessment.reason, assessment.interpretation,
                         assessment.suggestion, assessment.question))
                self.db.executemany('INSERT OR IGNORE INTO facts VALUES (?, ?)', [(key, version_id) for key in fact_keys])
            self.db.execute('UPDATE sources SET head=?, last_success=? WHERE url=?', (version_id, at, url))
            self.db.execute('UPDATE attempts SET status=?, finished_at=? WHERE id=?', (status, at, attempt_id))
        return status

    def fail(self, attempt_id, error, now):
        with self.db:
            self.db.execute("UPDATE attempts SET status='failed', error=?, finished_at=? WHERE id=?", (error, timestamp(now), attempt_id))

    def answer(self, item_id, decision, answer, now):
        if decision not in ('finding', 'ignored') or not answer.strip():
            raise ValueError('Choose finding or ignored and provide a non-empty answer')
        with self.exclusive(), self.db:
            result = self.db.execute("UPDATE decisions SET status=?, answer=?, answered_at=? WHERE id=? AND status='pending'",
                                     (decision, answer.strip(), timestamp(now), item_id))
            if result.rowcount != 1:
                raise ValueError('No pending question with that ID; answered items are not overwritten')

    def decisions(self):
        return [dict(row) for row in self.db.execute('''SELECT d.*, v.url, old.text AS before_text,
            v.text AS after_text FROM decisions d JOIN versions v ON d.version_id=v.id
            JOIN versions old ON d.previous_id=old.id ORDER BY d.importance DESC, d.id''')]

    def attempts(self):
        return [dict(row) for row in self.db.execute('SELECT * FROM attempts ORDER BY id')]

    def versions(self):
        return [dict(row) for row in self.db.execute('SELECT * FROM versions ORDER BY id')]

    def sources(self):
        return [dict(row) for row in self.db.execute('SELECT * FROM sources ORDER BY url')]

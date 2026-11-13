"""Run one due check through capture, relevance assessment, persistence and a local brief."""

from datetime import datetime, timezone

from .fetch import FetchError, fetch_page
from .relevance import assess, facts
from .report import render_report


class Monitor:
    def __init__(self, watch, store, fetcher=fetch_page, clock=None):
        self.watch = watch
        self.store = store
        self.fetcher = fetcher
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.assessor = assess

    def check(self):
        results = []
        with self.store.exclusive():
            self.store.recover_interrupted(self.clock())
            for url in self.watch.urls:
                result = self.store.reserve(url, self.clock())
                if result['status'] != 'running':
                    results.append(result)
                    continue
                stage = 'fetch'
                try:
                    text = self.fetcher(url, self.watch.max_bytes)
                    if not isinstance(text, str) or not text.strip():
                        raise FetchError('Empty source content')
                    previous = self.store.previous(url)
                    stage = 'assessment'
                    assessment = None
                    if previous and not self.store.find_version(url, text):
                        assessment = self.assessor(previous['text'], text, self.watch.rules, self.store.known_facts())
                    result['status'] = self.store.complete(result['attempt_id'], url, text, assessment,
                                                           facts(text, self.watch.rules), self.clock())
                except Exception as exc:
                    detail = str(exc) if isinstance(exc, FetchError) else type(exc).__name__
                    result['status'] = 'failed'
                    self.store.fail(result['attempt_id'], f'{stage}: {detail}', self.clock())
                results.append(result)
        return results

    def report(self):
        return render_report(self.watch, self.store, self.clock())

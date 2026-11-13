"""Reproduce the acceptance journey with explicitly synthetic page changes."""

from datetime import datetime, timedelta, timezone

from .fetch import FetchError
from .monitor import Monitor


def run_demo(watch, store, state):
    if store.attempts():
        raise ValueError('Demo requires an empty state directory; existing evidence is never overwritten')
    if len(watch.urls) != 2 or {rule.name for rule in watch.rules} != {'stable', 'preview'}:
        raise ValueError('Demo requires the supplied two-page Python-release subscription')
    state.joinpath('.simulated').write_text('Synthetic Python release-watch acceptance journey.\n')
    now = datetime.now(timezone.utc) - timedelta(days=5)
    pages = {watch.urls[0]: 'Python 3.14.0', watch.urls[1]: 'Release news\nDonate'}

    def fetch(url, limit):
        if pages[url] is None:
            raise FetchError('Capture failed (simulated timeout)')
        return pages[url]

    monitor = Monitor(watch, store, fetch, lambda: now)

    def show(label):
        print(label + ': ' + ', '.join(item['status'] for item in monitor.check()))

    show('Initial context')
    now += timedelta(days=1)
    pages[watch.urls[0]] += '\nPython 3.14.1'
    show('Known relevant change')
    now += timedelta(days=1)
    pages[watch.urls[1]] = 'Announcing Python 3.14.1 again\nDonate'
    show('Repeated announcement')
    now += timedelta(days=1)
    pages[watch.urls[1]] = 'Announcing Python 3.14.1 again\nDonate to the foundation'
    show('Unrelated edit')
    now += timedelta(days=1)
    pages[watch.urls[0]] += '\nPython 3.15.0rc1'
    show('Ambiguous preview')
    now += timedelta(days=1)
    pages[watch.urls[1]] = None
    show('Unchanged content and explicit failure')
    for item in store.decisions():
        if item['status'] == 'pending':
            print(f'Pending item {item["id"]}: {item["question"]}')

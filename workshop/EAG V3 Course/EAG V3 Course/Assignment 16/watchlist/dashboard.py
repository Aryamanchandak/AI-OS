"""Build the dashboard view of local decisions, selected sources and monitoring health."""

from dataclasses import asdict
from datetime import datetime, timedelta, timezone

from .store import timestamp


def snapshot(watch, store, state, now=None):
    now = now or datetime.now(timezone.utc)
    attempts = store.attempts()
    sources = []
    for source in store.sources():
        history = [attempt for attempt in attempts if attempt['url'] == source['url']]
        latest = history[-1] if history else None
        due = (datetime.fromisoformat(source['last_attempt']) + timedelta(hours=watch.interval_hours)
               if source['last_attempt'] else now)
        health = 'never'
        if source['last_success']:
            health = 'overdue' if datetime.fromisoformat(source['last_success']) + timedelta(hours=watch.interval_hours) <= now else 'current'
        if latest and latest['status'] in ('failed', 'running'):
            health = latest['status']
        sources.append({**source, 'health': health, 'next_check': timestamp(due),
                        'latest_status': latest['status'] if latest else 'none'})
    counts = {'finding': 0, 'pending': 0, 'ignored': 0, **store.decision_counts()}
    failures = [attempt for attempt in attempts if attempt['status'] in ('failed', 'running')]
    counts['failed'] = len(failures)
    return {'watch': asdict(watch), 'sources': sources, 'counts': counts,
            'items': store.summaries(), 'failures': failures[-100:][::-1],
            'attempts_today': sum(item['started_at'][:10] == timestamp(now)[:10] for item in attempts),
            'generated_at': timestamp(now), 'simulated': (state / '.simulated').exists()}

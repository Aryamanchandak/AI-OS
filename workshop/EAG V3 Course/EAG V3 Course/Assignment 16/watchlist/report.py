"""Render an evidence-backed local Markdown brief with monitoring status."""

import html
import re
from datetime import datetime, timedelta, timezone

from .relevance import changed_lines
from .store import timestamp


def literal(text):
    """Quote untrusted evidence as text, including embedded Markdown and HTML."""
    longest = max((len(part) for part in re.findall(r'`+', text)), default=0)
    fence = '`' * max(3, longest + 1)
    return f'{fence}text\n{text}\n{fence}'


def render_report(watch, store, now):
    attempts = store.attempts()
    decisions = store.decisions()
    lines = [f'# Watch brief: {html.escape(watch.name)}', '', literal(watch.question), '',
             f'Generated: {timestamp(now)}', '',
             'Assessment: explicit local rules plus human clarification. Matches are observed statements, not verified truth.',
             'Spending: $0; no model calls. Suggestions stay local.', '',
             '## Monitoring status', '',
             f'Checking interval: {watch.interval_hours:g} hours. Daily page-attempt ceiling: {watch.max_checks_per_day} (UTC).',
             f'Page size ceiling: {watch.max_bytes} bytes. No background scheduler is installed.', '']
    today = now.astimezone(timezone.utc).date().isoformat()
    used = sum(item['started_at'][:10] == today for item in attempts)
    lines += [f'Attempts today: {used}/{watch.max_checks_per_day}.', '']
    for source in store.sources():
        history = [item for item in attempts if item['url'] == source['url']]
        latest = history[-1] if history else None
        due = (datetime.fromisoformat(source['last_attempt']) + timedelta(hours=watch.interval_hours)
               if source['last_attempt'] else now)
        if not source['last_success']:
            health = 'not yet successful'
        elif latest and latest['status'] in ('failed', 'running'):
            health = 'FAILED or interrupted' if latest['status'] == 'failed' else 'running or interrupted'
        elif datetime.fromisoformat(source['last_success']) + timedelta(hours=watch.interval_hours) <= now:
            health = 'OVERDUE'
        else:
            health = 'current'
        lines += [f'- Source: {source["url"]}',
                  f'  Status: {health}; last successful capture: {source["last_success"] or "never"}; '
                  f'last attempt: {source["last_attempt"] or "never"}; latest result: {latest["status"] if latest else "none"}; '
                  f'next eligible check: {timestamp(due)}.', '']
    for heading, status in [('Findings', 'finding'), ('Ignored changes', 'ignored'), ('Pending questions', 'pending')]:
        lines += [f'## {heading}', '']
        items = [item for item in decisions if item['status'] == status]
        if not items:
            lines += ['None.', '']
        for item in items:
            removed, added = changed_lines(item['before_text'], item['after_text'])
            lines += [f'### Item {item["id"]} · importance {item["importance"]}/3', '',
                      f'Source: {item["url"]}', '', 'Decision reason:', literal(item['reason']), '',
                      f'Observed facts — previous capture {item["before_at"]}; current capture {item["after_at"]}.',
                      'Removed lines:', literal(removed or '(none)'), 'Added lines:', literal(added or '(none)'), '',
                      f'Full evidence: watch.db versions {item["previous_id"]} → {item["version_id"]}.', '',
                      'Interpretation:', literal(item['interpretation'] or 'No interpretation added.'), '',
                      'Suggested local follow-up:', literal(item['suggestion'] or 'None.'), '']
            if item['question']:
                lines += ['Question:', literal(item['question']), '']
            if item['answer']:
                lines += [f'Your answer ({item["answered_at"]}):', literal(item['answer']), '']
    lines += ['## Failures', '']
    failures = [item for item in attempts if item['status'] in ('failed', 'running')]
    if not failures:
        lines += ['None.', '']
    for item in failures:
        lines += [f'- Attempt {item["id"]}: {item["url"]} at {item["started_at"]}',
                  literal(item['error'] or 'Attempt running or interrupted; next check will record recovery.'), '']
    return '\n'.join(lines).rstrip() + '\n'

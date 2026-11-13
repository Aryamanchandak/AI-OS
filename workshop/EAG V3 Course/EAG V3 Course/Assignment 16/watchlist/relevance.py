"""Assess changed statements using explicit rules; leave ambiguous intent to the user."""

import difflib
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Assessment:
    status: str
    importance: int
    reason: str
    interpretation: str = ''
    suggestion: str = ''
    question: str = ''


def facts(text, rules):
    """A fact key identifies a matched statement, not its truth or a permission."""
    found = {}
    for rule in rules:
        for match in re.finditer(rule.pattern, text, re.IGNORECASE):
            key = rule.name + ':' + ' '.join(match.group().casefold().split())
            found[key] = rule
    return found


def changed_lines(before, after):
    removed, added = [], []
    for line in difflib.ndiff(before.splitlines(), after.splitlines()):
        if line.startswith('- '):
            removed.append(line[2:])
        elif line.startswith('+ '):
            added.append(line[2:])
    return '\n'.join(removed), '\n'.join(added)


def assess(before, after, rules, known):
    current = facts(after, rules)
    previous = facts(before, rules)
    new = {key: rule for key, rule in current.items() if key not in known}
    if new:
        ranked = sorted(new.items(), key=lambda pair: (-pair[1].importance, pair[0]))
        questions = list(dict.fromkeys(rule.question for rule in new.values() if rule.question))
        return Assessment(
            'pending' if questions else 'finding', ranked[0][1].importance,
            'New watched statement(s): ' + ', '.join(key for key, _ in ranked),
            '\n'.join(dict.fromkeys(rule.interpretation for _, rule in ranked)),
            '\n'.join(dict.fromkeys(rule.suggestion for _, rule in ranked if rule.suggestion)),
            '\n'.join(questions),
        )
    missing = set(previous) - set(current)
    if missing:
        return Assessment('pending', max(previous[key].importance for key in missing),
                          'A previously watched statement disappeared; removal is not proof of reversal.',
                          question='A watched statement was removed. Does this require follow-up?')
    _, added = changed_lines(before, after)
    if facts(added, rules):
        return Assessment('ignored', 0, 'Repeated announcement: all matched statements were already observed.')
    return Assessment('ignored', 0, 'No new statement matched the selected relevance rules; unrelated or weak edit.')

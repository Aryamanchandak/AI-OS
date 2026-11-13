"""Load the human-owned subscription and explicit relevance rules."""

import csv
import hashlib
import json
import math
import re
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path

from .fetch import validate_url


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: str
    importance: int
    interpretation: str
    suggestion: str
    question: str

    def __post_init__(self):
        if not self.name.strip() or not self.pattern or not 1 <= self.importance <= 3:
            raise ValueError('Rules need a name, a pattern, and importance 1–3')
        if re.compile(self.pattern, re.IGNORECASE).match(''):
            raise ValueError('A rule must not match empty text')


@dataclass(frozen=True)
class Watch:
    name: str
    question: str
    urls: tuple[str, ...]
    interval_hours: float
    max_checks_per_day: int
    max_bytes: int
    spending_ceiling_usd: float
    rules: tuple[Rule, ...]

    def __post_init__(self):
        if not self.name.strip() or not self.question.strip() or not self.urls or not self.rules:
            raise ValueError('A watch needs a name, question, selected URLs and rules')
        if len(set(self.urls)) != len(self.urls) or len({r.name for r in self.rules}) != len(self.rules):
            raise ValueError('URLs and rule names must be unique')
        if not math.isfinite(self.interval_hours) or self.interval_hours <= 0:
            raise ValueError('Checking interval must be positive and finite')
        if type(self.max_checks_per_day) is not int or self.max_checks_per_day <= 0:
            raise ValueError('Daily page-attempt ceiling must be a positive integer')
        if type(self.max_bytes) is not int or not 1 <= self.max_bytes <= 10_000_000:
            raise ValueError('Page byte ceiling must be between 1 and 10,000,000')
        if self.spending_ceiling_usd != 0:
            raise ValueError('This version supports zero spend only; paid model runs are not enabled')
        for url in self.urls:
            validate_url(url)

    @property
    def fingerprint(self):
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()


def load_watch(path):
    path = Path(path)
    with path.open('rb') as handle:
        settings = tomllib.load(handle)
    rules = []
    with (path.parent / settings.pop('rules_file')).open(newline='', encoding='utf-8') as handle:
        for row in csv.DictReader(handle):
            row['importance'] = int(row['importance'])
            rules.append(Rule(**row))
    settings['urls'] = tuple(settings['urls'])
    return Watch(**settings, rules=tuple(rules))

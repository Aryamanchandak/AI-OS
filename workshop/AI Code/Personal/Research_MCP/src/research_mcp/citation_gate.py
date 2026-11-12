"""Deterministic citation gate (section 10). No LLM. A run cannot complete if this fails.

Checks:
  1. Every [Sn] tag references a source in the run's source list.
  2. Every direct quote is a verbatim substring of Sn's stored raw_excerpt
     (whitespace/quote-normalised).
  3. Factual-looking sentences with no [Sn] anchor are flagged (not hard-fail, but reported).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .contracts import LogicalSource


@dataclass
class CitationGateResult:
    passed: bool
    invalid_tags: list[str] = field(default_factory=list)
    failed_quotes: list[str] = field(default_factory=list)
    unanchored_sentences: list[str] = field(default_factory=list)


_SENTENCE_RE = re.compile(r"[^.!?]*[.!?]")
_TAG_RE = re.compile(r"\[S(\d+)\]")
_QUOTE_WITH_TAG_RE = re.compile(r'"([^"]{10,}?)"\s*\[S(\d+)\]')
_FACTUAL_STARTERS = re.compile(
    r"^\s*(The |In |Research (shows|demonstrates|suggests|indicates)|Studies |According |Evidence |Data )",
    re.IGNORECASE,
)

# All curly/smart quote variants as their Unicode code points
_QUOTE_CHARS = "".join(chr(c) for c in (0x2018, 0x2019, 0x201C, 0x201D, 0x0027, 0x0022))
_QUOTE_RE = re.compile("[" + re.escape(_QUOTE_CHARS) + "]")


def _normalise(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = _QUOTE_RE.sub("", text)
    text = re.sub(r"\s+", " ", text)
    return text.lower().strip()


def verify_citations(essay: str, sources: list[LogicalSource]) -> CitationGateResult:
    label_to_source: dict[int, LogicalSource] = {i + 1: s for i, s in enumerate(sources)}
    valid_indices = set(label_to_source.keys())

    invalid_tags: list[str] = []
    failed_quotes: list[str] = []
    unanchored: list[str] = []

    # 1. Validate every [Sn] tag
    for m in _TAG_RE.finditer(essay):
        n = int(m.group(1))
        if n not in valid_indices:
            invalid_tags.append(m.group(0))

    # 2. Check direct quotes
    for m in _QUOTE_WITH_TAG_RE.finditer(essay):
        quote_text = m.group(1)
        n = int(m.group(2))
        if n not in label_to_source:
            failed_quotes.append(quote_text)
            continue
        excerpt = label_to_source[n].raw_excerpt
        if _normalise(quote_text) not in _normalise(excerpt):
            failed_quotes.append(quote_text)

    # 3. Flag factual-looking sentences with no tag
    for sent in _SENTENCE_RE.findall(essay):
        if _FACTUAL_STARTERS.match(sent) and not _TAG_RE.search(sent):
            unanchored.append(sent.strip())

    passed = not invalid_tags and not failed_quotes
    return CitationGateResult(
        passed=passed,
        invalid_tags=invalid_tags,
        failed_quotes=failed_quotes,
        unanchored_sentences=unanchored,
    )

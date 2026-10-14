"""Protected-span detection: regions cleanup must never propose or apply a change in.

Covers YAML frontmatter, fenced and inline code, Markdown link/image targets,
autolinks, URLs, email addresses, and path-like text (component_8.md section
6.2). Only the *target* of a Markdown link/image is protected, not its
visible label text -- the label is ordinary prose and stays reviewable.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

_FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
_FENCED_CODE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`\n]+`")
_MD_LINK_TARGET = re.compile(r"!?\[[^\]]*\]\(([^)]*)\)")
_AUTOLINK = re.compile(r"<(https?://[^>\s]+|[^@\s<>]+@[^@\s<>]+)>")
_URL = re.compile(r"\bhttps?://\S+")
_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_TOKEN = re.compile(r"\S+")
_DRIVE_LETTER = re.compile(r"^[A-Za-z]:\\")


def _looks_like_path(token: str) -> bool:
    """A path-like token while preserving slash-ending shorthand.

    A single bare slash is left alone on purpose: punctuation-bearing
    shorthand like ``w/`` legitimately ends in one slash and must stay
    matchable (component_8.md section 6.2), so "path-like" here means an
    conventional path with content on both sides of its slash (``docs/file``),
    a multi-segment path, or a Windows drive path.
    """

    # Markdown link/image targets are handled precisely by
    # ``_MD_LINK_TARGET``; treating the whole token as a path would also hide
    # its visible label.
    if "](" in token:
        return False
    if _DRIVE_LETTER.match(token):
        return True
    if token.startswith("./") or token.startswith("../"):
        return True
    if token.count("/") >= 2:
        return True
    if token.count("/") == 1:
        left, right = token.split("/", 1)
        return bool(left and right)
    return False


@dataclass(frozen=True)
class ProtectedSpan:
    start: int
    end: int


def find_protected_spans(text: str) -> list[ProtectedSpan]:
    spans: list[ProtectedSpan] = []
    for pattern in (_FRONTMATTER, _FENCED_CODE, _INLINE_CODE):
        for match in pattern.finditer(text):
            spans.append(ProtectedSpan(match.start(), match.end()))
    for match in _MD_LINK_TARGET.finditer(text):
        spans.append(ProtectedSpan(match.start(1), match.end(1)))
    for pattern in (_AUTOLINK, _URL, _EMAIL):
        for match in pattern.finditer(text):
            spans.append(ProtectedSpan(match.start(), match.end()))
    for match in _TOKEN.finditer(text):
        if _looks_like_path(match.group(0)):
            spans.append(ProtectedSpan(match.start(), match.end()))
    return _merge(spans)


def _merge(spans: list[ProtectedSpan]) -> list[ProtectedSpan]:
    if not spans:
        return []
    ordered = sorted(spans, key=lambda span: span.start)
    merged = [ordered[0]]
    for span in ordered[1:]:
        last = merged[-1]
        if span.start <= last.end:
            merged[-1] = ProtectedSpan(last.start, max(last.end, span.end))
        else:
            merged.append(span)
    return merged


def intersects(spans: list[ProtectedSpan], start: int, end: int) -> bool:
    return any(span.start < end and start < span.end for span in spans)

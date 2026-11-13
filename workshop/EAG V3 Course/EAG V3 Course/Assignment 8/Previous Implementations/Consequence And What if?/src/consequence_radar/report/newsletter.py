from __future__ import annotations

import re

from ..models import NewsletterReport, ReportContext
from ..providers.model import ModelClient

# Source IDs are minted as ``S`` followed by digits (providers/search.py), so a
# citation marker is exactly that shape.  The previous pattern accepted any
# bracketed word beginning with S, which made ordinary prose about ``[SEBI]`` or
# the ``[Sensex]`` read as an invented citation and failed a correct report.
# Case is matched but normalised away, so a lower-case ``[s2]`` is still checked
# against the real source IDs rather than silently passing as prose.
MARKER = re.compile(r"\[[Ss]\d+\]")
PROHIBITED = [re.compile(p, re.I) for p in (r"\b(?:buy|sell|hold)\s+(?:the\s+)?(?:stock|shares?)\b", r"\b(?:investors?|readers?)\s+should\s+(?:buy|sell|hold|purchase)\b", r"\bwe recommend\b", r"\bprice target\b")]


def word_count(markdown: str) -> int:
    return len(re.findall(r"\b[\w’'-]+\b", markdown))


def _collapse(value: str) -> str:
    """Line wrapping is not a difference in an assumption statement."""
    return re.sub(r"\s+", " ", value).strip()


def validate_report(report: NewsletterReport, context: ReportContext, min_words: int, max_words: int) -> list[str]:
    errors = []
    count = word_count(report.article_markdown)
    if not min_words <= count <= max_words: errors.append(f"article word count {count} is outside {min_words}-{max_words}")
    source_ids = {s.id.upper() for s in context.sources}
    markers = {m[1:-1].upper() for m in MARKER.findall(report.article_markdown)}
    if not markers <= source_ids: errors.append(f"unknown source markers: {sorted(markers - source_ids)}")
    if not {s.upper() for s in report.source_ids_used} <= source_ids: errors.append("source_ids_used contains unknown sources")
    assumptions = {_collapse(a.statement) for a in context.assumptions}
    if not {_collapse(s) for s in report.key_assumptions} <= assumptions: errors.append("key_assumptions contains a statement absent from the final graph")
    for field in (report.why_this_matters, report.central_case_summary):
        if len(field.split()) < 8: errors.append("required narrative section is not substantive")
    if not report.what_changes_the_view: errors.append("what_changes_the_view is empty")
    if any(pattern.search(report.article_markdown) for pattern in PROHIBITED): errors.append("prohibited investment-instruction language detected")
    return errors


def write_report(run_id: str, context: ReportContext, model: ModelClient, min_words: int, max_words: int) -> tuple[NewsletterReport, list[str]]:
    report = model.generate(run_id=run_id, stage="newsletter", prompt_name="report/newsletter_writer.md", prompt_data=context.model_dump_json(), schema=NewsletterReport, model_tier="report")
    return report, validate_report(report, context, min_words, max_words)


def export_markdown(report: NewsletterReport) -> str:
    return f"# {report.headline}\n\n*{report.dek}*\n\n{report.article_markdown}\n"

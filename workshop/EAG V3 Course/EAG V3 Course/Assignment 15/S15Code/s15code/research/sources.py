"""Deterministic local passage selection with original line provenance."""
import re

from .models import Document

_WORDS = re.compile(r"[a-z0-9]+")
_STOP = set("the a an and or of to in for is it what when how does with on per".split())


def retrieve(question: str, documents: list[Document], limit: int = 14) -> list[dict]:
    terms = set(_WORDS.findall(question.lower())) - _STOP
    candidates = []
    for index, doc in enumerate(documents):
        lines = doc.text.splitlines()
        start = 0
        while start < len(lines):
            end, length = start, 0
            while end < len(lines) and (length + len(lines[end]) <= 1400 or end == start):
                length += len(lines[end]) + 1
                end += 1
            text = "\n".join(lines[start:end])
            if text.strip():
                words = set(_WORDS.findall(text.lower()))
                score = len(terms & words) / max(1, len(terms))
                candidates.append((score, {"id": f"D{index + 1}:L{start + 1}-{end}",
                    "document_index": index, "document": doc.name,
                    "line_start": start + 1, "line_end": end, "text": text}))
            start = end
    # Stable ties follow original document order. No network or model is used.
    candidates.sort(key=lambda item: -item[0])
    return [item[1] for item in candidates[:limit]]


def verify_citations(value, evidence: list[dict]) -> None:
    passages = {item["id"]: item["text"] for item in evidence}

    def walk(item):
        if isinstance(item, dict):
            if "evidence_id" in item:
                source = passages.get(item["evidence_id"])
                if source is None or item["quote"] not in source:
                    raise ValueError("citation quote does not occur verbatim in the selected source passage")
            for child in item.values():
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)

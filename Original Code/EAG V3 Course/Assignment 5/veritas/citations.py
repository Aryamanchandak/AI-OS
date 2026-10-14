"""Deterministic citation integrity.

`verify` is another LLM call and inherits LLM failure modes — run 2 in the
README cites `PMID:4059230` in its prose rationale while the retrieved set
contains `PMID:9059230`, and check C1 passed anyway. Set membership is not a
judgement call, so it is asserted in code here, the same way `fetch` is code
rather than a prompt.

The malformed id lived in `verdict_rationale`, not in a structured
`source_id` field, so this scans **every** string in the payload rather than
walking known keys.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable

# Only the id schemes sources.py actually mints. Case-insensitive: a model that
# writes `pmid:9999999` must not slip past the scanner unextracted — an id that
# is never extracted is never compared, and so is never flagged.
_CITE = re.compile(r"\b(PMID|arXiv)\s*:\s*([0-9A-Za-z][0-9A-Za-z./_-]*)", re.I)

# arXiv ids arrive from the API version-suffixed (`arXiv:2206.14521v2`) but get
# cited both ways. Since a failed check now costs a whole extra round, that
# cosmetic difference must not read as a hallucinated citation.
_ARXIV_VERSION = re.compile(r"v\d+$", re.I)


def _norm(raw: str) -> str:
    """`ARXIV: 2206.14521v2` and `arXiv:2206.14521` are the same citation."""
    scheme, _, rest = raw.partition(":")
    scheme, rest = scheme.strip().lower(), rest.strip().rstrip(".,;:")
    if scheme == "arxiv":
        rest = _ARXIV_VERSION.sub("", rest)
    return f"{scheme}:{rest}"


def cited_ids(payload: Any) -> set[str]:
    """Every source id mentioned anywhere in `payload` — prose included."""
    blob = json.dumps(payload, default=str)
    return {_norm(f"{scheme}:{body}") for scheme, body in _CITE.findall(blob)}


def citation_violations(payload: Any, fetched: Iterable[str]) -> list[str]:
    """Ids the model cited that were never retrieved. Empty list means clean."""
    known = {_norm(str(i)) for i in fetched}
    return sorted(cited_ids(payload) - known)


def integrity_check(check_id: str, name: str, violations: list[str]) -> dict[str, Any]:
    """A check row shaped like `verify`'s, so the CLI and UI render it unchanged."""
    return {
        "id": check_id,
        "name": name,
        "result": "pass" if not violations else "fail",
        "reason": (
            "every cited source id is in the retrieved set"
            if not violations
            else "cited but never retrieved: " + ", ".join(violations)
        ),
        "deterministic": True,
    }

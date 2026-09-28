"""Extraction prompts for the gateway-backed extractor.

Written against the rich concept/claim/relation shape (`SemanticExtraction` in
`ingestion.models`). IP's old `kg/prompts.py` (flat triplets only) was kept only
as a phrasing reference during design, not reused here.

Two prompts, one contract:

- `build_extraction_prompt` — one passage, one payload.
- `build_batch_extraction_prompt` — several highlights, one payload each,
  tagged by `batch_item_id` so the caller can verify the mapping back in code.

Both share the same extraction rules; the batched one adds each highlight's
surrounding context, which exists purely to disambiguate pronouns and
references. Context is never quotable: evidence quotes are checked against the
highlight alone, so a quote lifted from the context is discarded and the
proposal ends up in review.
"""

from __future__ import annotations

from typing import Iterable, Protocol

from gateway.ingestion.parsing import CONTEXT_ELISION


class _HighlightLike(Protocol):
    batch_item_id: str
    highlight_text: str
    context_text: str | None


EXTRACTION_SYSTEM_PROMPT = (
    "You are an information-extraction engine for a personal knowledge graph "
    "and vector index. You read one normalized passage and extract "
    "concepts, claims, and relations that are clearly stated or strongly "
    "implied in the text. You never invent facts, never paraphrase evidence, "
    "and never report a confidence score higher than your actual certainty. "
    "A clear declarative sentence must produce at least a claim, and an "
    "explicit subject-predicate-object statement must also produce a relation. "
    "Every reported quote must be an exact, verbatim substring of the "
    "passage text you were given. Respond with raw JSON only — no markdown "
    "code fences, no backticks, and no prose before or after the JSON object."
)

# The extraction contract itself, shared verbatim by both prompts so the two
# can never drift apart on what a concept, claim, relation, or quote is.
EXTRACTION_RULES = """\
Return, for each passage:
- **concepts**: distinct entities or ideas discussed in the text. Each needs
  a canonical `label`, optional `aliases`, a `confidence` (0.0-1.0), and one
  or more `evidence_quotes` — exact verbatim substrings of the passage that
  support it. `aliases` are evidence-bearing identity assertions, not helpful
  synonyms: include an alias ONLY when the passage explicitly states that
  two names refer to the same concept. Otherwise return an empty alias list.
- **claims**: factual statements made about one or more concepts. Each needs
  `text` (the claim), the `concept_labels` it relates to, a `confidence`, and
  `evidence_quotes` (verbatim, as above).
- **relations**: subject-predicate-object triples between concepts. Use
  short, canonical noun phrases for `subject`/`object` and an
  UPPER_SNAKE_CASE `predicate` (e.g. CAUSES, REQUIRES, PART_OF,
  CONTRASTS_WITH, DEFINED_BY, RELATES_TO). Each needs a `confidence` and
  `evidence_quotes`, plus a `hierarchical` flag (default false) — set it to
  true ONLY when the passage explicitly states that this specific relation
  is a strict, non-cyclic hierarchy (e.g. "X is a prerequisite of Y", "X is a
  component of Y") where the reverse direction would be a contradiction, not
  just a plausible converse. Never set it based on the predicate word alone —
  the same predicate can be hierarchical in one passage and not in another.
  When unsure, leave it false.
- **field_tags**: short topical tags for the passage.
- **source_quality_signals**: short notes on anything that should make a
  human double-check this extraction (ambiguous wording, contradictions,
  low-quality OCR, corrupted or incomplete sentences, etc.) — empty list if
  none. Report an objective defect in the supplied source, not merely that the
  passage is short, narrowly scoped, or uses a qualification which the
  extracted claim can preserve verbatim.
- **overall_confidence**: your overall confidence (0.0-1.0) in this
  extraction as a whole.

Rules:
- Every `evidence_quotes` entry MUST be copied exactly, character-for-
  character, from the passage text — no paraphrasing, no ellipses, no
  added punctuation. A quote that doesn't match exactly will be discarded.
- Treat every clear declarative factual sentence as a candidate claim.
- Preserve qualifications such as "usually", "can", or "under these
  conditions" in the claim text. A faithfully preserved qualification is not
  by itself a source-quality defect.
- When the text explicitly says that X is, contains, requires, causes,
  measures, reduces, contrasts with, or is part of Y, emit the corresponding
  relation as well as any supported claim.
- Return empty concepts/claims/relations only when the passage truly contains
  no factual assertion, definition, comparison, or relationship. An empty
  extraction from a passage with declarative content is incomplete and must
  not receive `overall_confidence` above 0.2.
- Extract only what is clearly stated or strongly implied — do not
  speculate.

Example: for "Duration measures interest-rate sensitivity." extract the
concepts "Duration" and "Interest-rate sensitivity", the claim stated by that
sentence, and a `MEASURES` relation. Use the exact sentence as evidence.\
"""

EXTRACTION_PROMPT_TEMPLATE = """\
Extract structured knowledge from the passage below.

{rules}

Passage:
{{document}}
""".format(rules=EXTRACTION_RULES)

# The context caveat only exists in the batched prompt, because only the
# batched prompt supplies context. It is load-bearing: evidence quotes are
# located in the highlight alone, so a quote taken from the context is dropped
# and its proposal is routed to human review as unevidenced.
BATCH_EXTRACTION_PROMPT_TEMPLATE = """\
Extract structured knowledge from each of the {count} passages below.

Return a single JSON object with exactly one top-level key, `items`, whose
value is a JSON array containing exactly one payload object per passage — no
other top-level keys.

Each passage is introduced by an `id:` line. Return one payload per passage,
carrying that passage's `batch_item_id` copied exactly. Return every id you
were given, exactly once each — no extras, no omissions. Treat each passage
independently: never let one passage's content justify another's extraction.

Some passages are followed by a `context:` block showing the surrounding text
in the original document, with {elision} marking where the passage itself was
removed. Context is for disambiguation only — resolving a pronoun, or seeing
what "it" refers to. NEVER quote from the context: every `evidence_quotes`
entry must be a verbatim substring of that passage's own `text`.

{rules}

Passages:
{passages}
"""


def build_extraction_prompt(normalized_content: str) -> str:
    return EXTRACTION_PROMPT_TEMPLATE.format(document=normalized_content)


def build_batch_extraction_prompt(items: Iterable[_HighlightLike]) -> str:
    """Render several highlights as one labeled, independently-extractable set."""
    blocks: list[str] = []
    count = 0
    for item in items:
        count += 1
        block = f"id: {item.batch_item_id}\ntext:\n{item.highlight_text}"
        if item.context_text:
            block += f"\ncontext:\n{item.context_text}"
        blocks.append(block)
    if not count:
        raise ValueError("build_batch_extraction_prompt requires at least one highlight")
    return BATCH_EXTRACTION_PROMPT_TEMPLATE.format(
        count=count,
        elision=CONTEXT_ELISION,
        rules=EXTRACTION_RULES,
        passages="\n\n---\n\n".join(blocks),
    )

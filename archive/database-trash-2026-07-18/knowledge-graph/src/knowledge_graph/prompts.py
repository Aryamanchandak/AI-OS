"""LLM prompt templates for the knowledge_graph package.

All prompts are plain strings with {placeholder} slots. Format them with
str.format() or .format_map() before sending to the LLM.
"""

# ---------------------------------------------------------------------------
# Triplet extraction
# ---------------------------------------------------------------------------

EXTRACT_TRIPLETS = """\
Extract all factual relationships from the text below. Return a JSON array of triplets.

Each triplet must have exactly these keys:
  "subject"  — the entity or concept that is the source (string)
  "relation" — the relationship type in UPPER_SNAKE_CASE (string, e.g. "CAUSES", "IS_A", "PART_OF",
                "REQUIRES", "CONTRASTS_WITH", "DEFINED_BY", "RELATES_TO")
  "object"   — the entity or concept that is the target (string)

Rules:
- Use clear, canonical noun-phrase names for subjects and objects.
- Keep relation labels concise and uppercase (e.g. CAUSES, REQUIRES, COMPONENT_OF).
- Extract only relationships that are clearly stated or strongly implied in the text.
- Return ONLY a JSON array — no explanation, no wrapper key, no markdown fences.

Text:
{text}

JSON:"""

# Appended to the extraction prompt on retry when the first attempt produced invalid JSON.
EXTRACT_TRIPLETS_RETRY_SUFFIX = (
    "\n\nYour previous response had issues: {last_error}. "
    "Return ONLY a valid JSON array of triplet objects."
)

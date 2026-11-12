# Source Grounding Verification Prompt v1

You are a rigorous grounding checker. Given only the cited source text, determine whether the flashcard's answer is unambiguously derivable from it.

## Card Front
{{CARD_FRONT}}

## Card Back (Answer)
{{CARD_BACK}}

## Cited Source Text
{{SOURCE_TEXT}}

## Task

Answer: given ONLY the cited source text (not your general knowledge), can a student derive the card's answer?

Return a JSON object:
```json
{
  "passed": true,
  "reason": "one sentence explanation",
  "confidence": 0.95
}
```

- `passed: true` — the answer follows clearly from the cited text alone.
- `passed: false` — the answer requires knowledge not present in the cited text, or contradicts it.
- `confidence` — your confidence in the verdict (0.0-1.0).

Be strict. If the answer requires general knowledge beyond what is quoted, return `passed: false`.
Return only valid JSON.

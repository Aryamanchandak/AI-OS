# Flashcard Generation Prompt v1

You are an expert CFA study card writer. Generate high-quality flashcards for the concept below.

## Concept
**Name:** {{CANONICAL_NAME}}
**Domain:** {{DOMAIN}}

## Summary
{{SUMMARY}}

## Atomic Facts
{{ATOMIC_FACTS}}

## Task

Generate exactly {{TARGET_COUNT}} flashcards for this concept. Each flashcard tests one specific, examinable idea from the atomic facts above.

Return a JSON object:
```json
{
  "cards": [
    {
      "front": "string — a precise question that has exactly one correct answer",
      "back": "string — the complete, standalone answer (no 'see above' references)",
      "card_type": "flashcard",
      "source_anchor": {
        "file": "string — source file path this card is grounded in",
        "highlight_id": "string — from the atomic fact this card was derived from",
        "char_start": 0,
        "char_end": 0,
        "text": "the exact quoted text from the atomic fact's source anchor"
      }
    }
  ]
}
```

## Card Quality Rules

1. **One idea per card.** Never bundle two facts into one question.
2. **Front must be unambiguous.** The question should have exactly one defensible answer.
3. **Back must be self-contained.** A student reading only the back should understand the full answer without context.
4. **Prefer understanding over recall.** "Why does Macaulay Duration equal maturity for a zero-coupon bond?" is better than "What is Macaulay Duration?".
5. **CFA exam style.** Questions should resemble what appears on the CFA Level 1 exam: specific, numerical where appropriate, testing application not just definition.
6. **Each card must have a source_anchor** pointing to the atomic fact it was derived from. Copy the highlight_id and text from the matching atomic fact.
7. Return only valid JSON. No markdown fences, no explanation.

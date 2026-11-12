# lib/prompts.ts — Technical Documentation

**Last updated:** 2026-05-10
**Lines of code:** 167
**Language:** TypeScript

---

## What This File Does (Plain English)

This file contains every prompt sent to Claude, and nothing else. Each prompt is either a string constant or a function that returns a string. The prompts instruct Claude to return strictly-formatted JSON and include the schema inline. All prompt engineering for the application lives here.

---

## How It Actually Works

### Entry Points

All five exports are imported by `lib/operations.ts`, which passes them as the `system` argument to `callClaudeJSON` or `callClaude`.

### Data Flow

Each prompt function receives runtime data (mode, sections, chat history, extracted context, etc.) and interpolates it directly into a template literal. The resulting string becomes the system prompt for a Claude API call.

### State Management

None — pure functions over string inputs, no mutable state.

### Key Functions / Classes

| Name | What it actually does |
|---|---|
| `PROMPT_SECTION_DETECTOR(mode)` | Returns a system prompt that instructs Claude to split either a prompt or a markdown plan into sections and return JSON with `sections[]`, each having `title`, `kind`, `content`, and `rationale`. The kind vocabulary is different for prompt vs plan mode. |
| `PROMPT_CONTEXT_EXTRACTOR` | A static string that instructs Claude to parse a freeform project dump into six structured fields: `goal`, `tech_stack`, `constraints`, `key_decisions`, `architecture_notes`, `open_questions`. |
| `PROMPT_ITERATION({...})` | Returns a system prompt for chat-driven section iteration. Injects the full document, the current section, the chat history, and the project context. Instructs Claude to return four fields: `rewritten_content`, `reasoning`, `clarifying_question`, `suggested_context_update`. |
| `PROMPT_CONFLICT_DETECTOR({...})` | Returns a system prompt that presents all sections (marking the just-edited one with `[EDITED]`) and asks Claude to find contradictions, redundancies, and orphan references. Returns `conflicts[]`. |
| `PROMPT_LLM_JUDGE({...})` | Returns a system prompt for evaluating whether a model output meets a stated criterion. Returns `{passed: boolean, reasoning: string}`. Used by the `semantic` assertion type. |

### External Dependencies

- `lib/types.ts` — imports `Mode`, `Section`, `ExtractedContext`, `ChatMessage`
- No API calls or I/O — all pure template construction

### Error Handling

None — these are string-returning functions. Errors only emerge downstream when the generated strings are used in API calls.

---

## Non-Technical Decisions Embedded in the Code

- Every prompt ends with `Return ONLY valid JSON with this exact schema:` followed by a schema literal. This is the primary defense against Claude wrapping output in prose. The schema is shown verbatim in the system prompt, not computed or derived.
- `PROMPT_SECTION_DETECTOR`: "80% of users should accept your splits without reorganizing" — this acceptance-rate target is baked into the prompt as an instruction. It's a heuristic about Claude's judgment, not a measurable guarantee.
- `PROMPT_SECTION_DETECTOR`: `content` is explicitly labeled `"VERBATIM text from the input"`. This is the critical constraint — if Claude paraphrases, downstream diffs become meaningless because the content no longer matches the user's original text.
- `PROMPT_ITERATION`: when `projectContext` is null, the injected text is `"(no context provided yet — be especially willing to ask clarifying questions)"`. This is the mechanism that causes Claude to default to asking questions rather than guessing when context is missing.
- `PROMPT_ITERATION`: chat history is rendered by joining `m.role + ': ' + m.text` — there is no structural separation between user and assistant turns, just a convention. Claude is expected to interpret the format correctly.
- `PROMPT_CONFLICT_DETECTOR`: sections are labeled `[EDITED]` or `[OK]` to distinguish which one just changed. The brackets are inline markers in the section header — they depend on Claude reliably parsing this convention.
- `PROMPT_LLM_JUDGE`: "If the criterion is ambiguous, lean toward `passed: false`" — conservative bias toward failure. This means an underspecified criterion will produce `false` results rather than noise.
- `PROMPT_LLM_JUDGE`: when `projectContext` is present, there is a spacing inconsistency — the context block ends with a newline and then `CRITERION:` follows immediately. When context is absent, `CRITERION:` appears at the top. Functionally harmless but cosmetically inconsistent.

---

## Honest Gaps and Risks

- **All schemas are inline strings.** If the schema changes (adding a field, renaming a field), the developer must update both the prompt string here and the TypeScript type in `lib/types.ts` (and `lib/operations.ts` where the response is destructured). There is no shared source of truth — these three places can silently drift.
- **No versioning.** The `Plan.md` mentions `prompts/section_splitter_v1.md` as a future versioned location, but prompts are inlined in this file with no version identifier. Iterating on a prompt without tracking the previous version makes regression analysis impossible.
- **`PROMPT_ITERATION` injects the full document as a string** (`fullDocument`). For a long document with many sections, this can be thousands of tokens prepended to every iteration call, driving up API cost and potentially hitting context limits.
- **`PROMPT_CONFLICT_DETECTOR` injects all section content** in one call. For large plans, this can be very large — the total token count is proportional to the sum of all section lengths.
- **No validation that the interpolated data is safe.** If a section's content contains characters like `"""` (the delimiter used in `PROMPT_ITERATION`), it could confuse Claude's parsing of the prompt structure.
- **`PROMPT_CONTEXT_EXTRACTOR`** instructs Claude to "not invent" data, but the field `open_questions` could include invented questions if Claude interprets the absence of explicit open questions as a signal to generate plausible ones.

---

## Developer Notes

When you edit a prompt, the change affects every call to that prompt simultaneously — there is no per-call override mechanism. To A/B test prompt variations, you would need to duplicate the function and wire the alternative to a separate code path. The `PROMPT_LLM_JUDGE` prompt is itself a first-class prompt in the application's domain (the `Plan.md` calls this "pleasingly recursive") — it is a reasonable candidate for the tool to analyze and iterate on itself.

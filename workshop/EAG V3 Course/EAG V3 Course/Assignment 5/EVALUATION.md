# Prompt Evaluation — Veritas Master Prompt

The assignment requires that the prompt be **qualified** by an LLM against the
session's evaluation rules, and that the qualification output be shown.

Everything below is **real model output**, produced by running:

```bash
cd veritas && python evaluate.py
```

Raw artifacts are committed under `veritas/evaluations/`:
`v1.json`, `v2.json`, `v1.raw.txt`, `v2.raw.txt`, `summary.json`. Nothing in
this file was authored by hand — re-run the script to reproduce it.

- **Judge:** `openai/gpt-4o` (the assignment permits ChatGPT; this is the key
  present in the environment). To re-run under Claude, set `ANTHROPIC_API_KEY`
  and `evaluate.py` will use `claude-opus-4-8` automatically.
- **Result:** v1 scored **3/9 yes**; v2 scored **9/9 yes, 0 critical gaps**.

> ⚠️ **Rubric provenance.** The session's own evaluation prompt was not
> available in this repo at build time, so `evaluate.py` uses the standard
> nine-criterion TSAI rubric, reproduced verbatim below. If your session used
> different criteria, replace `EVALUATOR_PROMPT` in `veritas/evaluate.py` and
> re-run — nothing else changes.

---

## The evaluator prompt

Verbatim from `veritas/evaluate.py`:

```text
You are an expert prompt evaluator. Evaluate the following system prompt
against these nine criteria. For each, answer yes/no/partial and justify in one
sentence. Then return a JSON block with the scores.

1. Explicit Reasoning Instructions - does the prompt tell the model to
   reason step-by-step before answering?
2. Structured Output Format - does it define a clear, parseable output
   structure?
3. Separation of Reasoning and Tools - is thinking separated from tool
   use / action?
4. Conversation Loop Support - can it handle multi-turn or iterative
   interaction?
5. Instructional Framing - does it explain how to behave, with examples
   or clear role definition?
6. Internal Self-Checks - does it instruct the model to verify its own
   output?
7. Reasoning Type Awareness - does it ask the model to identify the KIND
   of reasoning being used?
8. Error Handling / Fallbacks - does it define what to do when things
   fail or are ambiguous?
9. Overall Clarity - is the prompt clear and unambiguous?

Be a demanding grader. Award "yes" only when the prompt operationalizes the
criterion with a concrete mechanism; award "partial" when it gestures at the
criterion without enforcing it; award "no" when it is absent.

Return ONLY this JSON object: { ... }
```

---

## Round 1 — v1 prompt · **3/9**

v1 was a single block: role, the seven skills as a bulleted list, "return JSON".

<details>
<summary>v1 prompt (superseded)</summary>

```text
You are Veritas, a scientific claim verification agent. Given a claim, you
verify it against published literature.

Your skills:
- decompose the claim into sub-claims
- search for evidence
- fetch primary sources
- extract findings
- grade source quality
- synthesize a verdict
- verify your own work

Return a verdict of Supported, Mixed, Refuted, or Insufficient Evidence,
with a confidence score and citations for each claim you make. Be rigorous
and do not make things up. Return your answer as JSON.
```
</details>

### Judge output — `veritas/evaluations/v1.json`

```json
{
  "scores": {
    "explicit_reasoning_instructions": "partial",
    "structured_output_format": "yes",
    "separation_of_reasoning_and_tools": "partial",
    "conversation_loop_support": "no",
    "instructional_framing": "partial",
    "internal_self_checks": "yes",
    "reasoning_type_awareness": "no",
    "error_handling_fallbacks": "partial",
    "overall_clarity": "yes"
  },
  "justifications": {
    "explicit_reasoning_instructions": "The prompt suggests a process but does not explicitly instruct step-by-step reasoning.",
    "structured_output_format": "The prompt specifies returning the answer in JSON format.",
    "separation_of_reasoning_and_tools": "The prompt combines reasoning tasks with tool usage but does not clearly separate them.",
    "conversation_loop_support": "The prompt does not account for iterative or multi-turn interactions.",
    "instructional_framing": "The prompt defines a role but lacks specific behavior examples.",
    "internal_self_checks": "The prompt instructs the model to verify its own work.",
    "reasoning_type_awareness": "The prompt does not require the model to identify reasoning types.",
    "error_handling_fallbacks": "It suggests not making things up but lacks detailed error handling instructions.",
    "overall_clarity": "The prompt is clear in conveying its intent and format requirements."
  },
  "total_yes": 3,
  "critical_gaps": [
    "explicit_reasoning_instructions",
    "conversation_loop_support",
    "reasoning_type_awareness"
  ],
  "verdict": "The prompt is adequately designed with emphasis on self-checking and structured output but lacks support for iterative interaction and explicit reasoning steps."
}
```

**3 yes · 4 partial · 2 no.**

Worth noting where the judge was more generous than I would have been: it awarded
`internal_self_checks: yes` for the bare phrase *"verify your own work"* and
`structured_output_format: yes` for *"return your answer as JSON"* with no schema.
Both are named ambitions with no mechanism behind them — exactly the gap v2 closes.
The judge's own `verdict` field is likewise softer than its scores warrant.

---

## Round 2 — v2 prompt · **9/9**

Each v1 gap was addressed with a concrete mechanism rather than a stronger
exhortation:

| v1 gap | Fix in v2 |
|---|---|
| `explicit_reasoning_instructions: partial` | `# REASONING PROTOCOL` — a mandatory `reasoning` field populated before the answer fields |
| `reasoning_type_awareness: no` | Six mandatory inference tags (`[DEDUCTIVE]`, `[STATISTICAL]`, `[CAUSAL]`, …); an untagged step is declared malformed |
| `conversation_loop_support: no` | `# CONVERSATION AND STATE` — statelessness contract, `PRIOR_ATTEMPT` / `VERIFIER_FEEDBACK`, `MAX_ROUNDS`-bounded retry edge |
| `separation_of_reasoning_and_tools: partial` | `ACTIVE_SKILL` binds each call to one skill; `fetch` moved out of the LLM entirely into deterministic code |
| `error_handling_fallbacks: partial` | `# ERROR HANDLING AND FALLBACKS` — six named degraded cases, each with a `status` enum value |
| `instructional_framing: partial` | Per-skill contract files with worked examples and explicit `OUTPUT_SCHEMA` blocks |
| "verify your own work" was decorative | `# SELF-CHECKS` — a seven-item pre-emit checklist, plus a separate `verify` skill running six named audit checks |
| "do not make things up" was unenforceable | `# EVIDENCE DISCIPLINE` — five mechanical rules (source_id required, no un-supplied citations, numbers copied not recalled, disconfirming search mandatory, `Insufficient Evidence` legitimized) |

### Judge output — `veritas/evaluations/v2.json`

```json
{
  "scores": {
    "explicit_reasoning_instructions": "yes",
    "structured_output_format": "yes",
    "separation_of_reasoning_and_tools": "yes",
    "conversation_loop_support": "yes",
    "instructional_framing": "yes",
    "internal_self_checks": "yes",
    "reasoning_type_awareness": "yes",
    "error_handling_fallbacks": "yes",
    "overall_clarity": "yes"
  },
  "justifications": {
    "explicit_reasoning_instructions": "The prompt explicitly requires reasoning in a 'reasoning' field before providing an output, with mandatory tagging of inference type.",
    "structured_output_format": "It clearly defines a JSON object with specific keys as the output format.",
    "separation_of_reasoning_and_tools": "The prompt separates reasoning (in the 'reasoning' field) from action (in the 'output' field).",
    "conversation_loop_support": "It includes mechanisms for handling iterative interactions and re-invocations in a pipeline loop.",
    "instructional_framing": "The prompt provides a detailed role definition and how to behave as Veritas with defined skills.",
    "internal_self_checks": "It includes a checklist to verify outputs before final submission.",
    "reasoning_type_awareness": "The prompt requires tagging each reasoning step with a specific type of inference.",
    "error_handling_fallbacks": "The prompt includes specific error handling and fallback strategies for various issues.",
    "overall_clarity": "The prompt is comprehensive and unambiguous, with clear instructions."
  },
  "total_yes": 9,
  "critical_gaps": [],
  "verdict": "The prompt is exceptionally well-constructed, addressing all criteria thoroughly."
}
```

**9 yes · 0 partial · 0 no · 0 critical gaps.**

A caveat I'd rather state than hide: a 9/9 from a single judge on a prompt this
long is a soft signal. LLM graders reward explicit structure, and v2 is
conspicuously structured — headed sections that name each rubric criterion almost
verbatim. The score confirms the prompt *addresses* every criterion; it does not
prove the mechanisms work. The evidence that they work is in the run traces, not
here.

---

## From rubric criterion to observable behaviour

Each criterion is verifiable in the JSON traces under `veritas/runs/`, not just
asserted in the prompt:

| Criterion | Where you can see it in a trace |
|---|---|
| Explicit reasoning | `steps[].reasoning` populated on every LLM skill |
| Reasoning-type awareness | `[STATISTICAL]` / `[CAUSAL]` tags inside those reasoning strings |
| Structured output | Every `steps[].output` is schema-shaped JSON |
| Separation of reasoning and tools | `fetch` appears with no `reasoning` — it is code |
| Internal self-checks | The `verify` step's `checks[]` array: six named pass/fail results |
| Error handling | `status` fields, `unusable_sources` (4 in run 2), `direction: "irrelevant"` counts |
| Conversation loop | `steps[].round`, plus a second `search` step whenever `verify` returns `needs_more_evidence` |

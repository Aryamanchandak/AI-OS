# Bite 3: Grade an answer (I5)

**Goal:** `grade(card, answer)` returns a Verdict, and code turns it into a rating.
**Builder:** Claude, with your eval cases. **After:** bite 2. **Budget:** about 120 lines plus the prompt.

**Needs you:** write the cases in `grade.evals.yaml`: right, wrong, half-right, fluent but wrong. Examples 1–3 in `nodes/learnsys.md` are drafts to replace.

**Write the tests first (offline, fake I1):**
- Each verdict maps to its rating: wrong and fluent_wrong give Again, partial gives Hard, correct gives Good, complete gives Easy.
- A reply that breaks the schema raises an error; it is never guessed.
- The call uses the answer-grading-v1 profile and sends a JSON schema.

**Build:**
- `leaves/learning/grade.py` and `prompts/grade_v1.md`, reusing interview-coach's strict calibration, cite-their-words and JSON-only rules.
- `tests/eval_runner.py` (I14), marked `eval`.

**Done when:** the offline tests pass, and `pytest -m eval` scores your cases against the live gateway.
**Out of scope:** the tools, scheduling.

---
id: learnsys
stage: 1
part: leaf
provides: [I4, I5]
uses: [I1, I2, I3]
builder: claude
reviewer: codex
line_budget: 400
existing: pull pieces (projects/learning/learning-system; projects/life/interview-coach/prompts/evaluation.md)
status: detailed
---

# Learning system: Stage 1

**Job:** schedule your CFA cards, grade typed answers, and keep the mistake log.

## Rules (all assumed; change any)

**Grade to rating.** The model gives a verdict and code turns it into a rating:
- **wrong** gives Again.
- **fluent_wrong** (sounds right, but is wrong) gives Again.
- **partial** (a key point missing) gives Hard.
- **correct** gives Good.
- **complete** (correct, with every key point and the right terms) gives Easy.

**Mistakes.** Every Again on a concept card logs a mistake automatically, with the grader's reason as "why". You can also log one by hand.

A mistake holds:
- the question
- your answer
- the correct answer
- the topic
- why it was wrong
- the source (review or manual)
- the date

**Disagreeing.** If you think the grade is wrong, you tap a different rating. Your rating is the one that counts. The pair (your answer, your rating) is saved as a candidate eval case.

**Card kinds.** You set each card's kind in the deck file, and it defaults to concept. Formula cards show the answer on a button press and get four rating buttons, with no model call.

**Session size.** At most 20 due cards per sitting, and 10 new cards a day.

**Decks.** One YAML file per deck in `leaves/learning/decks/`. Each card has `front`, `back`, `kind`, `topic`, and optionally `los`.

## Done when (assumed examples; replace with your own)

1. **Correct answer.** The concept card "Why does a bond's price fall when market yields rise?" is answered "the fixed coupons are discounted at a higher rate, so their present value falls". It is graded **Good**, and the next due date is set.
2. **Fluent but wrong.** The concept card "What does Macaulay duration measure?" is answered "how much the price changes for a 1% change in yield". That describes modified duration, so it is graded **Again**. A mistake is logged with that reason.
3. **Partial answer.** The concept card "Give two differences between yield to maturity and current yield" is answered with one difference. It is graded **Hard**, and the reason names the missing one.
4. **Formula card.** The formula card "Modified duration" gets answer, then Good. No model call is made, and the next due date is set.

Cases 1 to 3 are also the first grading eval cases. Your capstone guardrail says tests submitted for credit should be written by you, so treat these as drafts to replace.

## Build

**`leaves/learning/` contents:**
- Tables, migrated through I2: `cards`, `card_state` (py-fsrs card JSON), `reviews` and `mistakes`.
- The deck loader.
- The four tools in I4, registered through I3.
- `grade()` (I5), which calls I1 with a JSON schema. The prompt is `prompts/grade_v1.md`.

**Scheduling** uses the py-fsrs library (approved 2026-11-03), behind `leaves/learning/schedule.py`.

**Evals** use the I14 shape: `leaves/learning/grade.evals.yaml`, run with `pytest -m eval`.

**Reused from the old Learning System:**
- the idea of a card-kind enum, cut down to concept and formula
- the review-state table design

**Not reused from it:**
- the hand-written FSRS scheduler (174 lines; the library replaces it)
- `StudyCore`
- overrides, idempotency and generation runs
- Feynman and challenger

**Reused from interview-coach's evaluation prompt:** its strict calibration, "cite the candidate's words" and "JSON only" rules.

## Delayed

- Generating cards from your notes (Stage 2).
- The screenshot-to-mistake path (Stage 2).
- Formula images (Stage 2).
- Voice answers.
- Understanding check and Sharpen.
- The GMAT deck.
- Graphiti and Chroma.

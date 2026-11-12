# Bite 1: Contracts and fakes

**Goal:** the shapes in I4 and I7 exist as code, with a fake learning system that passes the I4 contract tests.
**Builder:** Claude. **After:** Stage 0 (needs `core/registry.py`). **Budget:** about 120 lines.

**Write the tests first:**
- `tests/contracts/test_i4.py`: next_card returns a Card with no back; submit_answer returns Graded; rate_card returns a next due date; log_mistake returns a Mistake; unknown card_id is refused. It takes the implementation as a fixture so the real system can run it later.
- `tests/contracts/test_i7.py`: a Button tap becomes `registry.call(tool, payload)`.

**Build:**
- `leaves/learning/models.py`: the Pydantic models Card, Graded, Mistake and NewMistake.
- `leaves/telegram/buttons.py`: the Button model and the tap-to-registry function.
- `tests/fakes/learning.py`: two hard-coded cards, registered through I3.

**Done when:** `pytest tests/contracts` passes against the fake.
**Out of scope:** real tables, grading, the bot itself.

# Bite 4: Scheduling and the four tools (I4)

**Goal:** the real learning system passes the same I4 contract tests as the fake.
**Builder:** Claude. **After:** bite 3. **Budget:** the learning system stays under 400 lines in total.

**Write the tests first (fake I1, frozen clock):**
- Examples 1–4 from `nodes/learnsys.md`. Example 4 asserts that no model call is made.
- An Again on a concept card logs a mistake with the grader's reason.
- Your override rating wins and is saved as a candidate eval case.
- At most 20 due cards per sitting and 10 new cards a day.
- `tests/contracts/test_i4.py` runs against the real tools.

**Build:**
- `leaves/learning/schedule.py`: the only file that imports py-fsrs.
- `leaves/learning/tools.py`: the four tools, registered through I3.

**Done when:** all learning tests and the I4 contract tests pass.
**Out of scope:** the bot, card generation.

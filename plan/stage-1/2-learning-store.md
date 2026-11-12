# Bite 2: Learning tables and decks

**Goal:** decks in YAML load into the learning system's own tables.
**Builder:** Claude. **After:** bite 1. **Budget:** about 100 lines.

**Write the tests first:**
- Loading `decks/cfa-fixed-income.yaml` creates one row per card.
- Loading it again adds nothing; an edited back updates the card.
- A card with an unknown kind is refused with the file and line.
- A missing kind defaults to concept.

**Build:**
- `leaves/learning/migrations.py`: the tables cards, card_state, reviews and mistakes, migrated through I2 with owner `learning`.
- `leaves/learning/decks.py`: the loader.
- `leaves/learning/decks/cfa-fixed-income.yaml`: the four example cards from `nodes/learnsys.md`.

**Done when:** the tests pass on a temporary database file.
**Out of scope:** scheduling, grading.

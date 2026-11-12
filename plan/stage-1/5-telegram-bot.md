# Bite 5: Telegram bot (against the fake)

**Goal:** every "done when" in `nodes/telegram.md` works against the fake learning system.
**Builder:** Codex. **After:** bite 1, in parallel with bites 2–4. **Budget:** 250 lines.

**Write the tests first (no network; the handlers are called directly):**
- `/review` shows the fake's next card.
- A typed reply shows the grade, the reason, the correct answer and four buttons.
- Formula card: Show answer, then four rating buttons.
- Nothing due: says so with the next due time.
- `/mistake <text>` calls log_mistake.
- A message from another chat ID is ignored.

**Build:** `leaves/telegram/bot.py`, the only file that imports python-telegram-bot. It calls only registry tools through I7 buttons. The token and chat ID come from `.env`.

**Done when:** the tests pass; the bot answers you with the fake when you run it once by hand.
**Out of scope:** voice, photos, the push.

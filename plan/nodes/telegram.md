---
id: telegram
stage: 1
part: leaf
provides: [I7]
uses: [I3, I4]
builder: codex
reviewer: claude
line_budget: 250
existing: rewrite (no Telegram code found)
status: detailed
---

# Telegram: Stage 1

**Job:** turn your messages and button presses into learning-tool calls. It has no logic of its own.

**Done when:**
1. `/review` shows the next due card.
2. For a concept card, your typed reply comes back with the grade, the reason and the correct answer. Four buttons let you disagree.
3. For a formula card, "Show answer" reveals the back, then four rating buttons appear.
4. When nothing is due, it says so and gives the next due time.
5. `/mistake <text>` logs a manual mistake.
6. Messages from any chat other than yours are ignored.

**Build:**
- `leaves/telegram/bot.py`, using python-telegram-bot (approved 2026-11-03), behind that one file.
- The bot runs on the laptop with long polling: it asks Telegram for new messages, so no public URL is needed.
- It calls only I4 tools, through the registry (I3). It never touches the store or the model.
- Every button is an I7 `Button(label, tool, payload)`, so a tap is just a registry call.
- The bot token and your chat ID come from `.env`.
- It is built and tested against a fake learning system first, so it can be built in parallel with `learnsys`.

**Delayed:**
- Voice answers.
- Photo buttons (Mistake, Reading, Task).
- The 8am push (Stage 3).
- Mini Apps.
- Moving to the VPS (Stage 3).

Bot chats aren't end-to-end encrypted, which is already noted in the threat model.

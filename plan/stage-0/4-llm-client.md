# Bite 4: Model client (I1)

## For you

**What already exists.** The gateway accepts model requests at `/api/llm/chat` with a token, but nothing in AI OS calls it yet. `projects/life/interview-coach/llm.py` calls Anthropic directly, which skips the gateway and its cost log.

**What's being built.** `core/llm.py`, about 60 lines: one `chat()` function that the rest of AI OS uses to reach any model, always through the gateway. It's tested first against a fake gateway, then live with the grading case from bite 1.

**Your input** (write under each one):

1. Approve httpx (a library for sending web requests, which the gateway already uses) in the root project?
   - Your answer:
2. Should interview-coach later switch to going through the gateway, so its costs are logged too? It's out of scope for this bite either way.
   - Your answer:

---

**Goal:** `core/llm.py` is the only way AI OS code reaches a model, and golden case #1 runs through it.
**Builder:** Claude. **After:** bites 1 and 2. **Budget:** about 60 lines.

**Needs your OK:** an HTTP client library in the root project. The proposal is httpx, which the gateway already uses. Once approved it goes in `DEPENDENCIES.md`.

**Write the tests first:** `tests/contracts/test_i1.py`.
- A fake gateway returns a fixed JSON reply, and `chat()` returns the same `Reply` (text, parsed, tokens, cost).
- `images` are sent as base64 `image_url` blocks.
- A gateway error comes back as one clear exception, not a raw HTTP error.
- Live, marked `golden`: the `answer-grading-profile` request from bite 1, sent through `chat()` to the running gateway. It returns text and adds one ledger row.

**Build:** `core/llm.py` with `chat(profile, prompt, system, schema, images, agent, session) -> Reply`. It reads the gateway URL and `AI_OS_TOKEN` from `.env`, and loads `.env` before anything else reads it.

**Done when:** the offline contract tests pass and the live golden test passes. That covers Stage 0's first done-when.
**Out of scope:** retries, streaming, embeddings.

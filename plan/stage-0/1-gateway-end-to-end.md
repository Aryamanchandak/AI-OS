# Bite 1: Gateway end to end [THIS IS NOT A PLAN REALLY, IS THIS HOW YOU DO ADLC PLANS ??]

## For you

**What already exists.** The gateway is built: about 2,200 lines in `gateway/src`, with a `/health` page, a cost ledger (`Database/sqlite/gateway.sqlite`), a `.env` loader and 8 profiles (named model settings) in `config/profiles.yaml`. None of the profiles is for grading. `tests/golden/cases.yaml` already has 4 real-call cases. One of them, `reply-exactly-ok`, already checks that a Claude call writes one ledger row with a cost. 19 files in `gateway/` have uncommitted changes, and 4 new files (Graphiti readiness work and `simple_llm/`) were never added to git. What isn't known: whether these golden cases have ever passed with your real key.

**What's being built.** One new profile, `answer-grading-v1`, and one golden case built from a real CFA question. The case checks that the grade comes back right, not just that a row was logged. No other gateway code.

**Your input** (write under each one):

1. Has `pytest -m golden` ever passed with your real Anthropic key? Yes, no or not sure.
   - Your answer: NOT sure
2. A real CFA question:
   - Your answer: you can come up with one, use opus to come up with soem 
3. An answer to grade, ideally partly wrong:
   - Your answer: what grade ? then use sol or the other way around to grade 
4. The grade it should get, and why:
   - Your answer: not sure, use opus or sol I have access to both 
5. Is `claude-haiku-4-5` (the cheapest model) fine for grading?
   - Your answer: if it works for you 
6. The 23 uncommitted `gateway/` files (19 changed, 4 new): should I read the diffs and recommend, or do you already know (review and commit, branch, or stash)?
   - Your answer:

---

**Goal:** one real grading call goes through the gateway and writes a ledger row (see `nodes/gateway.md`).
**Builder:** Claude. **After:** your call on the uncommitted `gateway/` work (below). **Budget:** about an hour; no new gateway code beyond one profile and one golden case.

**Decide first, before any change:** `gateway/` has 19 modified files, and they're not just Graphiti. They include `providers/llm.py`, `providers/base.py`, `service.py` and the tests, and none of them is reviewed yet. Graphiti itself is frozen. Pick one: review then commit, move them to a branch, or stash them.

**Write the tests first:**

- In `tests/golden/cases.yaml`, add `answer-grading-profile` as the first case. It uses profile `answer-grading-v1` and one CFA question plus answer, and expects `ledger_rows: 1` and `cost_above_zero: true`.

**Build:**

- In `config/profiles.yaml`, add `answer-grading-v1` on Anthropic `claude-haiku-4-5`. Assumed.
- You put the Anthropic key and `AI_OS_TOKEN` in `gateway/.env`. I never read that file.
- Start the server, make the call by hand, and check that the ledger has the row.

**Done when:** `pytest -m golden` passes the new case, and the offline suite still passes with the same count as before.
**Out of scope:** the client (bite 4), embeddings, Ollama profiles, Langfuse, deploy.

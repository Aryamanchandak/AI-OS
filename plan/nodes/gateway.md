---
id: gateway
stage: 0
part: trunk
provides: [I1]
uses: []
builder: claude
reviewer: codex
line_budget: no growth (existing ~2,200 lines)
existing: keep and finish (gateway/)
status: detailed
---

# Gateway

**Path chosen 3 Nov: finish the gateway.** Build steps are in `stage-0/1-gateway-end-to-end.md`.

**Job:** the only path to any model, with every call logged.

**Done when:**
1. With the gateway running, one real Claude call with the `answer-grading-v1` profile returns an answer.
2. That call writes one row to the ledger, with tokens and cost.
3. That request is golden-set case #1 in `gateway/tests/golden/cases.yaml`, and `pytest -m golden` passes it.

**Build (about an hour):**
**Working-tree baseline:** gateway was clean on 13 Nov 2026. Recheck before implementation; do not use historical changed-file counts as blockers.
- You put the Anthropic key and `AI_OS_TOKEN` in `gateway/.env`.
- Add the `answer-grading-v1` profile: Anthropic, `claude-haiku-4-5`. That's the cheap model already in your profiles. Assumed.
- Run the server and make the call.
- Check the ledger row.
- Run the golden test, then the offline tests (record the actual result).

The client side (I1) is `core/llm.py`. It is written in Stage 0 with the other trunk pieces, so the gateway itself gains no code.

**Delayed:**
- Embeddings and the Ollama profiles (needed when memory enters).
- The ingestion runner's port mismatch (8107 vs 8000).
- The OpenAI-compatible endpoint for Graphiti.
- Batching and Together.
- Langfuse (Stage 5).

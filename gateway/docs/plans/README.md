# Gateway Shrink Plans

As of 2026-10-18 · Sources: `docs/yagni-review.md`, `docs/yagni-review-followup.md`

These plans shrink the gateway until you can explain it one module at a time, then get one request working end to end. Start a step only when you say "start step N". Re-check its plan first, because earlier steps change the code. Your OK on a plan covers the test files it lists for deletion; nothing else gets deleted.

**Done.** Step 0 (commit `8f64fbd`). Steps 1–2c (commit `fa30d94`): dead code and fake routes, providers trimmed to Claude/GPT/Ollama with prices fixed, streaming and semantic cache removed, unused request features removed, budgets by agent and session. Step 3 (commit `564e389`): `/v1` addresses, shell hosting, legacy health and dashboard routes, the agent-trace forwarder and the service registry removed ([archived plan](archive/step-3-mechanical-batch.md)). Suite passes (113 tests, 2026-10-19).

**Step 4 — one call log** ([step-4-one-call-log.md](step-4-one-call-log.md)). The ledger becomes the only call log, one YAML adapter, one SQLite helper. Separate because it changes behaviour (spend survives restarts) and adds a file.

**Step 5 — end to end** ([step-5-end-to-end.md](step-5-end-to-end.md)). Load keys from `.env`, one real Claude request, the golden set. First time the gateway works.

**Steps 6–7** ([step-6-any-llm.md](step-6-any-llm.md), [step-7-together.md](step-7-together.md)). any-llm and OpenTelemetry behind one adapter each; then Together as config only. Both are checked against the step 5 golden set.

## Later: new features, not planned yet

Your CLAUDE.md says to flag new features until one request works end to end. Each gets its own plan after step 5: an OpenAI-format address for Graphiti (chat with structured output plus embeddings, logged and costed; check what its reranker needs); real batching on Anthropic, OpenAI and Together (checking for results needs a scheduling library); a spend dashboard as a leaf reading `/cost`; the image pipeline as an ingestion leaf, once your image-approach chat is settled; and a trace viewer such as Arize Phoenix, the first time you need to debug a trace.

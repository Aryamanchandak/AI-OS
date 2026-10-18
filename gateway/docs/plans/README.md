# Gateway Shrink Plans

As of 2026-10-18 · Sources: `docs/yagni-review.md`, `docs/yagni-review-followup.md`

These plans shrink the gateway until you can explain it one module at a time, then get one request working end to end. Each step has its own plan file.

**How to use these plans**
- **Do one step per session**, and start a step only when you say "start step N".
- **Re-check each plan at the start of its session.** The plans describe the code as it was on 2026-10-18, and earlier steps change it.
- **Your OK on a plan covers the test files it lists for deletion.** Nothing else gets deleted.
- **Commit after every step.** Each plan ends with the git commands.

## The steps

| Step | Plan | One line | Status |
|---|---|---|---|
| 0 | [step-0-commit-pending-work.md](step-0-commit-pending-work.md) | Commit the work already sitting uncommitted, so step 1 starts from a clean slate | Not started |
| 1 | [step-1-dead-code-and-fake-routes.md](step-1-dead-code-and-fake-routes.md) | Remove code nothing calls, and routes that return made-up data | Not started |
| 2a | [step-2a-trim-providers.md](step-2a-trim-providers.md) | Keep only Claude, GPT and the local Ollama models; one provider entry per company; fix prices | Not started |
| 2b | [step-2b-remove-streaming-and-semantic-cache.md](step-2b-remove-streaming-and-semantic-cache.md) | Remove streaming and the semantic cache | Not started |
| 2c | [step-2c-remove-unused-request-features.md](step-2c-remove-unused-request-features.md) | Remove `/chat/batch`, the fake `batch` setting, the unused routing fields, `/vision`, image downloading; budgets by agent + session | Not started |
| 3 | [step-3-move-non-llm-features-out.md](step-3-move-non-llm-features-out.md) | Remove the old `/v1` addresses, shell hosting, the legacy health and dashboard routes, the agent-trace forwarder | Not started |
| 4 | [step-4-one-call-log-and-config-adapter.md](step-4-one-call-log-and-config-adapter.md) | The ledger becomes the only call log; one YAML adapter; one SQLite helper | Not started |
| 5 | [step-5-end-to-end-and-golden-set.md](step-5-end-to-end-and-golden-set.md) | Load keys from `.env`, get one real Claude request working end to end, build the golden set | Not started |
| 6 | [step-6-any-llm-and-otel-adapters.md](step-6-any-llm-and-otel-adapters.md) | Replace the hand-written provider code with any-llm; OpenTelemetry behind one adapter | Not started |
| 7 | [step-7-add-together.md](step-7-add-together.md) | Add Together.ai as a provider | Not started |

Steps 1–4 only remove or merge code, so the gateway gets smaller before it's proven. Step 5 is the first time it works end to end. Steps 6–7 are checked against the golden set from step 5.

## Later: new features, not planned yet

Your CLAUDE.md says to flag new features until one request works end to end. Each of these gets its own plan after step 5:

- **An OpenAI-format address for Graphiti.** Graphiti's chat calls (with structured output, which forces replies into a fixed JSON shape) and its embeddings go through the gateway, so they're logged, costed and use your nomic embedding model. Check what Graphiti's reranker needs.
- **Real batching.** Submit work to the batch services of Anthropic, OpenAI and Together, store the batch ID, check when results are ready, and store them. Checking needs a scheduling library, not hand-written code.
- **A spend dashboard.** A leaf that reads the gateway's `/cost` routes. It sits outside the trunk.
- **The image pipeline.** An ingestion leaf. The nomic vision embedder runs as its own small local service. Captions go through gateway profiles. Plan it once your separate image-approach chat is settled.
- **A trace viewer**, such as Arize Phoenix. Add one the first time you need to debug a trace.

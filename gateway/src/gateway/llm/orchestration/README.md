# Chat request orchestration

This folder coordinates one chat request from validation to response. `pipeline.py` implements `LLMPipeline`; stages exchange data through `PipelineContext` in `context.py`. `__init__.py` exports the pipeline.

## Normal chat stages

| Order | File | Work performed |
| --- | --- | --- |
| 1 | `validation.py` | Requires prompt/messages and a positive token limit; rejects conflicting profile selectors and overly deep/large response schemas. |
| 2 | `profile_resolution.py` | Resolves a named chat profile to an exact provider/model pin. |
| 3 | `normalization.py` | Converts a plain prompt to messages, safely fetches remote `image_url` blocks into data URLs, and estimates input tokens. |
| 4 | `cache_lookup.py` | Builds cache namespace fields, performs scoped semantic lookup, and saves the embedding for later storage. A hit supplies the response early. |
| 5 | `routing.py` | Chooses explicit or ordered registry candidates and rejects missing/unavailable selections. |
| 6 | `budget.py` | Reserves projected spending across the candidate set and raises HTTP 402 when admission fails. |
| 7 | `provider_call.py` | Calls providers under a concurrency semaphore, retries retryable provider errors, falls through to other providers when unpinned, and verifies returned profile models. |
| 8 | `structured_output.py` | Parses and validates JSON against the original schema; on failure makes one repair request and combines both results' token usage. Tool-call results bypass this validation. |
| 9 | `finalization.py` | Runs once from a `finally` boundary, calculates cost, reconciles/releases budget, records in-memory usage, and writes durable audit metadata. |
| 10 | `cache_store.py` | Stores successful normal responses after cost/budget attachment, reusing the lookup embedding. |

Cache hits bypass routing, budget reservation, provider execution, and structured validation, but still reach finalization. The current provider-call defaults permit one retry and 32 concurrent calls within that stage. Explicit provider/profile selection prevents cross-provider failover. Routing uses registry order; there is no classifier or tier escalation here.

## Streaming path

`run_stream()` eagerly runs stages 1–6 so validation/routing/budget failures remain ordinary HTTP errors. A cache hit returns JSON even if streaming was requested. Otherwise `_stream_frames()` streams from the first candidate directly; it does not use the normal provider-call semaphore/retry/failover stage or structured-output repair/cache-storage stages.

`streaming.py` encodes SSE text deltas, tool-call delta strings, errors, and terminal done frames. A confirmed profile model mismatch produces an error frame; an unconfirmed model is marked in the done frame. Finalization belongs to the generator's `finally` block, so disconnects and cancellation still reach accounting. Accounting uses whatever complete provider result is available: buffered adapters supply one, while the incremental compatible adapter currently supplies model confirmation without accumulated usage.

`LLMPipeline._run_stage()` wraps stage execution in OpenTelemetry spans when a tracer is attached. See [service](../README.md), [providers](../providers/README.md), and [economics](../economics/README.md).

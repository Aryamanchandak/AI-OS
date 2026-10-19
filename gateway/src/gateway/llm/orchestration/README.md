# Chat request orchestration

This folder coordinates one chat request from validation to response. `pipeline.py` implements `LLMPipeline`; stages exchange data through `PipelineContext` in `context.py`. `__init__.py` exports the pipeline.

## Normal chat stages

| Order | File | Work performed |
| --- | --- | --- |
| 1 | `validation.py` | Requires prompt/messages and a positive token limit; rejects conflicting profile selectors and overly deep/large response schemas. |
| 2 | `profile_resolution.py` | Resolves a named chat profile to an exact provider/model pin. |
| 3 | `normalization.py` | Converts a plain prompt to messages, requires embedded image data and rejects image links, and estimates input tokens. |
| 4 | `routing.py` | Chooses explicit or ordered registry candidates, rejects missing/unavailable selections, and restricts image requests to vision-capable candidates. |
| 5 | `budget.py` | Reserves projected spending across the candidate set and raises HTTP 402 when admission fails. |
| 6 | `provider_call.py` | Calls providers under a concurrency semaphore, retries retryable provider errors, falls through to other providers when unpinned, and verifies returned profile models. |
| 7 | `structured_output.py` | Parses and validates JSON against the original schema; on failure makes one repair request and combines both results' token usage. Tool-call results bypass this validation. |
| 8 | `finalization.py` | Runs once from a `finally` boundary, calculates cost, reconciles/releases budget, and writes one call-ledger row (a failed write fails the call). |

The current provider-call defaults permit one retry and 32 concurrent calls within that stage. Explicit provider/profile selection prevents cross-provider failover. Routing uses registry order; there is no classifier or tier escalation here.

`LLMPipeline._run_stage()` wraps stage execution in OpenTelemetry spans when a tracer is attached. See [service](../README.md), [providers](../providers/README.md), and [economics](../economics/README.md).

# LLM domain

This folder exposes one service interface over several LLM vendors and local models. It handles chat, embeddings, profiles, usage attribution, budgets, pricing, and semantic response caching.

| File or folder | Responsibility |
| --- | --- |
| `service.py` | Implements the lifespan-owned `LLMService` facade, builds domain dependencies from configuration, wires chat stages, attaches cache/tracing, handles embeddings, and supplies provider/status diagnostics. |
| `models.py` | Defines Pydantic request/response contracts for chat, tools, structured output, embeddings, vision, batches, budgets, and preflight checks. |
| `__init__.py` | Exports `LLMService`. |
| [api](api/README.md) | Translates HTTP requests into service calls. |
| [orchestration](orchestration/README.md) | Implements chat stages and streaming control flow. |
| [providers](providers/README.md) | Translates common requests/results to and from vendor-specific APIs. |
| [profiles](profiles/README.md) | Loads named exact provider/model pins and embedding dimensions. |
| [economics](economics/README.md) | Computes prices, reserves budgets, and aggregates in-memory usage. |
| [cache](cache/README.md) | Persists and searches semantic response-cache entries. |

`LLMService.build()` reads `local_models.yaml`, `profiles.yaml`, `pricing.yaml`, and `budgets.yaml` from the configured directory. Startup separately constructs the semantic cache from `cache.yaml` and attaches it to the service.

Chat uses the orchestration pipeline. Embeddings instead iterate eligible providers directly, enforcing profile dimensions when specified, then recording usage and audit metadata. Internal cache embeddings use `record=False`. The current embedding path records zero monetary cost and does not perform chat-style budget admission.

Several models retain legacy fields and comments. Current behavior is determined by service/stage code: tier routing and cascade escalation are dormant, and `batch` affects accounting multipliers rather than submitting work to a vendor batch API. Capability diagnostics describe configured adapters; they are not live availability probes.

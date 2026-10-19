# LLM domain

This folder exposes one service interface over several LLM vendors and local models. It handles chat, embeddings, profiles, usage attribution, budgets, pricing, and provider prompt caching.

| File or folder | Responsibility |
| --- | --- |
| `service.py` | Implements the lifespan-owned `LLMService` facade, builds domain dependencies from configuration, wires chat stages, attaches tracing, handles embeddings, and supplies provider/status diagnostics. |
| `models.py` | Defines Pydantic request/response contracts for chat, tools, structured output, embeddings, budgets, and preflight checks. |
| `__init__.py` | Exports `LLMService`. |
| [api](api/README.md) | Translates HTTP requests into service calls. |
| [orchestration](orchestration/README.md) | Implements chat stages and finalization. |
| [providers](providers/README.md) | Translates common requests/results to and from vendor-specific APIs. |
| [profiles](profiles/README.md) | Loads named exact provider/model pins and embedding dimensions. |
| [economics](economics/README.md) | Computes prices, reserves budgets, and aggregates in-memory usage. |

`LLMService.build()` reads `local_models.yaml`, `profiles.yaml`, `pricing.yaml`, and `budgets.yaml` from the configured directory.

Chat uses the orchestration pipeline. Embeddings instead iterate eligible providers directly, enforcing profile dimensions when specified, then writing one call-ledger row. The current embedding path records zero monetary cost and does not perform chat-style budget admission.

Chat requests use explicit provider/model selection or exact profiles, with agent and session attribution. Unknown request options are rejected. Capability diagnostics describe configured adapters; they are not live availability probes.

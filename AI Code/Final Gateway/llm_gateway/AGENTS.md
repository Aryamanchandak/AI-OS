# Cleanup AGENTS.md

This file is the handoff note for future cleanup work in this repo. Treat it as
the current product direction unless the user says otherwise.

## Goal

Simplify `llm_gateway` into a small, useful personal LLM gateway.

Keep:

- `POST /v1/chat`
- `POST /v1/embed`
- Provider selection by explicit provider or configured order
- Optional model tool-call passthrough/normalization only if the harness uses it
- Generic structured output support for caller-provided Pydantic output models
- SQLite call logs
- Rate/cooldown/backoff awareness
- Embedding status/config endpoint
- A small Python client
- Lightweight client helpers for caller-provided Pydantic output models

Remove or reduce:

- Old V3 router/classifier history and docs
- `auto_route` compatibility leftovers
- Unused router-decision fields
- Web UI references
- Broad historical README material
- Any code path that exists only to preserve old V1/V2/V3 behavior and is not
  needed for the current gateway
- A gateway-owned shared contracts layer unless repeated cross-project contracts
  actually emerge
- Gateway-owned tool registration or tool execution

## Current Feature Meanings

### Tool Calls

Do not build a tool registry or tool execution system in this gateway. The MCP
server and harness own tools.

The only tool-related behavior that may belong here is optional provider
protocol normalization: if the harness sends tool schemas to the model, the
gateway can translate those schemas into each provider's format and normalize
the provider's returned `tool_calls` into one shape.

This is valuable because each provider has a different native tool/function
calling API, but it is also a likely failure point. Cleanup must treat tool-call
translation carefully: add focused tests for OpenAI, Anthropic, Gemini, and
Ollama request/response shapes before changing this area.

If the harness does not use model-emitted `tool_calls`, remove the tool fields
from the gateway entirely during cleanup.

### Structured Output

Structured output lets the caller pass `response_format` with a JSON schema. The
gateway asks the provider for schema-shaped JSON, validates the returned text,
and for non-streaming calls makes one repair attempt if validation fails.

Keep this feature, but simplify the implementation so streaming and
non-streaming share as much validation/repair code as practical. Add client
helpers that accept a caller-provided Pydantic model and return a validated
instance. Do not require shared gateway-owned contracts for this.

This is different from tool input contracts. Tool input contracts belong with
the MCP tools. Structured output is only for cases where the caller wants the
model's final response, decision, extraction, or classification as typed JSON.
If every typed model interaction happens through tool calls, structured output
can be reduced or removed later.

### Pydantic Contracts

Do not create a shared contracts package just for neatness. Right now the user's
Pydantic contracts mostly live at the tool/MCP level, which is the right place
for tool input schemas.

The useful gateway-side abstraction is generic:

- accept any caller-provided Pydantic output model
- turn it into `response_format`
- validate `result["parsed"]`
- return the typed model instance

Only add shared contracts later if the same output schemas are repeatedly used
across multiple projects.

### Logs

Logs are stored in SQLite through `db.py`. They track provider, model, status,
latency, token counts, prompt/response sizes, selected provider override,
attempts/skips, tool-call count, reasoning flag, call role, and embedding dim.

Keep this feature. It is useful for debugging provider behavior and cost/latency.

### Rate Awareness

Chat rate awareness lives in `router.py`; embeddings have separate state in
`embedders.py`. It prevents choosing providers that are in cooldown, backoff, or
over configured RPM/TPM/RPD limits.

Keep this feature, but rename/reframe `router.py` if the old "router" wording
keeps implying the deleted LLM classifier.

### Embeddings

Embeddings are a first-class call via `POST /v1/embed` and `LLM().embed(...)`.
The current behavior is Ollama first, Gemini fallback, fixed at 768 dimensions.
Do not casually change embedding model or dimension because existing vector
indexes become incompatible.

Keep this feature.

## Cleanup Priorities

1. Rewrite `README.md` around the current system only. Move or delete V3 history.
2. Remove `auto_route` from `client.py` and any stale docs/tests mentioning it.
3. Add lightweight structured-output helpers to `client.py` for arbitrary
   caller-provided Pydantic models.
4. Split the large `/v1/chat` handler in `main.py` into small helpers:
   request normalization, provider selection, provider call, structured
   validation/repair, logging, and response formatting.
5. Consider renaming `router.py` to something like `selection.py` or
   `provider_state.py` if doing so does not create unnecessary churn.
6. Split `providers.py` by backend if provider code continues to grow:
   OpenAI, Anthropic, Gemini, and Ollama adapters.
7. Remove unused schema/database fields only after checking migration impact on
   the existing `gateway_v7.db`.
8. Keep tests focused on the retained contract: provider registry, no chat
   runtime failover after a selected provider error, tool call normalization,
   structured output validation/repair, embeddings, and rate-state behavior.
   Tool-call tests should verify deterministic schema translation and returned
   call normalization for every provider adapter.

## Working Notes

- This directory is not currently a git repository.
- Avoid changing the embedding dimension or default embedding models as part of
  cleanup.
- Do not replace the useful logging/rate-awareness features with a stateless
  one-shot wrapper.
- Favor small behavior-preserving cleanup commits/patches over a rewrite.

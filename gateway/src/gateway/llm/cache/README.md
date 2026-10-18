# Persistent semantic response cache

All implementation is in `__init__.py`: `SemanticCacheConfig` parses settings, `CacheLookup` represents lookup outcomes, and `SemanticCache` stores and searches responses in SQLite.

A semantic cache reuses a response when a prompt's embedding is sufficiently similar to a stored embedding. It searches only entries in the same request namespace and caller scope. The namespace defaults to model/provider/profile/system/tools/response format/temperature; the default scope is tenant.

## Request flow

1. Check whether caching is enabled/requested and whether temperature, tools, and streaming satisfy eligibility settings.
2. Obtain an embedding through the injected asynchronous embedding callback.
3. Search unexpired matching SQLite rows using cosine similarity and return the best response above the threshold.
4. On a miss, let chat execute, then store its response using the lookup embedding to avoid embedding the prompt again.

Default settings are opt-in caching, a 0.95 similarity threshold, a one-hour TTL, a 5,000-entry limit, maximum temperature 0.3, and skipping tools and streaming. `cache.yaml` can change these. A zero TTL disables expiry filtering, and a zero maximum entry count disables capacity trimming.

Rows persist prompt text truncated to 8,000 characters, its hash, the embedding, response JSON, namespace/scope, timestamps, and hit count. This cache therefore contains request/response content, unlike the bounded trace metadata store. Statistics also persist. `purge()` can delete expired entries or everything; `healthcheck()` checks SQLite integrity and writability. Database errors propagate.

[LLMService](../README.md) constructs the cache; [orchestration](../orchestration/README.md) performs lookup before provider routing/budget admission and storage after normal response finalization. The incremental streaming path does not store newly generated responses.

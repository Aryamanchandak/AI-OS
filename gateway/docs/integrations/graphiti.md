# What Graphiti Needs from the Gateway

Oct 17, 2026 · Based on the `graphiti-core` 0.31.1 source code (downloaded and read, not installed).

Graphiti never talks to the gateway directly. A small adapter file (written later) translates
Graphiti's calls into gateway requests. This page lists what those requests need the gateway to do.

## Glossary

| Term | Plain meaning |
| --- | --- |
| Structured output | The model must reply with JSON that matches a given shape. |
| JSON schema | A description of that shape: field names, types, which are required. |
| Pydantic model | A Python class that defines a JSON shape. Graphiti turns it into a JSON schema. |
| Embedding | A list of numbers that represents a text's meaning; similar texts get similar numbers. |
| Reranker | A model that re-sorts search results by relevance. |

## 1. Chat with structured output

Graphiti uses chat calls to pull entities and facts out of text, check for duplicates, and write
entity summaries.

| Need | Detail |
| --- | --- |
| Messages | A list of `{role, content}`: one `system` and one `user` message. Content is plain text. |
| Structured output | Every call carries a JSON schema from a Pydantic model. The schemas are nested and have optional fields and `$defs` references. The reply must match the schema; a reply that doesn't should come back as an error, not as half-valid JSON. Graphiti also pastes the schema into the prompt. |
| Two model sizes | Each call is tagged `small` or `medium`. Small: dedup checks, attributes, summaries. Medium: entity and fact extraction. Both tags can map to the same model. |
| Temperature | Must be passed through exactly. Graphiti's default is 1 (very random); the adapter will send 0. |
| Max tokens | Must be passed through exactly. Graphiti's default is 16,384 per call. The model must support whatever value the adapter sends. |
| Reply contents | The JSON reply, plus which provider and exact model answered, and token counts for cost tracking. |

## 2. Embeddings

Graphiti cannot work without embeddings. It embeds:

- every entity name, to find possible duplicates ("IBM" vs "IBM Corp.")
- every fact sentence
- every search query

| Need | Detail |
| --- | --- |
| Single | One text in, one vector out. |
| Batch | A list of texts in, one vector per text out, in the same order. Graphiti calls this often. If the gateway takes only one text, the adapter loops, which means more calls. |
| Dimension | Any fixed size works; 768 is fine. On Neo4j, Graphiti compares vectors inside the query, with no fixed-size index. |
| One model per graph | Every vector in a graph must come from the same embedding model. Changing the model means rebuilding the graph. |
| Query vs document | Graphiti uses the same embed call for stored text and for search queries, so the adapter can't tell them apart. If the embedding model expects different prefixes for each (nomic-embed-text does), one prefix gets used for everything. |

## 3. Reranker: not needed

Graphiti can call a reranker during search, but search works without one (it merges result lists
with a plain formula called RRF). **If no reranker is passed in, Graphiti silently builds an OpenAI
one**, so the adapter will pass in one that does nothing. The gateway needs nothing for this.

## 4. Load and failure behaviour

| Behaviour | Detail |
| --- | --- |
| Parallel calls | Up to **20 at once** by default (the `SEMAPHORE_LIMIT` setting). The adapter can lower this. Either way the gateway sees several requests at the same time. |
| Graphiti's own retries | Graphiti retries each chat call up to **4 times**, waiting 5–120 seconds between tries. It retries on server errors (HTTP 5xx), rate limits, empty replies, and replies that aren't valid JSON. If the gateway also retries, the two stack up. |
| No retry | Errors in the 4xx range (except rate limits) are not retried. |
| Long calls | Extraction calls with big schemas can take a long time on slower models. |

## 5. Not needed by Graphiti

- An OpenAI-style `/v1/chat/completions` route: the adapter speaks the gateway's own format.
- Streaming, tool calling, image input.
- A rerank route.

## 6. Questions Graphiti raises for the gateway

1. Which model answers the `medium` and `small` calls? It must reliably return valid JSON for large, nested schemas.
2. Where should retries live: in Graphiti, in the gateway, or both?
3. How many calls at once can the gateway and its models handle?
4. Will the embed route accept a list of texts?

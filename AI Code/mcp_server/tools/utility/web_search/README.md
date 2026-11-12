# `web_search`  ·  group: `utility`

1 registered MCP tool(s). Everything for this tool lives in this folder.

### `web_search(query: 'str', max_results: 'int' = 5) -> 'list[dict]'`

Search the web through Brave Search.

Pass a concise search-engine query, not a chatty prompt. Use keywords plus context:
entity/topic, important nouns, timeframe, document/event, or metric. For broad
research, run multiple focused searches instead of one giant query.

The calling agent chooses `max_results` based on query complexity. Use fewer results
for simple factual lookups and more results for broad, comparative, ambiguous, or
multi-part research queries. This tool does not infer complexity itself; it validates
and caps the requested count.

Configuration:

- Set `BRAVE_SEARCH_API_KEY` in `/Users/aryamanchandak/Documents/AI Code/.env`.
- `AI_CODE_ROOT` can override the workspace root when this repo is moved.

Returns a list of result dictionaries:

```json
{
  "title": "...",
  "url": "https://...",
  "snippet": "...",
  "source": "brave"
}
```

**Files:** `tool.py`, `__init__.py` (registration).

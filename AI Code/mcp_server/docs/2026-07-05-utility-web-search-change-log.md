# 2026-07-05 Utility Web Search Change Log

This note records the approved one-tool change for `tools/utility/web_search/`.

## Decision

- Keep `web_search` as one MCP tool in its own folder.
- Use Brave Search as the only web search provider.
- Do not use Gemini Google Search for this tool.
- Do not use DuckDuckGo fallback for this tool.
- The calling agent chooses `max_results` based on query complexity.
- The tool validates and caps `max_results`; it does not infer complexity.

## Code Changes

### `tools/utility/web_search/tool.py`

- Replaced the Gemini REST call and DuckDuckGo fallback with Brave Search.
- Added AI Code root `.env` lookup for `BRAVE_SEARCH_API_KEY`.
- Kept `AI_CODE_ROOT` as an override for moved workspaces.
- Added blank-query validation.
- Raised the tool cap to 20 results.
- Normalized each result to:
  - `title`
  - `url`
  - `snippet`
  - `source`
- Changed usage logging from `duckduckgo` to `brave_search`.

### `tools/utility/web_search/README.md`

- Updated provider documentation to Brave Search.
- Documented that the agent, not the tool, chooses result count from query complexity.
- Documented required `BRAVE_SEARCH_API_KEY` configuration.

### AI Agent Decision Prompt

- Added an instruction in the Decision layer telling the agent to choose
  `web_search.max_results` based on query complexity.

## Verification

- Compiled `tools/utility/web_search/tool.py`.
- Compiled the AI Agent Decision prompt file.
- Ran an isolated mocked Brave response check for:
  - query trimming
  - `count` request parameter
  - API key header
  - result normalization
  - blank-query rejection

Full `import tools` is still blocked in this local sandbox by the known
knowledge-memory external import path issue.

# `search`  ·  group: `research`

5 registered MCP tool(s). Everything for this tool lives in this folder.

### `search_arxiv(query: 'str', category: 'Optional[str]' = None) -> 'str'`

Search arXiv preprints. Optional category filter e.g. 'cs.AI'.

### `search_google_books(query: 'str') -> 'str'`

Search for books via Gemini Google Search grounding.

### `search_semantic_scholar(query: 'str') -> 'str'`

Search Semantic Scholar for peer-reviewed academic papers.

### `search_web(query: 'str') -> 'str'`

Search the open web via Gemini Google Search grounding.

### `search_wikipedia(query: 'str') -> 'str'`

Search Wikipedia articles.

**Files:** `clients.py`, `contracts.py`, `tool.py`, `__init__.py` (registration).

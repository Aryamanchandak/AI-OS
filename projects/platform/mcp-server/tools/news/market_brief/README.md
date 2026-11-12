# `market_brief`  ·  group: `news`

5 registered MCP tool(s). Everything for this tool lives in this folder.

### `classify_news(articles: list[dict]) -> list[dict]`

Classify a list of news articles by relevance using Gemini. Input: article list from
fetch_news or matching schema. Returns only the articles classified as relevant.

### `cluster_stories(articles: list[dict]) -> list[dict]`

Cluster similar news stories and generate a one-sentence summary per cluster. Input:
relevant article list from classify_news or matching schema. Returns a list of cluster
dicts with fields: summary, sources (list of {name, url}).

### `fetch_news(category: str) -> list[dict]`

Fetch and deduplicate news articles from Google News RSS for a given category. Returns a
list of article dicts with fields: title, url, source, published_at.

### `generate_news_html(clusters: list[dict]) -> str`

Render a formatted HTML news brief from clustered stories. Input: cluster list from
cluster_stories or matching schema. Returns HTML string with bullet summaries and
clickable source chips.

### `run_news_pipeline(category: str) -> str`

Run the full news brief pipeline for a category. Steps: fetch → classify → cluster →
generate HTML. Returns a rendered HTML brief ready for display.

**Files:** `logic.py`, `__init__.py` (registration).

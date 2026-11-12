from tool_registry import register
from market_brief_mcp import (
    fetch_news,
    classify_news,
    cluster_stories,
    generate_news_html,
    run_news_pipeline,
)

for _fn in [fetch_news, classify_news, cluster_stories, generate_news_html, run_news_pipeline]:
    register(group="news")(_fn)

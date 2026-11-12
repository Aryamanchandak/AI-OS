"""
Module-level singletons. Import from search.py — never re-instantiate.
research_tools is bootstrapped once by mcp_server.py before groups are imported.
"""
from research_tools.sources.arxiv import ArXivClient
from research_tools.sources.gemini_web import GeminiWebClient
from research_tools.sources.google_books import GoogleBooksClient
from research_tools.sources.semantic_scholar import SemanticScholarClient
from research_tools.sources.wikipedia import WikipediaClient

arxiv = ArXivClient()
semantic_scholar = SemanticScholarClient()
wikipedia = WikipediaClient()
gemini_web = GeminiWebClient()
google_books = GoogleBooksClient()

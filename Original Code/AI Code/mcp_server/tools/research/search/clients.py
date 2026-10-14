"""
Module-level singletons. Import from search.py — never re-instantiate.
research_tools is bootstrapped once by mcp_server.py before groups are imported.
"""
from .sources.arxiv import ArXivClient
from .sources.gemini_web import GeminiWebClient
from .sources.google_books import GoogleBooksClient
from .sources.semantic_scholar import SemanticScholarClient
from .sources.wikipedia import WikipediaClient

arxiv = ArXivClient()
semantic_scholar = SemanticScholarClient()
wikipedia = WikipediaClient()
gemini_web = GeminiWebClient()
google_books = GoogleBooksClient()

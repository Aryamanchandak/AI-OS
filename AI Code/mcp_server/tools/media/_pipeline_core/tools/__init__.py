"""Scaffold tool handlers — pending MCP registration.

Moved to main server:
  - ingestion (RSS/YouTube listing, audio download) → backend/media/podcast_ingestion.py
  - delivery (Readwise Reader)                      → backend/media/podcast_deliver.py
"""

from tools.media._pipeline_core.tools.research import research_episode_claims
from tools.media._pipeline_core.tools.summarise import summarise_episode
from tools.media._pipeline_core.tools.transcribe import transcribe_episode

__all__ = [
    "research_episode_claims",
    "summarise_episode",
    "transcribe_episode",
]

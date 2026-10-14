"""
pipeline.py — Thin wrapper over core.orchestrator.process_episode.

Kept for backward compatibility with CLI and poller callers. All stage logic
lives in core/orchestrator.py and core/stages.py.
"""

from typing import Optional
from core.config import ShowConfig
from core.orchestrator import process_episode


def run_pipeline(
    url: str,
    show: Optional[ShowConfig] = None,
    profile: str = "hybrid",
    speakers_hint: str = "",
    show_name: str = "Manual entry",
    transcript_only: bool = False,
    skip_research: bool = False,
) -> dict:
    """Run the full pipeline on a URL. Returns a dict with the result."""
    return process_episode(
        url=url,
        show=show,
        profile=profile,
        speakers_hint=speakers_hint,
        show_name=show_name,
        transcript_only=transcript_only,
        skip_research=skip_research,
    )

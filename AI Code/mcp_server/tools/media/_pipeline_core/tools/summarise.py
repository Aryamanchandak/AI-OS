"""Future MCP summarisation tool boundary.

Summarisation is expected to run through LLM_Gateway with a model selected from
project configuration rather than hardcoded in tool logic.
"""

from tools.media._pipeline_core.contracts.episode import EpisodeToolRequest, EpisodeToolResponse


def summarise_episode(request: EpisodeToolRequest) -> EpisodeToolResponse:
    # Expected prompt inputs:
    # - Transcript text for the episode.
    # - Optionally, verified claims once the research step is wired.
    #
    # Model selection should come from config/models.yaml, or the eventual equivalent
    # config location defined by the project, so the summarisation model can change
    # without modifying this tool.
    #
    # Expected output is a structured markdown brief covering title, key takeaways,
    # claims, quotes, and speaker profile.
    return EpisodeToolResponse(
        episode_id=request.episode_id,
        metadata={
            "status": "scaffold",
            "message": (
                "Summarisation will be exposed here as an MCP tool after model "
                "selection moves into shared config."
            ),
            "artifact_paths": [],
        },
    )

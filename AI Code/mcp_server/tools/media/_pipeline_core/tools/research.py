"""Future MCP research tool boundary."""

from tools.media._pipeline_core.contracts.episode import EpisodeToolRequest, EpisodeToolResponse


def research_episode_claims(request: EpisodeToolRequest) -> EpisodeToolResponse:
    return EpisodeToolResponse(
        episode_id=request.episode_id,
        metadata={
            "status": "scaffold",
            "message": (
                "Research orchestration will be exposed here as an MCP tool "
                "when research-specific services are intentionally integrated."
            ),
            "artifact_paths": [],
        },
    )

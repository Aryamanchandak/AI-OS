"""Future MCP transcription tool boundary.

Transcription is expected to call LLM_Gateway's Deepgram integration once that
endpoint is exposed to this project.
"""

from tools.media._pipeline_core.contracts.episode import EpisodeToolRequest, EpisodeToolResponse


def transcribe_episode(request: EpisodeToolRequest) -> EpisodeToolResponse:
    # Expected contract:
    # - Input: a local audio file path for an episode artifact, such as mp3 or m4a.
    # - Output: an EpisodeToolResponse with artifact_paths pointing at the transcript file.
    #
    # Deepgram credentials already live in .env. Implementation is blocked on
    # LLM_Gateway exposing a Deepgram transcription endpoint that this tool can call.
    return EpisodeToolResponse(
        episode_id=request.episode_id,
        metadata={
            "status": "scaffold",
            "message": (
                "Transcription will be exposed here as an MCP tool after "
                "LLM_Gateway is wired to Deepgram."
            ),
            "artifact_paths": [],
        },
    )

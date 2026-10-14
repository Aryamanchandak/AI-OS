"""Placeholder workflow definitions for MCP automation."""

from __future__ import annotations

from pydantic import BaseModel, Field


class WorkflowStep(BaseModel):
    name: str
    owner: str
    notes: str = ""


class MCPWorkflow(BaseModel):
    """Coordinator definition for a pre-wired end-to-end pipeline.

    This model describes the anti-orchestration-burden pattern for podcast flows:
    callers eventually invoke one workflow entrypoint instead of manually chaining
    every MCP tool step themselves.
    """

    name: str
    steps: list[WorkflowStep] = Field(default_factory=list)


"""PODCAST_BRIEF_WORKFLOW is a partially implemented coordinator definition.

The ingest step is represented in the workflow today. The transcribe,
extract_claims, research, summarise, and deliver steps are still scaffolds and
need concrete wiring before this workflow can run end to end. A future
run_workflow(workflow: MCPWorkflow, context: dict) entrypoint can execute this
definition once those step integrations are live.
"""
PODCAST_BRIEF_WORKFLOW = MCPWorkflow(
    name="podcast_brief",
    steps=[
        WorkflowStep(name="ingest", owner="ingestion", notes="Podcast-specific"),
        WorkflowStep(name="transcribe", owner="mcp_tools"),  # TODO: Wire this to the future LLM_Gateway Deepgram transcription endpoint.
        WorkflowStep(name="extract_claims", owner="claims"),  # TODO: Wire this to ClaimExtractionService once the LLM-backed implementation exists.
        WorkflowStep(name="research", owner="external_research_adapter"),  # TODO: Wire this to the claim verification/research adapter for grounded web checks.
        WorkflowStep(name="summarise", owner="mcp_tools"),  # TODO: Wire this to the configurable LLM_Gateway summarisation tool and markdown brief output.
        WorkflowStep(name="deliver", owner="delivery"),  # TODO: Wire this to the final brief delivery/export step once output packaging is defined.
    ],
)

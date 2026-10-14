"""Shared Pydantic contracts used across podcast MCP modules."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ContentInput(BaseModel):
    """Generic source content that claims can be extracted from."""

    source_ref: str = ""
    content: str
    content_type: str = "text/plain"
    title: str = ""
    author: str = ""
    created_at: str = ""
    metadata: dict[str, str] = Field(default_factory=dict)


class ClaimRecord(BaseModel):
    claim_id: str
    source_ref: str = ""
    claim_type: str = ""
    quote: str = ""
    summary: str = ""
    speaker: str = ""
    timestamp: str = ""
    metadata: dict[str, str] = Field(default_factory=dict)


class ClaimExtractionRequest(BaseModel):
    """Extraction request for any information source, not just episodes."""

    input: ContentInput
    instructions: str = ""
    claim_types: list[str] = Field(default_factory=list)
    max_claims: int = 0


class ClaimExtractionBatch(BaseModel):
    batch_id: str = ""
    source_ref: str = ""
    claims: list[ClaimRecord] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


class VerificationSource(BaseModel):
    title: str = ""
    url: str = ""
    excerpt: str = ""
    published: str = ""
    metadata: dict[str, str] = Field(default_factory=dict)


class ClaimVerificationRequest(BaseModel):
    """Verification request for a generic list of claims."""

    claims: list[ClaimRecord] = Field(default_factory=list)
    context: str = ""
    instructions: str = ""
    metadata: dict[str, str] = Field(default_factory=dict)


class ClaimVerificationRecord(BaseModel):
    claim_id: str
    verdict: str = "pending"
    rationale: str = ""
    confidence: str = ""
    supporting_sources: list[VerificationSource] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


class ClaimVerificationBatch(BaseModel):
    run_id: str = ""
    items: list[ClaimVerificationRecord] = Field(default_factory=list)
    metadata: dict[str, str] = Field(default_factory=dict)


class EpisodeRef(BaseModel):
    episode_id: str
    source_url: str = ""


class ToolRunMetadata(BaseModel):
    status: str = "scaffold"
    message: str = ""
    artifact_paths: list[str] = Field(default_factory=list)


class IngestToolRequest(BaseModel):
    url: str
    show_name: str = ""
    profile: str = ""


class RSSIngestToolRequest(BaseModel):
    rss_url: str
    limit: int = 5


class YouTubeIngestToolRequest(BaseModel):
    channel_id: str
    limit: int = 5


class SourceEpisodeDownloadRequest(BaseModel):
    url: str
    title: str = ""


class IngestToolResponse(BaseModel):
    episode_id: str = ""
    title: str = ""
    metadata: ToolRunMetadata = Field(default_factory=ToolRunMetadata)


class AudioArtifactToolResponse(BaseModel):
    episode_id: str
    title: str
    audio_path: str
    metadata: ToolRunMetadata = Field(default_factory=ToolRunMetadata)


class EpisodeListItem(BaseModel):
    episode_id: str
    title: str
    source_url: str
    published: str = ""
    description: str = ""
    platform: str = ""


class EpisodeListToolResponse(BaseModel):
    episodes: list[EpisodeListItem] = Field(default_factory=list)
    metadata: ToolRunMetadata = Field(default_factory=ToolRunMetadata)


class EpisodeToolRequest(BaseModel):
    episode_id: str


class EpisodeToolResponse(BaseModel):
    episode_id: str
    metadata: ToolRunMetadata = Field(default_factory=ToolRunMetadata)


class EpisodeRow(BaseModel):
    episode_id: str
    show_name: str = ""
    title: str = ""
    source_url: str = ""
    profile: str = ""
    status: str = "pending"


class RunRow(BaseModel):
    episode_id: str
    stage: str
    status: str
    message: str = ""


class ArtifactRow(BaseModel):
    episode_id: str
    artifact_type: str
    artifact_path: str


class ClaimRow(BaseModel):
    claim_id: str
    episode_id: str
    claim_type: str = ""
    quote: str = ""
    summary: str = ""


class ToolExecutionRow(BaseModel):
    tool_name: str
    episode_id: str = ""
    status: str
    message: str = ""

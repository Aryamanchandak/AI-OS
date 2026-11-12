"""
models.py — Shared Pydantic v2 models for podcast-brief.

All domain types live here so every module can import from one place.
No runtime dependencies beyond pydantic and stdlib.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ─── Ingestion ────────────────────────────────────────────────────────────────

class EpisodeInfo(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    id: str
    title: str
    source_url: str
    audio_path: Path


class RSSEpisode(BaseModel):
    guid: str
    title: str
    audio_url: str
    published: str
    description: str


# ─── Transcription ────────────────────────────────────────────────────────────

class Segment(BaseModel):
    speaker: str
    start: float
    end: float
    text: str

    @property
    def timestamp(self) -> str:
        total = int(self.start)
        h = total // 3600
        m = (total % 3600) // 60
        s = total % 60
        return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


class Transcript(BaseModel):
    episode_id: str
    segments: list[Segment]
    speakers: list[str]
    full_text: str

    def to_prompt_format(self, max_chars: int = 180_000) -> str:
        lines = [f"[{s.speaker} — {s.timestamp}] {s.text}" for s in self.segments]
        full = "\n".join(lines)
        if len(full) <= max_chars:
            return full
        keep_start = int(max_chars * 0.6)
        keep_end = int(max_chars * 0.2)
        return (
            full[:keep_start]
            + "\n\n[... middle section truncated for length — full transcript saved to disk ...]\n\n"
            + full[-keep_end:]
        )

    @property
    def duration_seconds(self) -> float:
        return self.segments[-1].end if self.segments else 0.0

    def save(self, path: Path) -> None:
        data = {
            "episode_id": self.episode_id,
            "speakers": self.speakers,
            "full_text": self.full_text,
            "segments": [s.model_dump() for s in self.segments],
        }
        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path: Path) -> "Transcript":
        data = json.loads(path.read_text())
        segments = [Segment(**s) for s in data["segments"]]
        return cls(
            episode_id=data["episode_id"],
            segments=segments,
            speakers=data["speakers"],
            full_text=data["full_text"],
        )


# ─── Extraction ───────────────────────────────────────────────────────────────

class Claim(BaseModel):
    type: str
    speaker: str
    timestamp: str
    quote: str
    summary: str
    search_query: str


class ExtractionResult(BaseModel):
    episode_id: str
    profile: str
    claims: list[Claim]
    episode_description: str

    def save(self, path: Path) -> None:
        path.write_text(self.model_dump_json(indent=2))

    @classmethod
    def load(cls, path: Path) -> "ExtractionResult":
        return cls.model_validate_json(path.read_text())


# ─── Research ─────────────────────────────────────────────────────────────────

class LogicalSource(BaseModel):
    title: str
    authors: list[str] = Field(default_factory=list)
    published: Optional[str] = None
    url: Optional[str] = None
    raw_excerpt: str = ""


class SurfacedItemWithClaim(BaseModel):
    claim: Claim
    triage_correctness: str
    triage_effort: str
    triage_confidence: float
    triage_rationale: str
    essay_path: Optional[str] = None
    logical_sources: list[LogicalSource] = Field(default_factory=list)


# ─── Stage result types (returned by core/stages.py) ─────────────────────────

class IngestResult(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    episode_id: str
    title: str
    audio_path: Path
    audio_size_mb: float
    already_processed: bool = False


class TranscribeResult(BaseModel):
    episode_id: str
    duration_seconds: float
    segment_count: int
    speakers: list[str]
    transcript_path: str


class ExtractResult(BaseModel):
    episode_id: str
    claim_count: int
    episode_description: str
    extraction_path: str
    claims_by_type: dict[str, int] = Field(default_factory=dict)


class ResearchResult(BaseModel):
    episode_id: str
    surfaced_count: int
    deep_count: int
    light_count: int
    research_run_id: str
    research_path: str


class SynthesizeResult(BaseModel):
    episode_id: str
    char_count: int
    brief_path: str


class DeliverResult(BaseModel):
    episode_id: str
    reader_url: str
    brief_path: str
    transcript_only: bool = False

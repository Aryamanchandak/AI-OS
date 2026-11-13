"""Typed contracts every layer in the S7 agent talks in.

One small file, read top-to-bottom. Every other module imports from here, so
the boundary between layers is a Pydantic model rather than a free-form dict.

Session 7 adds one optional field on `MemoryItem`: `embedding`. Items of
kind `fact`, `preference`, and `tool_outcome` carry a vector embedding
written by Memory at insert time. The embedding underlies FAISS vector
search. Items of kind `scratchpad` are run-scoped and skip embedding.

`expires_at` (optional) marks an item stale after a specific point in time.
`None` means durable (the default, unchanged behaviour). Set by Memory's
classifier at write time; read paths hard-filter expired items out of
results.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def new_id(prefix: str = "id") -> str:
    return f"{prefix}:{uuid4().hex[:8]}"


# ── Memory ──────────────────────────────────────────────────────────────────

MemoryKind = Literal["fact", "preference", "tool_outcome", "scratchpad"]


class MemoryItem(BaseModel):
    """One record in memory. Reads happen by vector similarity first
    (FAISS over the `embedding` field) with keyword overlap as the
    fallback when vector search returns nothing. Bytes never live here;
    they live in the artifact store."""

    id: str
    kind: MemoryKind
    keywords: list[str] = Field(default_factory=list)
    descriptor: str                              # one short human-readable line
    value: dict = Field(default_factory=dict)    # structured payload
    artifact_id: str | None = None
    embedding: list[float] | None = None         # set by Memory at write time
    source: str
    run_id: str
    goal_id: str | None = None
    confidence: float = 1.0
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime | None = None           # None = durable; set by the classifier


# ── Artifacts ───────────────────────────────────────────────────────────────

class Artifact(BaseModel):
    id: str
    content_type: str
    size_bytes: int
    source: str
    descriptor: str
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ── Blocks, Goals & Results ─────────────────────────────────────────────────

class Goal(BaseModel):
    id: str
    text: str
    done: bool = False
    needs_artifact_ids: list[str] = Field(default_factory=list)


class Block(BaseModel):
    round: int
    goals: list[Goal]
    rationale: str = ""


class ToolCall(BaseModel):
    name: str
    arguments: dict


class GoalResult(BaseModel):
    goal_id: str
    kind: Literal["tool", "synthesis", "capability_gap"]
    tool_call: ToolCall | None = None
    output_descriptor: str
    artifact_id: str | None = None
    status: Literal["ok", "error", "capability_gap"]
    message: str = ""


class ReviewFinding(BaseModel):
    check: Literal[
        "unaddressed",
        "error",
        "capability_gap",
        "discovery",
        "insufficient",
        "uncovered",
    ]
    goal_id: str | None = None
    detail: str
    proposed_goal_text: str | None = None


class Review(BaseModel):
    finished: bool
    findings: list[ReviewFinding] = Field(default_factory=list)
    next_block: Block | None = None

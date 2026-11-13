"""Typed contracts every layer talks in.

One small file, read top to bottom. Every other module imports from here, so
the boundary between layers is a Pydantic model and never a free-form dict.
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
    """One record in memory, found by keyword overlap. Bytes never live
    here; they live in the artifact store."""

    id: str
    kind: MemoryKind
    keywords: list[str] = Field(default_factory=list)
    descriptor: str                              # one short human-readable line
    value: dict = Field(default_factory=dict)    # structured payload
    artifact_id: str | None = None
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

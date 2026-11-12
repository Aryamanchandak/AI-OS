"""Pydantic data contracts for source records."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class SourceRecord(BaseModel):
    source: str
    external_id: str
    title: str
    authors: list[str] = Field(default_factory=list)
    published: Optional[str] = None  # ISO date or year string
    url: Optional[str] = None
    raw_excerpt: str = ""
    source_tier: str = ""
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

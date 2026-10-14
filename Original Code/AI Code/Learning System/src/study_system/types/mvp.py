"""Small MVP domain types shared by core, storage, MCP, and automation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class ConceptSummary:
    id: str
    name: str
    domain: str = ""
    summary: str = ""
    source_version: str | None = None


@dataclass(frozen=True)
class RetrievedContext:
    concept: ConceptSummary
    kg_context: dict[str, Any] = field(default_factory=dict)
    vector_context: list[dict[str, Any]] = field(default_factory=list)

    @property
    def source_refs(self) -> list[dict[str, Any]]:
        refs: list[dict[str, Any]] = [
            {
                "type": "kg_concept",
                "id": self.concept.id,
                "version": self.concept.source_version,
            }
        ]
        for item in self.vector_context:
            refs.append(
                {
                    "type": "vector_hit",
                    "id": item.get("id") or item.get("source_id") or "",
                    "version": item.get("version") or item.get("hash"),
                }
            )
        return refs


@dataclass(frozen=True)
class GeneratedCard:
    id: str
    concept_id: str
    front: str
    back: str
    card_type: str
    source_refs: list[dict[str, Any]]
    source_version: str | None
    model: str
    prompt_version: str
    created_at: datetime = field(default_factory=datetime.utcnow)

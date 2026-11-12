"""Public read contracts used by the study core.

Adapters may call MCP tools, package APIs, SQL drivers, or local JSON fixtures,
but the core only depends on these small read-only protocols.
"""

from __future__ import annotations

from typing import Any, Protocol

from study_system.types.mvp import ConceptSummary


class FinalKGRepository(Protocol):
    def list_concepts(self, limit: int | None = None) -> list[ConceptSummary]:
        """Return final, user-visible concepts in stable deterministic order."""

    def get_concept(self, concept_id: str) -> ConceptSummary | None:
        """Return one final KG concept by ID."""

    def neighborhood(self, concept_id: str, depth: int = 1) -> dict[str, Any]:
        """Return read-only neighborhood/context for a concept."""

    def search(self, text: str, limit: int = 10) -> list[ConceptSummary]:
        """Search the final KG surface."""


class VectorRepository(Protocol):
    def search(
        self, query: str, filters: dict[str, Any] | None = None, limit: int = 5
    ) -> list[dict[str, Any]]:
        """Search the final vector DB surface."""

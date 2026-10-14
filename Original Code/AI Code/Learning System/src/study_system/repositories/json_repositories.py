"""JSON-backed read adapters for local MVP/dev runs and tests.

These adapters implement the final KG/vector contracts without importing
private ingestion code. They are intentionally simple and deterministic.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from study_system.repositories.interfaces import FinalKGRepository, VectorRepository
from study_system.types.mvp import ConceptSummary


class JsonKGRepository(FinalKGRepository):
    """Read concepts from a JSON file.

    Accepted shape:
    {
      "concepts": [
        {"id": "c1", "name": "Duration", "domain": "Fixed Income",
         "summary": "...", "source_version": "hash"}
      ],
      "neighborhoods": {"c1": {"related": [...]}}
    }
    """

    def __init__(self, path: Path) -> None:
        if not path.exists():
            raise FileNotFoundError(f"KG concepts JSON not found: {path}")
        raw = json.loads(path.read_text(encoding="utf-8"))
        self._concepts = [
            ConceptSummary(
                id=str(item["id"]),
                name=str(item.get("name") or item.get("canonical_name") or item["id"]),
                domain=str(item.get("domain") or ""),
                summary=str(item.get("summary") or ""),
                source_version=item.get("source_version") or item.get("version") or item.get("hash"),
            )
            for item in raw.get("concepts", [])
        ]
        self._neighborhoods = dict(raw.get("neighborhoods", {}))

    def list_concepts(self, limit: int | None = None) -> list[ConceptSummary]:
        concepts = sorted(self._concepts, key=lambda c: (c.domain, c.name, c.id))
        return concepts[:limit] if limit is not None else concepts

    def get_concept(self, concept_id: str) -> ConceptSummary | None:
        return next((c for c in self._concepts if c.id == concept_id), None)

    def neighborhood(self, concept_id: str, depth: int = 1) -> dict[str, Any]:
        return {"depth": depth, **dict(self._neighborhoods.get(concept_id, {}))}

    def search(self, text: str, limit: int = 10) -> list[ConceptSummary]:
        needle = text.lower()
        matches = [
            c
            for c in self.list_concepts()
            if needle in c.name.lower() or needle in c.summary.lower() or needle in c.domain.lower()
        ]
        return matches[:limit]


class EmptyKGRepository(FinalKGRepository):
    """Graceful stand-in when no final-KG source is configured yet.

    Lets MCP tools that don't need concept lookups (due cards, ratings,
    overrides, progress) work before a real KG/vector adapter exists,
    instead of failing MCP-server startup entirely.
    """

    def list_concepts(self, limit: int | None = None) -> list[ConceptSummary]:
        return []

    def get_concept(self, concept_id: str) -> ConceptSummary | None:
        return None

    def neighborhood(self, concept_id: str, depth: int = 1) -> dict[str, Any]:
        return {"depth": depth}

    def search(self, text: str, limit: int = 10) -> list[ConceptSummary]:
        return []


class JsonVectorRepository(VectorRepository):
    """Read vector-like snippets from JSON and rank by substring match."""

    def __init__(self, path: Path | None = None) -> None:
        self._items: list[dict[str, Any]] = []
        if path is None:
            return
        if not path.exists():
            raise FileNotFoundError(f"Vector snippets JSON not found: {path}")
        raw = json.loads(path.read_text(encoding="utf-8"))
        self._items = list(raw.get("items", raw if isinstance(raw, list) else []))

    def search(
        self, query: str, filters: dict[str, Any] | None = None, limit: int = 5
    ) -> list[dict[str, Any]]:
        filters = filters or {}
        query_terms = {part.lower() for part in query.split() if part.strip()}

        def allowed(item: dict[str, Any]) -> bool:
            return all(item.get(key) == value for key, value in filters.items())

        def score(item: dict[str, Any]) -> int:
            haystack = " ".join(str(item.get(k, "")) for k in ("text", "title", "concept_id")).lower()
            return sum(1 for term in query_terms if term in haystack)

        ranked = sorted(
            [item for item in self._items if allowed(item)],
            key=lambda item: (-score(item), str(item.get("id", ""))),
        )
        return ranked[:limit]

"""SourceClient ABC and shared error types."""
from __future__ import annotations

from abc import ABC, abstractmethod

from ..contracts import SourceRecord


class SourceUnavailableError(Exception):
    """Raised when a source client cannot operate (missing API key, service down)."""


class SourceClient(ABC):
    name: str
    source_tier: str

    @abstractmethod
    async def search(self, query: str, **kwargs) -> list[SourceRecord]:
        """Search for `query` and return a list of SourceRecords."""

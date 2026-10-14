"""Result models retained by the archived vector store."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, repr=False)
class SimilarityHit:
    """A single vector-similarity result."""

    id: str
    score: float
    metadata: dict[str, Any]
    text: str = ""

    def __repr__(self) -> str:
        preview = (self.text[:60] + "…") if len(self.text) > 60 else self.text
        return f"SimilarityHit(id={self.id!r}, score={self.score:.3f}, text={preview!r})"

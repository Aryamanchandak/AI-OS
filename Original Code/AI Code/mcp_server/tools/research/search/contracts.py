from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class SourceRecord:
    title: str
    url: str | None = None
    source: str | None = None
    snippet: str | None = None
    authors: list[str] = field(default_factory=list)
    published: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def model_dump(self, mode: str = "python") -> dict[str, Any]:
        return asdict(self)


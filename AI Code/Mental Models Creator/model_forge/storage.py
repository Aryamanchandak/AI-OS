from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import tempfile

from .schema import CausalModel


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-") or "model"


class FlatFileLibrary:
    def __init__(self, root: str | Path | None = None) -> None:
        configured = root or os.getenv("MODEL_FORGE_LIBRARY", "model-library")
        self.root = Path(configured).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _json_path(self, model: CausalModel) -> Path:
        return self.root / f"{_slug(model.name)}--{model.id}.json"

    def save(self, model: CausalModel) -> CausalModel:
        model.validate()
        model.updated_at = datetime.now(timezone.utc).isoformat()
        destination = self._json_path(model)
        payload = json.dumps(model.to_dict(), indent=2, ensure_ascii=False) + "\n"
        fd, temporary = tempfile.mkstemp(prefix=".forge-", dir=self.root, text=True)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
            os.replace(temporary, destination)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        destination.with_suffix(".md").write_text(render_markdown(model), encoding="utf-8")
        return model

    def list(self) -> list[CausalModel]:
        models: list[CausalModel] = []
        for path in self.root.glob("*.json"):
            try:
                models.append(CausalModel.from_dict(json.loads(path.read_text(encoding="utf-8"))))
            except (ValueError, TypeError, json.JSONDecodeError):
                continue
        return sorted(models, key=lambda item: item.updated_at, reverse=True)

    def get(self, identifier: str) -> CausalModel:
        matches = [m for m in self.list() if m.id == identifier or _slug(m.name) == _slug(identifier)]
        if not matches:
            raise KeyError(f"No model found for {identifier!r}")
        if len(matches) > 1 and all(m.id != identifier for m in matches):
            raise KeyError(f"Model name {identifier!r} is ambiguous; use its id")
        return next((m for m in matches if m.id == identifier), matches[0])


def render_markdown(model: CausalModel) -> str:
    def bullets(values: list[str]) -> str:
        return "\n".join(f"- {value}" for value in values) or "- None recorded"

    edge_rows = "\n".join(
        f"| {e.cause} | {e.effect} | {e.sign} | {e.magnitude} | {e.lag} | {e.support} |"
        for e in model.edges
    ) or "| — | — | — | — | — | — |"
    predictions = "\n".join(
        f"- [{p.status}] {p.due_date} ({p.confidence:.0%}): {p.statement}"
        for p in model.predictions
    ) or "- None — model is not yet admissible"
    return f"""# {model.name}

**Scope:** {model.scope}  
**Earned confidence:** {model.confidence:.0%}  
**Schema:** `{model.schema_version}`

## Boundary conditions
{bullets(model.boundary_conditions)}

## Compressions
- 40 words: {model.compressions.get('40', 'Not run')}
- 15 words: {model.compressions.get('15', 'Not run')}

## Entities
{bullets([f'{e.name} (`{e.namespace}`)' for e in model.entities])}

## Causal edges
| Cause | Effect | Sign | Magnitude | Lag | Support |
|---|---|---|---|---|---|
{edge_rows}

## Invariants
{bullets(model.invariants)}

## Predictions
{predictions}

## Anomalies
{bullets(model.anomalies)}
"""

from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Any

from .adapters import (
    LocalDecisionTracker, LocalMirfish, LocalSteelman,
    RemoteDecisionTracker, RemoteMirfish, RemoteSteelman,
)
from .ai import ForgeEngine, choose_engine
from .collision import find_collisions
from .honing import Honer
from .ingest import Ingested, from_path, from_text, from_upload, from_url, live_news
from .schema import CausalModel
from .storage import FlatFileLibrary


class ModelForge:
    def __init__(self, library: str | Path | None = None, engine: ForgeEngine | None = None) -> None:
        self.library = FlatFileLibrary(library)
        self.engine = engine or choose_engine()
        self.honer = Honer(self.engine)
        token = os.getenv("MODEL_FORGE_ADAPTER_TOKEN", "")
        self.steelman = RemoteSteelman(os.environ["STEELMAN_ENDPOINT"], token) if os.getenv("STEELMAN_ENDPOINT") else LocalSteelman()
        self.mirfish = RemoteMirfish(os.environ["MIRFISH_ENDPOINT"], token) if os.getenv("MIRFISH_ENDPOINT") else LocalMirfish()
        self.decision_tracker = RemoteDecisionTracker(os.environ["DECISION_TRACKER_ENDPOINT"], token) if os.getenv("DECISION_TRACKER_ENDPOINT") else LocalDecisionTracker()

    def forge_text(self, text: str, name: str = "", predictions: int = 3, domain: str = "") -> dict[str, Any]:
        return self._forge(from_text(text, title=name), name, predictions, domain)

    def forge_path(self, path: str | Path, name: str = "", predictions: int = 3, domain: str = "") -> dict[str, Any]:
        return self._forge(from_path(path), name, predictions, domain)

    def forge_url(self, url: str, name: str = "", predictions: int = 3, domain: str = "") -> dict[str, Any]:
        return self._forge(from_url(url), name, predictions, domain)

    def forge_upload(self, filename: str, encoded: str, name: str = "", predictions: int = 3, domain: str = "") -> dict[str, Any]:
        try:
            data = base64.b64decode(encoded, validate=True)
        except ValueError as exc:
            raise ValueError("Upload content was not valid base64") from exc
        return self._forge(from_upload(filename, data), name, predictions, domain)

    def forge_news(self, query: str, name: str = "", predictions: int = 3, domain: str = "") -> dict[str, Any]:
        return self._forge(live_news(query), name or f"News model: {query}", predictions, domain)

    def _forge(self, ingested: Ingested, name: str, predictions: int, domain: str) -> dict[str, Any]:
        model = self.engine.construct(ingested.text, ingested.source, name or None)
        result = self.honer.run(model, predictions, domain)
        if result.rejected:
            return {"accepted": False, "reasons": result.reasons, "model": model.to_dict(), "collisions": []}
        model.validate(require_predictions=True)
        collisions = find_collisions(model, self.library.list())
        self.library.save(model)
        return {"accepted": True, "reasons": [], "model": model.to_dict(), "collisions": [item.to_dict() for item in collisions]}

    def list_models(self) -> list[dict[str, Any]]:
        return [model.to_dict() for model in self.library.list()]

    def get(self, identifier: str) -> CausalModel:
        return self.library.get(identifier)

    def collisions(self, identifier: str) -> list[dict[str, Any]]:
        model = self.get(identifier)
        return [item.to_dict() for item in find_collisions(model, self.library.list())]

    def hone(self, identifier: str, predictions: int = 3, domain: str = "") -> dict[str, Any]:
        model = self.get(identifier)
        model.revision += 1
        result = self.honer.run(model, predictions, domain)
        if not result.rejected:
            self.library.save(model)
        return {"accepted": not result.rejected, "reasons": result.reasons, "model": model.to_dict()}

    def harden(self, identifier: str, edge_id: str) -> dict[str, Any]:
        model = self.get(identifier)
        result = self.steelman.harden(model, edge_id)
        model.revision += 1
        self.library.save(model)
        return result

    def run_forward(self, identifier: str, observations: str) -> dict[str, Any]:
        model = self.get(identifier)
        result = self.mirfish.run_forward(model, observations)
        model.revision += 1
        self.library.save(model)
        return result

    def run_news(self, identifier: str, query: str, limit: int = 10) -> dict[str, Any]:
        news = live_news(query, limit)
        model = self.get(identifier)
        result = self.mirfish.run_forward(model, news.text)
        result["payload"]["source"] = news.source.__dict__ if hasattr(news.source, "__dict__") else {
            "id": news.source.id, "kind": news.source.kind, "locator": news.source.locator,
            "title": news.source.title, "captured_at": news.source.captured_at,
        }
        model.revision += 1
        self.library.save(model)
        return result

    def score(self, identifier: str, prediction_id: str, outcome: float, note: str = "") -> dict[str, Any]:
        model = self.get(identifier)
        result = self.decision_tracker.score(model, prediction_id, outcome, note)
        model.revision += 1
        self.library.save(model)
        return result

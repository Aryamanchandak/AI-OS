from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, timedelta
import json
import os
import re
from typing import Any
from urllib import error, request

from .schema import CausalModel, Edge, Entity, Prediction, Source


class ForgeEngine(ABC):
    @abstractmethod
    def construct(self, text: str, source: Source, name: str | None = None) -> CausalModel:
        raise NotImplementedError

    def complete_json(self, instruction: str, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError


class LocalEngine(ForgeEngine):
    """Deterministic, deliberately conservative fallback for offline work and tests."""

    CAUSAL = re.compile(
        r"(?P<cause>[A-Za-z][^.!?;]{1,70}?)\s+"
        r"(?P<verb>increases?|raises?|improves?|drives?|causes?|reduces?|lowers?|"
        r"decreases?|prevents?|constrains?|leads? to|results? in)\s+"
        r"(?P<effect>[^.!?;]{2,80})",
        re.IGNORECASE,
    )
    NEGATIVE = {"reduce", "reduces", "lower", "lowers", "decrease", "decreases", "prevent", "prevents", "constrain", "constrains"}

    def construct(self, text: str, source: Source, name: str | None = None) -> CausalModel:
        clean = " ".join(text.split())
        if not clean:
            raise ValueError("Source contained no readable text")
        edges: list[Edge] = []
        entities: dict[str, Entity] = {}
        for match in self.CAUSAL.finditer(clean):
            cause = self._trim(match.group("cause"))
            effect = self._trim(match.group("effect"))
            if len(cause.split()) > 10:
                cause = " ".join(cause.split()[-8:])
            sign = "negative" if match.group("verb").casefold() in self.NEGATIVE else "positive"
            for value in (cause, effect):
                entity = Entity(value)
                entities.setdefault(entity.namespace, entity)
            edges.append(Edge(
                cause=entities[Entity(cause).namespace].namespace,
                effect=entities[Entity(effect).namespace].namespace,
                sign=sign,
                magnitude="unspecified",
                lag="unspecified",
                claim=match.group(0).strip(),
                support="stated",
                source_ids=[source.id],
                confidence=0.65,
            ))
        if not edges:
            phrases = [self._trim(p) for p in re.split(r"[.!?]", clean) if len(p.split()) >= 4]
            if len(phrases) >= 2:
                cause, effect = phrases[0][:60], phrases[1][:60]
                a, b = Entity(cause), Entity(effect)
                entities = {a.namespace: a, b.namespace: b}
                edges.append(Edge(
                    cause=a.namespace, effect=b.namespace, claim="Possible relationship inferred from adjacency",
                    support="unsupported", source_ids=[], confidence=0.25,
                ))
        title = name or source.title or self._title(clean)
        model = CausalModel(
            name=title,
            scope=f"Causal structure extracted from {source.kind} source: {source.locator}",
            boundary_conditions=["Applies only within the source's stated or implied context", "Breaks when the identified causal links do not hold"],
            entities=list(entities.values()),
            edges=edges,
            invariants=["Every accepted causal claim must connect two named entities"],
            provenance={source.id: source},
        )
        return model

    @staticmethod
    def _trim(value: str) -> str:
        return re.sub(r"^(and|but|because|when|if|then)\s+", "", value.strip(" ,:-"), flags=re.I)

    @staticmethod
    def _title(text: str) -> str:
        words = re.findall(r"[A-Za-z0-9'-]+", text)[:7]
        return " ".join(words).title() or "Untitled model"


class OpenAIEngine(ForgeEngine):
    endpoint = "https://api.openai.com/v1/responses"

    def __init__(self, api_key: str, model: str | None = None) -> None:
        self.api_key = api_key
        self.model = model or os.getenv("MODEL_FORGE_OPENAI_MODEL", "gpt-5-mini")

    def complete_json(self, instruction: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = {
            "model": self.model,
            "instructions": instruction + " Return only a valid JSON object.",
            "input": json.dumps(payload, ensure_ascii=False),
            "text": {"format": {"type": "json_object"}},
        }
        req = request.Request(
            self.endpoint,
            data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        try:
            with request.urlopen(req, timeout=120) as response:
                result = json.load(response)
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"OpenAI request failed ({exc.code}): {detail}") from exc
        output = result.get("output_text")
        if not output:
            for item in result.get("output", []):
                for content in item.get("content", []):
                    if content.get("type") == "output_text":
                        output = content.get("text")
        if not output:
            raise RuntimeError("OpenAI response contained no output text")
        return json.loads(output)

    def construct(self, text: str, source: Source, name: str | None = None) -> CausalModel:
        instruction = """Extract a causal mental model, not a summary. Identify entities and explicit or inferred
causal edges. Each edge needs cause/effect entity namespace keys, sign (positive/negative/mixed/unknown),
magnitude, lag, claim, support (stated/inferred/unsupported), and confidence. Preserve unsupported hypotheses.
Return keys: name, scope, boundary_conditions, entities, edges, invariants. Entity keys: name, kind, namespace, aliases."""
        data = self.complete_json(instruction, {"suggested_name": name, "source": text[:100000]})
        model = CausalModel(
            name=name or data.get("name") or source.title or "Untitled model",
            scope=data.get("scope") or "Scope not established",
            boundary_conditions=data.get("boundary_conditions", []),
            entities=[Entity(**item) for item in data.get("entities", [])],
            invariants=data.get("invariants", []),
            provenance={source.id: source},
        )
        valid_keys = {entity.namespace for entity in model.entities}
        for item in data.get("edges", []):
            item = dict(item)
            item["source_ids"] = [source.id] if item.get("support") != "unsupported" else []
            if item.get("cause") in valid_keys and item.get("effect") in valid_keys:
                model.edges.append(Edge(**item))
        return model


def choose_engine(mode: str | None = None) -> ForgeEngine:
    selected = (mode or os.getenv("MODEL_FORGE_MODE", "auto")).casefold()
    key = os.getenv("OPENAI_API_KEY")
    if selected == "openai" and not key:
        raise RuntimeError("MODEL_FORGE_MODE=openai requires OPENAI_API_KEY")
    if selected == "openai" or (selected == "auto" and key):
        return OpenAIEngine(key or "")
    return LocalEngine()


def local_predictions(model: CausalModel, count: int) -> list[Prediction]:
    due = (date.today() + timedelta(days=90)).isoformat()
    predictions: list[Prediction] = []
    names = {entity.namespace: entity.name for entity in model.entities}
    if not model.edges:
        return []
    horizons = (30, 90, 180, 365)
    for index in range(count):
        edge = model.edges[index % len(model.edges)]
        due = (date.today() + timedelta(days=horizons[index % len(horizons)])).isoformat()
        cause, effect = names.get(edge.cause, edge.cause), names.get(edge.effect, edge.effect)
        direction = "increase" if edge.sign == "positive" else "decrease" if edge.sign == "negative" else "change"
        condition = "materially rises" if index < len(model.edges) else f"remains elevated for {horizons[index % len(horizons)]} days"
        predictions.append(Prediction(
            statement=f"If {cause} {condition}, {effect} will {direction} by {due}.",
            due_date=due,
            confidence=edge.confidence,
            edge_ids=[edge.id],
            observable=f"Measure the direction of change in {effect} after a change in {cause}.",
        ))
    return predictions

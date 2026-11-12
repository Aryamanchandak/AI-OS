from __future__ import annotations

from abc import ABC, abstractmethod
import json
import os

from steelman.graph import build_deterministic_graph
from steelman.models import ArgumentGraph, ClaimCard


class ConstructionProvider(ABC):
    name: str

    @abstractmethod
    def construct(self, card: ClaimCard) -> ArgumentGraph:
        raise NotImplementedError


class DeterministicProvider(ConstructionProvider):
    name = "deterministic"

    def construct(self, card: ClaimCard) -> ArgumentGraph:
        return build_deterministic_graph(card)


class OpenAIProvider(ConstructionProvider):
    name = "openai"

    def __init__(self, model: str = "gpt-4.1-mini", api_key: str | None = None) -> None:
        self.model = model
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY is required for the OpenAI provider")

    def construct(self, card: ClaimCard) -> ArgumentGraph:
        from openai import OpenAI

        client = OpenAI(api_key=self.api_key)
        schema = ArgumentGraph.model_json_schema()
        response = client.responses.create(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "Reconstruct the strongest coherent world in which the claim is correct. "
                        "Return only JSON matching the supplied schema. Use typed premise nodes, "
                        "mark load-bearing premises, and never invent citations or source IDs. "
                        "All edge endpoints must be node IDs that exist in the nodes array."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {"claim_card": card.model_dump(mode="json"), "json_schema": schema}
                    ),
                },
            ],
        )
        raw = response.output_text.strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
        graph = ArgumentGraph.model_validate_json(raw)
        if graph.claim_hash != card.claim_hash:
            graph = graph.model_copy(update={"claim_hash": card.claim_hash})
        return graph


def get_provider(name: str, model: str = "gpt-4.1-mini") -> ConstructionProvider:
    if name == "openai":
        return OpenAIProvider(model=model)
    if name == "deterministic":
        return DeterministicProvider()
    raise ValueError(f"Unknown provider: {name}")


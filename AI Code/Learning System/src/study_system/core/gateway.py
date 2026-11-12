"""Small client adapters for the shared LLM gateway.

The core depends on protocols, while this module owns the HTTP and structured
output details.  No provider SDK is imported here or by the MVP services.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

from study_system.core.baseline import StudyBaseline
from study_system.types.mvp import GeneratedCard, RetrievedContext


_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
_GENERATION_PROMPT = _PROMPTS_DIR / "card_generation_flashcard_v1.md"
_VALIDATION_PROMPTS = _PROMPTS_DIR


class _SourceAnchor(BaseModel):
    file: str = ""
    highlight_id: str = ""
    char_start: int = 0
    char_end: int = 0
    text: str = ""


class _CardOutput(BaseModel):
    front: str = Field(min_length=1)
    back: str = Field(min_length=1)
    card_type: Literal["flashcard"] = "flashcard"
    source_anchor: _SourceAnchor | None = None


class _CardsOutput(BaseModel):
    cards: list[_CardOutput] = Field(min_length=1)


class _FeynmanOutput(BaseModel):
    gaps: list[dict[str, Any]]
    shallow_areas: list[dict[str, Any]]
    connections_missed: list[dict[str, Any]]
    overall_assessment: str
    ready_to_conclude: bool


class _ChallengerOutput(BaseModel):
    initial_probe: str
    follow_up_probes: list[dict[str, Any]]
    edge_cases: list[dict[str, Any]]
    known_traps: list[str]


class _GroundingOutput(BaseModel):
    passed: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str


class _RubricOutput(BaseModel):
    scores: dict[str, int]
    overall: float = Field(ge=1.0, le=5.0)
    flags: list[str] = Field(default_factory=list)
    suggestion: str | None = None


class GatewayError(RuntimeError):
    """The configured shared LLM gateway was unavailable or invalid."""


class LLMGateway:
    def __init__(self, base_url: str, timeout_seconds: float = 120.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise GatewayError(f"LLM gateway request failed ({method} {path}): {exc}") from exc
        if not isinstance(data, dict):
            raise GatewayError(f"LLM gateway returned a non-object response for {path}")
        return data

    def check_available(self) -> None:
        self._request("GET", "/v1/status")

    def structured_chat(
        self,
        *,
        prompt: str,
        model: str,
        output_model: type[BaseModel],
        max_tokens: int,
        temperature: float,
    ) -> dict[str, Any]:
        response_format = {
            "type": "json_schema",
            "name": output_model.__name__,
            "strict": True,
            "schema": output_model.model_json_schema(),
        }
        result = self._request(
            "POST",
            "/v1/chat",
            {
                "prompt": prompt,
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "response_format": response_format,
            },
        )
        parsed = result.get("parsed")
        if parsed is None:
            try:
                parsed = json.loads(str(result.get("text", "")))
            except json.JSONDecodeError as exc:
                raise GatewayError("LLM gateway response contained no valid structured output") from exc
        try:
            return output_model.model_validate(parsed).model_dump()
        except ValidationError as exc:
            raise GatewayError(f"LLM gateway structured output failed validation: {exc}") from exc


class GatewayCardGenerator:
    def __init__(self, gateway: LLMGateway) -> None:
        self._gateway = gateway

    def generate(
        self, context: RetrievedContext, target_count: int, config: StudyBaseline
    ) -> list[GeneratedCard]:
        template = _GENERATION_PROMPT.read_text(encoding="utf-8")
        facts = "\n".join(
            str(item.get("text") or item.get("content") or "")
            for item in context.vector_context
            if item.get("text") or item.get("content")
        )
        neighborhood = json.dumps(context.kg_context, sort_keys=True, default=str)
        grounded_context = "\n".join(
            part for part in (context.concept.summary, facts, f"KG neighborhood: {neighborhood}") if part
        )
        prompt = (
            template.replace("{{CANONICAL_NAME}}", context.concept.name)
            .replace("{{DOMAIN}}", context.concept.domain)
            .replace("{{SUMMARY}}", context.concept.summary)
            .replace("{{ATOMIC_FACTS}}", grounded_context)
            .replace("{{TARGET_COUNT}}", str(target_count))
        )
        output = self._gateway.structured_chat(
            prompt=prompt,
            model=config.card_gen_model,
            output_model=_CardsOutput,
            max_tokens=4000,
            temperature=0.3,
        )
        raw_cards = output["cards"]
        if len(raw_cards) != target_count:
            raise GatewayError(
                f"Card generator returned {len(raw_cards)} cards; expected exactly {target_count}"
            )
        version = context.concept.source_version or "unversioned"
        prompt_version = config.prompt_versions.get("flashcard", "card_generation_flashcard_v1")
        return [
            GeneratedCard(
                id=str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"study-card:{context.concept.id}:{version}:{prompt_version}:{index}",
                    )
                ),
                concept_id=context.concept.id,
                front=str(raw["front"]).strip(),
                back=str(raw["back"]).strip(),
                card_type="flashcard",
                source_refs=context.source_refs,
                source_version=context.concept.source_version,
                model=config.card_gen_model,
                prompt_version=prompt_version,
            )
            for index, raw in enumerate(raw_cards)
        ]


class GatewayQualityChecker:
    """Run the existing grounding and rubric prompts through the shared gateway."""

    def __init__(self, gateway: LLMGateway) -> None:
        self._gateway = gateway

    def check(
        self,
        cards: list[GeneratedCard],
        context: RetrievedContext,
        config: StudyBaseline,
    ) -> list[GeneratedCard]:
        source_text = "\n".join(
            part
            for part in (
                context.concept.summary,
                *(str(item.get("text") or item.get("content") or "") for item in context.vector_context),
            )
            if part
        ) or "(no source text retrieved)"
        grounding_template = (_VALIDATION_PROMPTS / "source_grounding_v1.md").read_text(
            encoding="utf-8"
        )
        rubric_template = (_VALIDATION_PROMPTS / "rubric_v1.md").read_text(encoding="utf-8")
        accepted: list[GeneratedCard] = []
        seen: set[tuple[str, str]] = set()
        for card in cards:
            front = card.front.strip()
            back = card.back.strip()
            identity = (front.casefold(), back.casefold())
            if (
                len(front) < config.quality_min_front_chars
                or len(back) < config.quality_min_back_chars
                or not card.source_refs
                or identity in seen
            ):
                continue
            seen.add(identity)
            grounding_prompt = (
                grounding_template.replace("{{CARD_FRONT}}", front)
                .replace("{{CARD_BACK}}", back)
                .replace("{{SOURCE_TEXT}}", source_text)
            )
            grounding = self._gateway.structured_chat(
                prompt=grounding_prompt,
                model=config.quality_model,
                output_model=_GroundingOutput,
                max_tokens=512,
                temperature=0.0,
            )
            if not grounding["passed"] or grounding["confidence"] < config.grounding_min_confidence:
                continue
            rubric_prompt = (
                rubric_template.replace("{{CARD_FRONT}}", front)
                .replace("{{CARD_BACK}}", back)
                .replace("{{CARD_TYPE}}", card.card_type)
                .replace("{{SOURCE_TEXT}}", source_text)
            )
            rubric = self._gateway.structured_chat(
                prompt=rubric_prompt,
                model=config.quality_model,
                output_model=_RubricOutput,
                max_tokens=512,
                temperature=0.0,
            )
            if rubric["overall"] >= config.rubric_fail_threshold:
                accepted.append(card)
        return accepted


class GatewayPracticeEvaluator:
    def __init__(self, gateway: LLMGateway) -> None:
        self._gateway = gateway

    def evaluate_feynman(self, prompt: str, config: StudyBaseline) -> dict[str, Any]:
        return self._gateway.structured_chat(
            prompt=prompt,
            model=config.feynman_model,
            output_model=_FeynmanOutput,
            max_tokens=2000,
            temperature=0.1,
        )

    def grade_challenger(self, prompt: str, config: StudyBaseline) -> dict[str, Any]:
        return self._gateway.structured_chat(
            prompt=prompt,
            model=config.challenger_model,
            output_model=_ChallengerOutput,
            max_tokens=2000,
            temperature=0.1,
        )

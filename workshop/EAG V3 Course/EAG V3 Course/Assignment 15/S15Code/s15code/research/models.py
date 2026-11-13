"""Bounded input and output contracts for the research desk."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Document(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=100_000)


class ResearchRequest(StrictModel):
    question: str = Field(min_length=3, max_length=2000)
    documents: list[Document] = Field(min_length=1, max_length=12)
    budget: float = Field(default=0.05, gt=0, le=10, allow_inf_nan=False)
    strategy: Literal["routed", "frontier"] = "routed"

    @model_validator(mode="after")
    def total_size(self):
        if sum(len(d.text) for d in self.documents) > 200_000:
            raise ValueError("documents must total at most 200,000 characters")
        return self


class Citation(StrictModel):
    evidence_id: str
    quote: str = Field(min_length=10, max_length=1200)


class Claim(StrictModel):
    text: str = Field(min_length=1, max_length=3000)
    citations: list[Citation] = Field(min_length=1, max_length=6)


class Brief(StrictModel):
    title: str = Field(min_length=1, max_length=200)
    conclusions: list[Claim] = Field(min_length=1, max_length=8)
    alternatives: list[Claim] = Field(min_length=1, max_length=6)
    uncertainties: list[str] = Field(min_length=1, max_length=8)


class Card(StrictModel):
    question: str = Field(min_length=1, max_length=1000)
    answer: Claim


class Cards(StrictModel):
    cards: list[Card] = Field(min_length=1, max_length=6)


class Grade(StrictModel):
    verdict: Literal["correct", "partial", "incorrect"]
    explanation: Claim


class LearningRequest(StrictModel):
    research_run_id: str = Field(min_length=1, max_length=128)
    budget: float = Field(default=0.05, gt=0, le=10, allow_inf_nan=False)


class GradeRequest(StrictModel):
    cards_run_id: str = Field(min_length=1, max_length=128)
    card_index: int = Field(ge=0, le=5)
    answer: str = Field(min_length=1, max_length=4000)
    budget: float = Field(default=0.02, gt=0, le=10, allow_inf_nan=False)

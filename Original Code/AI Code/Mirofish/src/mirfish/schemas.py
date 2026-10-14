"""All pydantic models for MIRFISH.

Every pipeline stage reads and writes these models only. JSON out of every LLM
call is validated against them (one repair retry, then fail loudly). Models are
strict: unknown fields are rejected so drift between prompts and schemas
surfaces immediately.
"""

from __future__ import annotations

import datetime as dt
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class EventType(StrEnum):
    policy_rate = "policy_rate"
    fiscal = "fiscal"
    sovereign_rating = "sovereign_rating"
    commodity_supply = "commodity_supply"
    corporate_credit = "corporate_credit"
    geopolitical = "geopolitical"
    flows = "flows"
    data_surprise = "data_surprise"
    other = "other"


class NodeType(StrEnum):
    issuer = "issuer"
    sector = "sector"
    commodity = "commodity"
    currency = "currency"
    sovereign = "sovereign"
    policy_inst = "policy_inst"
    rate_instrument = "rate_instrument"
    macro_var = "macro_var"
    flow = "flow"


class Channel(StrEnum):
    policy = "policy"
    inflation = "inflation"
    funding = "funding"
    fx = "fx"
    trade = "trade"
    supply_chain = "supply_chain"
    risk_sentiment = "risk_sentiment"
    liquidity = "liquidity"
    flows = "flows"


class SignHint(StrEnum):
    pos = "pos"
    neg = "neg"
    ambiguous = "ambiguous"


class Lag(StrEnum):
    intraday = "intraday"
    days = "days"
    weeks = "weeks"
    months = "months"


class Provenance(StrEnum):
    curated = "curated"
    llm_proposed = "llm_proposed"


class Direction(StrEnum):
    up = "up"
    down = "down"
    widen = "widen"
    tighten = "tighten"
    steepen = "steepen"
    flatten = "flatten"
    ambiguous = "ambiguous"


class Confidence(StrEnum):
    high = "high"
    med = "med"
    low = "low"


class VerdictAction(StrEnum):
    keep = "keep"
    kill = "kill"
    contest = "contest"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Event(StrictModel):
    event_id: str
    as_of: dt.date
    headline: str
    body: str
    source_note: str = ""
    event_type: EventType
    matched_nodes: list[str] = Field(default_factory=list)
    unmatched_entities: list[str] = Field(default_factory=list)  # flagged, never dropped
    magnitude_note: str = ""
    surprise_score: float = Field(ge=0.0, le=1.0)  # vs consensus AT as_of date
    consensus_context: str = ""


class Node(StrictModel):
    node_id: str
    name: str
    type: NodeType
    aliases: list[str] = Field(default_factory=list)
    notes: str = ""


class Edge(StrictModel):
    src: str
    dst: str
    channel: Channel
    mechanism: str  # one sentence, named mechanism
    sign_hint: SignHint
    typical_lag: Lag
    provenance: Provenance = Provenance.curated  # llm_proposed = quarantined


class ChainStep(StrictModel):
    node_id: str
    direction: Direction
    mechanism: str
    lag: Lag
    confidence: Confidence


class Chain(StrictModel):
    chain_id: str
    steps: list[ChainStep]
    depth: int = Field(ge=1)
    origin_node: str
    terminal_node: str
    overall_confidence: Confidence
    priced_in: bool = False
    novelty_note: str = ""


class Verdict(StrictModel):
    chain_id: str
    action: VerdictAction
    reason: str
    contested_with: list[str] = Field(default_factory=list)


class ContestedNode(StrictModel):
    node_id: str
    chains: list[str]  # chain_ids reaching this node with opposing directions
    summary: str


class StageTokenUsage(StrictModel):
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0


class RunArtifact(StrictModel):
    run_id: str
    event: Event
    config_snapshot: dict
    prompt_hashes: dict[str, str] = Field(default_factory=dict)
    chains_raw: list[Chain] = Field(default_factory=list)
    verdicts: list[Verdict] = Field(default_factory=list)
    chains_final: list[Chain] = Field(default_factory=list)
    contested_nodes: list[ContestedNode] = Field(default_factory=list)
    proposed_edges: list[Edge] = Field(default_factory=list)  # quarantine bin
    token_usage: dict[str, StageTokenUsage] = Field(default_factory=dict)
    cost_inr: float = 0.0
    timings: dict[str, float] = Field(default_factory=dict)
    truncated: bool = False

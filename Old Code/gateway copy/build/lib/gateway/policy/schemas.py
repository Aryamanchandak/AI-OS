from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

Action = Literal["allow", "deny", "require_approval"]


class PolicyRule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: str = "*"
    channel: str = "*"
    trust_level: str = "*"
    condition: dict[str, Any] = Field(default_factory=dict)
    action: Action
    reason: str = ""


class PolicyVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: Action
    reason: str
    matched_rule_index: int | None = None


class PolicyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    rules: list[PolicyRule] = Field(default_factory=list)

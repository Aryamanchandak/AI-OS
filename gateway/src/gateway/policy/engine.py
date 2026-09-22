"""Thread-safe, fail-hard policy loading and atomic reload."""

from __future__ import annotations

import fnmatch
import os
from pathlib import Path
import re
import threading
from typing import Any

import yaml

from gateway.policy.schemas import PolicyConfig, PolicyRule, PolicyVerdict


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} expected str, got {type(value).__name__}")
    return value


def _matches(condition: dict[str, Any], parameters: dict[str, Any]) -> bool:
    for key, expected in condition.items():
        if key.endswith("_glob"):
            value = os.path.expanduser(_string(parameters.get(key[:-5]), "glob condition"))
            pattern = os.path.expanduser(_string(expected, "glob pattern"))
            if "**" in pattern:
                expression = re.escape(pattern).replace(r"\*\*", ".*").replace(r"\*", "[^/]*")
                if re.fullmatch(expression, value, re.DOTALL) is None:
                    return False
            elif not fnmatch.fnmatch(value, pattern):
                return False
        elif key.endswith("_regex"):
            if re.search(_string(expected, "regex pattern"), _string(parameters.get(key[:-6]), "regex condition"), re.DOTALL) is None:
                return False
        elif key.endswith("_in"):
            if parameters.get(key[:-3]) not in (expected or []):
                return False
        elif key == "command_matches":
            command = _string(parameters.get("command", ""), "command_matches").casefold()
            patterns = expected if isinstance(expected, list) else [expected]
            if not any(str(item).casefold() in command for item in patterns):
                return False
        elif parameters.get(key) != expected:
            return False
    return True


class PolicyEngine:
    def __init__(self, path: Path, configuration: PolicyConfig) -> None:
        self.path = path
        self._configuration = configuration
        self._lock = threading.RLock()

    @classmethod
    def from_yaml(cls, path: Path) -> PolicyEngine:
        return cls(path, cls._load(path))

    @staticmethod
    def _load(path: Path) -> PolicyConfig:
        try:
            raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise ValueError(f"policy.yaml does not exist: {path}") from exc
        except yaml.YAMLError as exc:
            raise ValueError(f"policy.yaml is malformed: {path}: {exc}") from exc
        try:
            return PolicyConfig.model_validate(raw)
        except Exception as exc:
            raise ValueError(f"policy.yaml is invalid: {path}: {exc}") from exc

    def reload(self) -> None:
        replacement = self._load(self.path)
        with self._lock:
            self._configuration = replacement

    def healthcheck(self) -> None:
        self._load(self.path)

    def evaluate(self, tool_call: dict[str, Any], context: dict[str, Any]) -> PolicyVerdict:
        tool = tool_call.get("name", "")
        parameters = tool_call.get("arguments") or {}
        channel = context.get("channel", "")
        trust_level = context.get("trust_level", "untrusted")
        with self._lock:
            rules = list(self._configuration.rules)
        first: tuple[int, PolicyRule] | None = None
        deny: tuple[int, PolicyRule] | None = None
        for index, rule in enumerate(rules):
            if rule.tool not in ("*", tool) or rule.channel not in ("*", channel):
                continue
            if rule.trust_level not in ("*", trust_level):
                continue
            try:
                condition_matches = not rule.condition or _matches(rule.condition, parameters)
            except TypeError:
                condition_matches = True
            if not condition_matches:
                continue
            first = first or (index, rule)
            if rule.action == "deny" and deny is None:
                deny = (index, rule)
        selected = deny or first
        if selected is not None:
            index, rule = selected
            return PolicyVerdict(
                action=rule.action,
                reason=rule.reason or f"matched rule #{index}",
                matched_rule_index=index,
            )
        if trust_level == "owner_paired":
            return PolicyVerdict(action="allow", reason="default-allow for owner_paired")
        return PolicyVerdict(action="deny", reason=f"default-deny for trust_level={trust_level}")

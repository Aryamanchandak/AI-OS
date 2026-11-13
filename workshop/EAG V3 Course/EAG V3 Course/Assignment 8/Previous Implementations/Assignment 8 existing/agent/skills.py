"""Skill catalogue loader.

A skill is a YAML entry + a prompt file. Nothing here knows what any
particular skill *does* — only which generic runtime it wants.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent

VALID_RUNTIMES = {"llm", "sandbox", "tool"}


@dataclass(frozen=True)
class Skill:
    name: str
    runtime: str
    prompt: str
    description: str
    tool: str | None = None


def load_config(path: str | pathlib.Path = "agent_config.yaml") -> dict:
    with open(ROOT / path) as fh:
        return yaml.safe_load(fh)


def load_skills(config: dict) -> dict[str, Skill]:
    skills: dict[str, Skill] = {}
    for name, entry in config["skills"].items():
        runtime = entry["runtime"]
        if runtime not in VALID_RUNTIMES:
            raise ValueError(
                f"skill {name!r}: unknown runtime {runtime!r}. "
                f"A new runtime is an Executor change — see agent_config.yaml."
            )
        prompt_path = ROOT / entry["prompt"]
        if not prompt_path.exists():
            raise FileNotFoundError(f"skill {name!r}: missing prompt {entry['prompt']}")
        skills[name] = Skill(
            name=name,
            runtime=runtime,
            prompt=prompt_path.read_text(),
            description=entry.get("description", "").strip(),
            tool=entry.get("tool"),
        )
    return skills


def catalogue_text(skills: dict[str, Skill]) -> str:
    """Renders the catalogue for the Planner prompt, so the Planner
    automatically learns about newly added skills."""
    lines = []
    for skill in skills.values():
        if skill.name == "planner":
            continue
        lines.append(f"- {skill.name}: {skill.description}")
    return "\n".join(lines)

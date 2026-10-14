"""Component 3.3 — tool renderer / context assembler (spine).

A pure function from state -> model input. Because we are NOT using the native
`tools` param, the model has to *read* the tools as text. This renders the MCP
tool list into a text block, and assembles the full system prompt:

    persona  +  rendered tool block  +  the JSON action contract

Keeping this as an explicit boundary (separate from the message list, which is
"what happened") is what lets us change prompting strategy later without
touching the loop.
"""

from __future__ import annotations

import json
from typing import Sequence

from .mcp_client import ToolSpec

# The action contract, stated once, verbatim, in the system prompt. This is the
# text half of Component 3.4 — the parser enforces exactly this shape.
ACTION_CONTRACT = """\
## How to respond

On every turn you must reply with **exactly one JSON object and nothing else** —
no prose before or after, no markdown code fences. The object is one of two shapes.

To use a tool:
{"thought": "why this tool, and what you expect", "tool": "<tool_name>", "tool_input": { ...args matching the tool's schema... }}

To finish, when you can fully answer:
{"thought": "why you are done", "final_answer": "the complete answer for the user"}

Rules:
- Exactly one JSON object per turn. No extra text, no fences.
- "tool" must be one of the tool names listed above; "tool_input" must match its schema.
- Take one step at a time. After each tool call you will receive an OBSERVATION;
  read it, then decide the next step.
- If an observation shows an error, do not repeat the same call — fix the tool
  name or arguments, or choose a different tool.
- Do not call file tools to guess whether unspecified content might exist. Use
  file tools only for files named by the user, attached/selected files, files
  identified by previous tool results, or an unambiguous active file.
- For .json output, prefer a structured JSON-writing tool when available. If
  you write raw JSON text and the tool reports invalid JSON, correct the JSON
  before claiming the file was saved.
- Only say something was created, saved, rendered, or generated successfully
  after the corresponding tool observation confirms success. If the latest
  relevant observation is an error, report the failure or retry with corrected
  inputs.
- Stop and emit "final_answer" as soon as you have enough to answer well."""


def render_tools(tools: Sequence[ToolSpec]) -> str:
    """Render the tool list into a readable text block for the prompt."""
    if not tools:
        return "No tools are available. You must answer directly with final_answer."

    blocks: list[str] = []
    for t in tools:
        schema = json.dumps(t.input_schema, indent=2) if t.input_schema else "{}"
        desc = t.description.strip() or "(no description provided)"
        blocks.append(
            f"### {t.name}\n{desc}\n\nInput schema (JSON Schema):\n{schema}"
        )
    return "\n\n".join(blocks)


def build_system_prompt(persona: str, tools: Sequence[ToolSpec]) -> str:
    """persona + rendered tools + contract -> the single system message."""
    return (
        f"{persona.strip()}\n\n"
        f"## Available tools\n\n"
        f"You can call the following tools. Each turn you may call at most one.\n\n"
        f"{render_tools(tools)}\n\n"
        f"{ACTION_CONTRACT}"
    )

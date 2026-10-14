"""Component 3.8 — trajectory trace (spine; matters here because it's graded).

A plain structured log, one entry per event. NOT the per-step summarizer we
killed (§4) — no extra LLM calls, just a record of what happened. It is both the
debugger while building and the demo artifact when submitting, so it renders
top-to-bottom in a way a grader can read straight through (Phase 4).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

EntryKind = Literal["action", "final", "repair", "guard"]


@dataclass
class TraceEntry:
    kind: EntryKind
    step: int
    thought: str = ""
    tool: str | None = None
    tool_input: dict[str, Any] = field(default_factory=dict)
    observation: str | None = None
    final_answer: str | None = None
    note: str | None = None  # for repair / guard entries

    def to_dict(self) -> dict[str, Any]:
        # kind + step are always present; the rest are optional per entry type.
        d = {"kind": self.kind, "step": self.step}
        # Only emit fields that carry real content — drop None/""/{} so an
        # `action` entry and a `guard` entry each serialize to just their
        # relevant keys instead of a wall of empty placeholders.
        for k in ("thought", "tool", "tool_input", "observation",
                  "final_answer", "note"):
            v = getattr(self, k)
            if v not in (None, "", {}):
                d[k] = v
        return d


class Trajectory:
    """Ordered list of trace entries with human- and machine-readable output."""

    def __init__(self, task: str) -> None:
        self.task = task
        self.entries: list[TraceEntry] = []

    def add(self, entry: TraceEntry) -> TraceEntry:
        self.entries.append(entry)
        return entry

    # -- machine-readable --------------------------------------------------
    def to_json(self, indent: int = 2) -> str:
        return json.dumps(
            {"task": self.task, "trajectory": [e.to_dict() for e in self.entries]},
            indent=indent,
            ensure_ascii=False,
        )

    # -- human-readable (Phase 4) -----------------------------------------
    def render(self, color: bool = False) -> str:
        # color=False keeps output clean when piped to a file; True adds ANSI for
        # a live terminal. One branch per entry kind, each formatted distinctly.
        c = _Palette(color)
        lines: list[str] = []
        lines.append(c.bold(f"TASK: {self.task}"))
        lines.append("=" * 72)
        for e in self.entries:
            lines.append("")  # blank line separates each step block
            if e.kind == "action":
                lines.append(c.head(f"STEP {e.step}"))
                lines.append(f"  {c.dim('thought')}      {e.thought}")
                lines.append(f"  {c.dim('tool')}         "
                             f"{c.tool(e.tool)}({_fmt_args(e.tool_input)})")
                lines.append(f"  {c.dim('observation')}  {_indent(e.observation)}")
            elif e.kind == "final":
                lines.append(c.head(f"STEP {e.step}  (final)"))
                lines.append(f"  {c.dim('thought')}      {e.thought}")
                lines.append(f"  {c.ok('final answer')} {_indent(e.final_answer)}")
            elif e.kind == "repair":
                lines.append(c.warn(f"STEP {e.step}  repair"))
                lines.append(f"  {c.dim('reason')}       {e.note}")
            elif e.kind == "guard":
                lines.append(c.warn(f"STEP {e.step}  guard"))
                lines.append(f"  {c.dim('intervention')} {e.note}")
        lines.append("")
        lines.append("=" * 72)
        return "\n".join(lines)


def _fmt_args(args: dict[str, Any]) -> str:
    return json.dumps(args, ensure_ascii=False) if args else ""


def _indent(text: str | None, width: int = 15) -> str:
    # Re-indent continuation lines of a multi-line value so they align under the
    # label column instead of falling back to the left margin.
    if not text:
        return ""
    pad = " " * width
    return text.replace("\n", "\n" + pad)


class _Palette:
    """ANSI colors, but only if requested (files/pipes stay clean)."""

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def _wrap(self, code: str, s: str) -> str:
        # Wrap in an ANSI SGR escape (\033[<code>m ... \033[0m) when enabled;
        # otherwise return the string untouched so piped output stays plain text.
        return f"\033[{code}m{s}\033[0m" if self.enabled else s

    def bold(self, s: str) -> str:  return self._wrap("1", s)
    def head(self, s: str) -> str:  return self._wrap("1;36", s)
    def dim(self, s: str) -> str:   return self._wrap("2", s)
    def tool(self, s: str) -> str:  return self._wrap("35", s)
    def ok(self, s: str) -> str:    return self._wrap("1;32", s)
    def warn(self, s: str) -> str:  return self._wrap("1;33", s)

"""Shared AX/vision execution: one grounded action, re-scan, then judgment.

The existing loop and contracts are retained; cua-driver owns OS interactions.
Prompts live in prompts/computer_ax.md and prompts/computer_vision.md.
"""
from __future__ import annotations

import asyncio
import time
import math
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

from browser.client import V9Client

from . import input as osinput
from .backend import get_driver
from .ax import UISnapshot, enumerate_ui
from .recorder import Recorder
from .screen import annotate, image_bytes, to_data_url


# ── action vocabulary (shared) ──────────────────────────────────────────────
ACTION_SCHEMA: dict = {
    "type": "object",
    "additionalProperties": False,
    "required": ["thinking", "actions"],
    "properties": {
        "thinking": {"type": "string", "description": "1-2 sentences of reasoning"},
        "actions": {
            "type": "array",
            "minItems": 1,
            "maxItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["type"],
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["click", "type", "key", "hotkey", "scroll",
                                 "drag", "wait", "done", "escalate"],
                    },
                    "mark":    {"type": "integer"},
                    "x":       {"type": "number"},
                    "y":       {"type": "number"},
                    "value":   {"type": "string"},
                    "modifiers": {"type": "array", "items": {"type": "string"}},
                    "clear":   {"type": "boolean"},
                    "from_x":  {"type": "integer"},
                    "from_y":  {"type": "integer"},
                    "to_x":    {"type": "integer"},
                    "to_y":    {"type": "integer"},
                    "amount":  {"type": "integer"},
                    "seconds": {"type": "number"},
                    "success": {"type": "boolean"},
                    "note":    {"type": "string"},
                    "direction": {"type": "string"},
                },
            },
        },
    },
}


PROMPTS = Path(__file__).resolve().parents[1] / "prompts"
SYSTEM_PROMPT_AX = (PROMPTS / "computer_ax.md").read_text()
SYSTEM_PROMPT_VISION = (PROMPTS / "computer_vision.md").read_text()


# ── shared records ──────────────────────────────────────────────────────────
@dataclass
class StepRecord:
    turn: int
    thinking: str
    actions: list[dict]
    outcome: str
    provider: str = ""
    model: str = ""
    latency_ms: int = 0
    tokens_in: int = 0
    tokens_out: int = 0


@dataclass
class DriverConfig:
    goal: str
    app: str
    max_steps: int = 12
    max_failures: int = 3
    pause_between_steps: float = 0.5
    provider: Optional[str] = None
    model: Optional[str] = None


@dataclass
class DriverResult:
    success: bool
    note: str
    steps: list[StepRecord] = field(default_factory=list)
    turns: int = 0
    actions: list[dict] = field(default_factory=list)
    extracted: str = ""


# ── action dispatcher (shared) ──────────────────────────────────────────────
def dispatch(action: dict, snap: UISnapshot) -> str:
    """Execute one action against the live screen. Marks resolve through the
    snapshot the model was shown, so a stale mark fails loudly rather than
    clicking whatever now occupies those coordinates."""
    t = action.get("type", "")

    if t in ("click", "type"):
        driver = get_driver()
        target = {"pid": snap.pid, "window_id": snap.window_id}
        if t == "click" and "mark" not in action:
            x, y = action.get("x"), action.get("y")
            if (type(x) not in (int, float) or type(y) not in (int, float)
                    or not math.isfinite(x) or not math.isfinite(y) or x < 0 or y < 0):
                return "error: click requires a valid mark or nonnegative x,y"
            width = snap.screenshot.get("screenshot_width")
            height = snap.screenshot.get("screenshot_height")
            if (width and x >= width) or (height and y >= height):
                return "error: click is outside the window screenshot"
            driver.call("click", {**target, "x": x, "y": y})
            return "ok"
        el = snap.by_id(int(action.get("mark", -1)))
        if not el:
            return f"error: no element with mark {action.get('mark')!r}"
        if t == "click":
            driver.call("click", {**target, "element_index": el.id})
        elif action.get("clear", True):
            driver.call("set_value", {**target, "element_index": el.id,
                                      "value": str(action.get("value", ""))})
        else:
            driver.call("type_text", {**target, "element_index": el.id,
                                      "text": str(action.get("value", ""))})
        return "ok"

    if t in ("key", "hotkey"):
        return osinput.press_key(str(action.get("value", "return")),
                                 modifiers=action.get("modifiers") or [])
    if t == "scroll":
        return osinput.scroll(str(action.get("direction", "down")),
                              int(action.get("amount", 5)))
    if t == "drag":
        return osinput.drag(int(action["from_x"]), int(action["from_y"]),
                            int(action["to_x"]), int(action["to_y"]))
    if t == "wait":
        time.sleep(max(0, min(float(action.get("seconds", 0.5)), 2)))
        return "ok"
    if t == "done":
        return "ok"
    return f"error: unknown action {t!r}"


# ── shared loop machinery ───────────────────────────────────────────────────
class BaseDriver:
    """Shared per-turn loop. Subclasses provide `_decide()` and the prompt."""

    SYSTEM_PROMPT: str = ""
    LAYER_NAME: str = "base"

    def __init__(self, client: V9Client, config: DriverConfig,
                 recorder: Recorder):
        self.client = client
        self.config = config
        self.rec = recorder
        self.steps: list[StepRecord] = []

    def _history_text(self) -> str:
        if not self.steps:
            return "(no actions yet)"
        lines = []
        for s in self.steps[-5:]:
            acts = ", ".join(
                f"{a['type']}({a.get('mark', a.get('value', ''))})"
                for a in s.actions[:3]
            )
            lines.append(f"turn {s.turn}: {acts} -> {s.outcome}")
        return "\n".join(lines)

    def _snapshot(self) -> UISnapshot:
        return enumerate_ui(self.config.app, mode="som" if self.LAYER_NAME == "vision" else "ax")

    async def _decide(self, snap: UISnapshot, turn: int):
        raise NotImplementedError

    async def step(self, turn: int) -> tuple[bool, bool, str]:
        snap = self._snapshot()
        if self.LAYER_NAME == "ax" and not snap.elements:
            self.steps.append(StepRecord(turn, "", [], "AX tree has no actionable target"))
            return True, False, "AX tree has no actionable target; escalate to vision"
        parsed, result = await self._decide(snap, turn)

        if not parsed:
            self.steps.append(StepRecord(
                turn, "", [],
                f"error: parsed output missing; raw={(result.text or '')[:120]!r}",
                result.provider, result.model, result.latency_ms,
                result.input_tokens, result.output_tokens))
            return False, False, "no parsed output"

        thinking = parsed.get("thinking", "")
        actions = parsed.get("actions") or []
        if len(actions) != 1:
            self.steps.append(StepRecord(turn, thinking, [], "error: exactly one action is required"))
            return False, False, "rejected action batch"
        if self.LAYER_NAME == "ax" and (actions[0].get("type") == "drag" or
                                       "x" in actions[0] or "y" in actions[0]):
            self.steps.append(StepRecord(turn, thinking, [], "text layer cannot infer coordinates"))
            return True, False, "text layer cannot infer coordinates; escalate to vision"
        outcomes: list[str] = []
        done_seen, success_seen, done_note = False, False, ""

        for a in actions:
            if a.get("type") == "escalate":
                done_seen, success_seen = True, False
                done_note = a.get("note", "target absent; escalate")
                outcomes.append("escalate")
                break
            if a.get("type") == "done":
                done_seen = True
                success_seen = bool(a.get("success", False))
                done_note = a.get("note", "")
                outcomes.append(f"done({success_seen})")
                break
            try:
                outcome = dispatch(a, snap)
            except PermissionError:
                raise
            except Exception as e:                       # noqa: BLE001
                outcome = f"error: {type(e).__name__}: {e}"
            outcomes.append(outcome)
            if outcome.startswith("error"):
                break
            time.sleep(self.config.pause_between_steps)
            verified = enumerate_ui(self.config.app)
            self.rec.artifact(self.LAYER_NAME, f"turn_{turn:02d}_verify.txt", verified.text_dump())

        rec = StepRecord(
            turn=turn, thinking=thinking, actions=actions,
            outcome=" | ".join(outcomes) or "ok",
            provider=result.provider, model=result.model,
            latency_ms=result.latency_ms,
            tokens_in=result.input_tokens, tokens_out=result.output_tokens,
        )
        self.steps.append(rec)
        self.rec.log("step", layer=self.LAYER_NAME, turn=turn,
                     actions=actions, outcome=rec.outcome)
        return done_seen, success_seen, done_note

    async def run(self) -> DriverResult:
        failures = 0
        for turn in range(1, self.config.max_steps + 1):
            done, success, note = await self.step(turn)
            last = self.steps[-1]
            if "error" in last.outcome:
                failures += 1
                if failures >= self.config.max_failures:
                    return self._result(False,
                                        f"{failures} consecutive failures; "
                                        f"last: {last.outcome}")
            else:
                failures = 0
            if done:
                return self._result(success, note or "driver reported done")
            await asyncio.sleep(0.2)
        return self._result(False, f"turn cap ({self.config.max_steps}) reached")

    def _result(self, success: bool, note: str) -> DriverResult:
        return DriverResult(
            success=success, note=note, steps=self.steps,
            turns=len(self.steps),
            actions=[{"turn": s.turn, "actions": s.actions, "outcome": s.outcome}
                     for s in self.steps],
        )


class AXDriver(BaseDriver):
    """Layer 2b — AX legend to /v1/chat. No image, no vision provider."""

    SYSTEM_PROMPT = SYSTEM_PROMPT_AX
    LAYER_NAME = "ax"

    async def _decide(self, snap: UISnapshot, turn: int):
        prompt = (
            f"GOAL: {self.config.goal}\n"
            f"APP: {snap.app}\nWINDOW: {snap.window_title}\n\n"
            f"ELEMENTS:\n{snap.legend()}\n\n"
            f"HISTORY:\n{self._history_text()}\n\n"
            f"Turn {turn} of {self.config.max_steps}. Emit your actions."
        )
        self.rec.artifact("ax", f"turn_{turn:02d}_legend.txt", snap.legend())
        self.rec.note_llm_call("ax")
        result = await self.client.chat(
            prompt, schema=ACTION_SCHEMA, schema_name="actions",
            system=self.SYSTEM_PROMPT, provider=self.config.provider,
            model=self.config.model,
        )
        return result.parsed, result


class VisionDriver(BaseDriver):
    """Layer 3 — annotated screenshot to /v1/vision.

    The legend still ships alongside the image. Marks alone are ambiguous
    once a screen has more than a handful of them, and the geometry hints
    are what let the model emit coordinates for unmarked canvas regions."""

    SYSTEM_PROMPT = SYSTEM_PROMPT_VISION
    LAYER_NAME = "vision"

    async def _decide(self, snap: UISnapshot, turn: int):
        png = image_bytes(snap)
        shot = annotate(png)
        self.rec.artifact("vision", f"turn_{turn:02d}_screen.png", shot)

        legend = "\n".join(
            e.legend_line()
            for e in snap.elements
        ) or "(no accessible elements — this target is canvas-rendered; " \
             "use coordinates read off the screenshot)"

        prompt = (
            f"GOAL: {self.config.goal}\n"
            f"APP: {snap.app}\nWINDOW: {snap.window_title}\n\n"
            f"WINDOW SCREENSHOT: {snap.screenshot.get('screenshot_width')} x "
            f"{snap.screenshot.get('screenshot_height')} pixels\n"
            f"MARK LEGEND:\n{legend}\n\n"
            f"HISTORY:\n{self._history_text()}\n\n"
            f"Turn {turn} of {self.config.max_steps}. Emit your actions."
        )
        self.rec.note_llm_call("vision")
        result = await self.client.vision(
            to_data_url(shot), prompt, schema=ACTION_SCHEMA,
            schema_name="actions", system=self.SYSTEM_PROMPT,
            provider=self.config.provider, model=self.config.model,
        )
        return result.parsed, result

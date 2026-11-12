"""Computer-use drivers — Layer 2b (AX tree, text LLM) and Layer 3 (vision).

Structurally identical to browser/driver.py, and for the same reason: the
two layers differ only in `_decide()`. Layer 2b sends the AX legend alone to
/v1/chat; Layer 3 sends an annotated screenshot to /v1/vision. Everything
else — the action vocabulary, the dispatcher, the per-turn loop, the
failure and done logic — is shared. Keeping them one class with one
override is what makes "Layer 3 is Layer 2b plus a screenshot" true in the
code rather than just in the comments.

Every LLM call passes through `Recorder.note_llm_call`, which is how the
zero-vision constraint stays auditable.
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Optional

from browser.client import V9Client

from . import input as osinput
from .ax import UISnapshot, enumerate_ui
from .recorder import Recorder
from .screen import annotate, capture, to_data_url


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
            "maxItems": 2,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["type"],
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["click", "type", "key", "hotkey", "scroll",
                                 "drag", "wait", "done"],
                    },
                    "mark":    {"type": "integer"},
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


_ACTIONS_DOC = (
    "  click(mark)                — click the centre of the element\n"
    "  type(mark, value, clear?)  — focus the element then type `value`\n"
    "  key(value, modifiers?)     — press a key, e.g. key('s', ['cmd'])\n"
    "  hotkey(value, modifiers?)  — alias of key, for chords\n"
    "  scroll(direction, amount?) — direction in ['up','down','left','right']\n"
    "  drag(from_x,from_y,to_x,to_y) — pointer drag in SCREEN POINTS\n"
    "  wait(seconds)              — pause to let the UI settle\n"
    "  done(success, note)        — finish; success=true if the goal is met\n"
)

SYSTEM_PROMPT_AX = (
    "You are a desktop-driving agent on macOS. Each turn you receive ONLY a "
    "text legend of the frontmost window's accessibility elements, formatted "
    "as [id]<tag role=\"AXRole\" value=\"...\">name</tag>. There is no "
    "screenshot. Make progress toward the goal by emitting a short list of "
    "actions. Available actions:\n" + _ACTIONS_DOC +
    "\nCHOOSING ELEMENTS:\n"
    "  - You CANNOT see the screen. Rely on role, name and value.\n"
    "  - `value` is the live state of a control. For a text field or a "
    "    display, the value — not the name — tells you what is currently "
    "    there. Read it before deciding you are done.\n"
    "  - AXStaticText elements are usually labels or readouts, not buttons. "
    "    Prefer AXButton / AXTextField / AXMenuItem as click targets.\n"
    "\nCRITICAL RULES:\n"
    "  - Never bundle `done` with other actions in the same turn. After an "
    "    action, observe the next turn's legend to confirm the state changed "
    "    the way you expected, then declare done.\n"
    "  - Menus are stateful: clicking a menu bar item reveals its items only "
    "    on the NEXT turn. Never chain a click after a menu-opening click.\n"
    "  - At most 2 actions per turn. Most turns should be ONE action.\n"
    "Be terse in `thinking` — one or two sentences."
)

SYSTEM_PROMPT_VISION = (
    "You are a desktop-driving agent on macOS. Each turn you receive a "
    "screenshot of the screen with numbered coloured boxes over candidate "
    "elements, plus a text legend mapping each number to its role and name. "
    "Some targets — canvas, game boards, drawings — have NO box, because "
    "they expose no accessibility information. For those, use drag() and "
    "click() with explicit coordinates read off the screenshot.\n"
    "Available actions:\n" + _ACTIONS_DOC +
    "\nCOORDINATES: the screenshot may be downscaled for transport, but you "
    "must emit coordinates in SCREEN POINTS as shown in the legend's "
    "geometry hints. When in doubt, prefer clicking a numbered mark over "
    "guessing a coordinate.\n"
    "\nCRITICAL RULES:\n"
    "  - Never bundle `done` with other actions. Confirm the change in the "
    "    next screenshot first.\n"
    "  - At most 2 actions per turn.\n"
    "Be terse in `thinking` — one or two sentences."
)


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
        el = snap.by_id(int(action.get("mark", -1)))
        if not el:
            return f"error: no element with mark {action.get('mark')!r}"
        out = osinput.click(el.cx, el.cy)
        if out.startswith("error") or t == "click":
            return out
        if action.get("clear", True):
            osinput.press_key("a", modifiers=["cmd"])
            osinput.press_key("delete")
        return osinput.type_text(str(action.get("value", "")))

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
        time.sleep(float(action.get("seconds", 0.5)))
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
        return enumerate_ui(self.config.app)

    async def _decide(self, snap: UISnapshot, turn: int):
        raise NotImplementedError

    async def step(self, turn: int) -> tuple[bool, bool, str]:
        snap = self._snapshot()
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
        outcomes: list[str] = []
        done_seen, success_seen, done_note = False, False, ""

        for a in actions:
            if a.get("type") == "done":
                done_seen = True
                success_seen = bool(a.get("success", False))
                done_note = a.get("note", "")
                outcomes.append(f"done({success_seen})")
                break
            try:
                outcome = dispatch(a, snap)
            except Exception as e:                       # noqa: BLE001
                outcome = f"error: {type(e).__name__}: {e}"
            outcomes.append(outcome)
            if outcome.startswith("error"):
                break
            time.sleep(self.config.pause_between_steps)

        rec = StepRecord(
            turn=turn, thinking=thinking, actions=actions,
            outcome=" | ".join(outcomes) or "ok",
            provider=result.provider, model=result.model,
            latency_ms=result.latency_ms,
            tokens_in=result.input_tokens, tokens_out=result.output_tokens,
        )
        self.steps.append(rec)
        self.rec.log("step", layer=self.LAYER_NAME, turn=turn,
                     thinking=thinking, actions=actions, outcome=rec.outcome)
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
        self.rec.artifact("ax", f"turn_{turn:02d}_legend.txt", prompt)
        result = await self.client.chat(
            prompt, schema=ACTION_SCHEMA, schema_name="actions",
            system=self.SYSTEM_PROMPT, provider=self.config.provider,
            model=self.config.model,
        )
        self.rec.note_llm_call("ax", provider=result.provider, model=result.model,
                               tokens_in=result.input_tokens,
                               tokens_out=result.output_tokens,
                               latency_ms=result.latency_ms)
        return result.parsed, result


class VisionDriver(BaseDriver):
    """Layer 3 — annotated screenshot to /v1/vision.

    The legend still ships alongside the image. Marks alone are ambiguous
    once a screen has more than a handful of them, and the geometry hints
    are what let the model emit coordinates for unmarked canvas regions."""

    SYSTEM_PROMPT = SYSTEM_PROMPT_VISION
    LAYER_NAME = "vision"

    async def _decide(self, snap: UISnapshot, turn: int):
        png, scale = capture()
        shot = annotate(png, snap.elements, scale)
        self.rec.artifact("vision", f"turn_{turn:02d}_screen.png", shot)

        legend = "\n".join(
            f"{e.legend_line()}  @ ({e.cx},{e.cy}) size {e.w}x{e.h}"
            for e in snap.elements
        ) or "(no accessible elements — this target is canvas-rendered; " \
             "use coordinates read off the screenshot)"

        prompt = (
            f"GOAL: {self.config.goal}\n"
            f"APP: {snap.app}\nWINDOW: {snap.window_title}\n\n"
            f"MARK LEGEND (screen points):\n{legend}\n\n"
            f"HISTORY:\n{self._history_text()}\n\n"
            f"Turn {turn} of {self.config.max_steps}. Emit your actions."
        )
        self.rec.artifact("vision", f"turn_{turn:02d}_prompt.txt", prompt)
        result = await self.client.vision(
            to_data_url(shot), prompt, schema=ACTION_SCHEMA,
            schema_name="actions", system=self.SYSTEM_PROMPT,
            provider=self.config.provider, model=self.config.model,
        )
        self.rec.note_llm_call("vision", provider=result.provider,
                               model=result.model,
                               tokens_in=result.input_tokens,
                               tokens_out=result.output_tokens,
                               latency_ms=result.latency_ms)
        return result.parsed, result

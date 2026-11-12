"""Component 3.6 — loop controller (THROWAWAY: the only piece PDMA rebuilds).

The whole ReAct while-loop:

    think -> parse -> if final_answer: stop
                      else call_tool -> append observation -> repeat

bounded by a max-iteration cap, with the guards (§3.7) and trace (§3.8) wired in.
The intelligence lives in the model; this is deliberately the small, boring core.

It also owns the message list (§3.5) — the memory. There is no separate
trajectory format: system prompt once, then alternating model decisions and tool
observations appended as the run proceeds.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from time import perf_counter
from typing import Callable

from .brain import Brain, Message
from .config import LoopConfig
from .guards import RepeatGuard, truncate_observation
from .mcp_client import MCPClient
from .parser import Decision, MalformedDecision, UnknownTool, parse
from .request_guard import unresolved_reference_response
from .tool_renderer import build_system_prompt
from .trace import TraceEntry, Trajectory

logger = logging.getLogger(__name__)

StopReason = str  # "final_answer" | "max_iterations" | "repair_exhausted"


@dataclass
class LoopResult:
    final_answer: str | None
    stop_reason: StopReason
    trajectory: Trajectory


class ReactLoop:
    """Drives one task to completion against one brain + one MCP client."""

    def __init__(
        self,
        brain: Brain,
        client: MCPClient,
        config: LoopConfig,
        on_entry: Callable[[TraceEntry], None] | None = None,
    ) -> None:
        self.brain = brain
        self.client = client
        self.config = config
        self._on_entry = on_entry

    def _emit(self, trajectory: Trajectory, entry: TraceEntry) -> TraceEntry:
        # Single choke-point for recording an event: append it to the permanent
        # trajectory AND fire the optional live callback (used by the web UI /
        # CLI to stream steps as they happen). Everything that happens goes
        # through here so nothing is silently untraced.
        trajectory.add(entry)
        if self._on_entry:
            self._on_entry(entry)
        return entry

    async def _think(self, messages: list[Message]) -> str:
        """Run the (synchronous) brain off the event loop so MCP I/O isn't blocked."""
        return await asyncio.to_thread(self.brain.think, messages)

    async def run(self, task: str) -> LoopResult:
        cfg = self.config
        trajectory = Trajectory(task)
        if response := unresolved_reference_response(task):
            self._emit(trajectory, TraceEntry(
                kind="final",
                step=1,
                thought="The request refers to unspecified content, so no tool "
                        "call is grounded.",
                final_answer=response,
            ))
            return LoopResult(response, "final_answer", trajectory)

        # Discover the toolset once, up front. `valid_names` is the set the
        # parser checks against to distinguish a real tool from a hallucinated one.
        tools = await self.client.list_tools()
        valid_names = {t.name for t in tools}

        logger.info(
            "run start: task=%r model=%s max_iterations=%d tools=%d",
            task[:120], cfg.model, cfg.max_iterations, len(tools),
        )

        # --- message list (§3.5): the memory -----------------------------
        messages: list[Message] = [
            {"role": "system", "content": build_system_prompt(cfg.persona, tools)},
            {"role": "user", "content": task},
        ]

        repeat_guard = RepeatGuard()

        # The main ReAct loop. `step` is 1-based for human-readable traces and is
        # the hard stop: at most max_iterations think->act cycles, no matter what.
        step = 0
        while step < cfg.max_iterations:
            step += 1

            # --- think + bounded repair path (§3.4, failure path 1) -------
            decision = await self._obtain_decision(
                messages, valid_names, trajectory, step
            )
            if decision is None:
                # Repair attempts exhausted: give up cleanly.
                logger.info("run end: stop_reason=repair_exhausted after %d step(s)", step)
                return LoopResult(None, "repair_exhausted", trajectory)
            if isinstance(decision, _UnknownToolOutcome):
                # Failure path 2: fed back as an observation, model self-corrects.
                logger.warning(
                    "step %d: unknown tool %r -> fed back as observation",
                    step, decision.tool,
                )
                self._append_observation(messages, decision.message)
                self._emit(trajectory, TraceEntry(
                    kind="action", step=step,
                    thought=decision.thought, tool=decision.tool,
                    tool_input=decision.tool_input,
                    observation=decision.message,
                ))
                continue

            # --- final answer? stop. -------------------------------------
            if decision.is_final:
                logger.info("step %d: final answer -> stop_reason=final_answer", step)
                self._emit(trajectory, TraceEntry(
                    kind="final", step=step,
                    thought=decision.thought, final_answer=decision.final_answer,
                ))
                return LoopResult(decision.final_answer, "final_answer", trajectory)

            # --- repeat-action guard (§3.7) ------------------------------
            assert decision.tool is not None
            logger.info("step %d: tool=%s", step, decision.tool)
            logger.debug(
                "step %d: thought=%r tool_input=%s",
                step, decision.thought, decision.tool_input,
            )
            if repeat_guard.is_repeat(decision.tool, decision.tool_input):
                logger.warning(
                    "step %d: repeat-guard tripped on tool=%s", step, decision.tool
                )
                note = RepeatGuard.message(decision.tool)
                self._append_observation(messages, note)
                self._emit(trajectory, TraceEntry(
                    kind="guard", step=step, note=note,
                ))
                continue

            # --- execute the tool; failure is just an observation --------
            # Core principle: a tool error is normal control flow, never a crash.
            # Any exception (bad args, server fault, transport drop) is caught and
            # turned into an ERROR observation the model can read and react to.
            started = perf_counter()
            try:
                raw_obs = await self.client.call_tool(
                    decision.tool, decision.tool_input
                )
                elapsed_ms = (perf_counter() - started) * 1000
                logger.info(
                    "step %d: tool=%s ok in %.0fms (%d chars)",
                    step, decision.tool, elapsed_ms, len(raw_obs),
                )
            except Exception as e:  # server/transport error -> observation
                elapsed_ms = (perf_counter() - started) * 1000
                logger.warning(
                    "step %d: tool=%s raised after %.0fms: %s",
                    step, decision.tool, elapsed_ms, e,
                )
                raw_obs = f"ERROR calling '{decision.tool}': {e}"

            # Truncate before it enters the context, then append + trace it.
            observation = truncate_observation(raw_obs, cfg.observation_char_limit)
            self._append_observation(messages, observation)
            self._emit(trajectory, TraceEntry(
                kind="action", step=step,
                thought=decision.thought, tool=decision.tool,
                tool_input=decision.tool_input, observation=observation,
            ))

        # --- hit the iteration cap without finishing ---------------------
        logger.info(
            "run end: stop_reason=max_iterations (cap=%d reached)", cfg.max_iterations
        )
        return LoopResult(None, "max_iterations", trajectory)

    # ---------------------------------------------------------------------
    async def _obtain_decision(
        self,
        messages: list[Message],
        valid_names: set[str],
        trajectory: Trajectory,
        step: int,
    ) -> "Decision | _UnknownToolOutcome | None":
        """Think, then parse. Handle the two failure paths distinctly.

        Returns a Decision on success, an _UnknownToolOutcome for the
        observation path, or None when the repair path is exhausted.
        """
        cfg = self.config
        # First attempt: ask the model, and record its raw reply in the memory
        # immediately so the conversation stays coherent even if parsing fails.
        reply = await self._think(messages)
        messages.append({"role": "assistant", "content": reply})

        repairs = 0
        while True:
            try:
                # Happy path (and unknown-tool path, which parse signals via a
                # distinct exception rather than a MalformedDecision).
                return parse(reply, valid_names)
            except UnknownTool as e:
                # Well-formed but names a missing tool -> caller feeds it back as
                # an observation. This is NOT counted against the repair budget.
                return _UnknownToolOutcome.from_error(reply, e)
            except MalformedDecision as e:
                if repairs >= cfg.max_repairs:
                    logger.warning(
                        "step %d: gave up after %d repair attempt(s): %s",
                        step, repairs, e,
                    )
                    self._emit(trajectory, TraceEntry(
                        kind="repair", step=step,
                        note=f"gave up after {repairs} repair attempts: {e}",
                    ))
                    return None
                repairs += 1
                logger.warning("step %d: repair attempt %d: %s", step, repairs, e)
                self._emit(trajectory, TraceEntry(
                    kind="repair", step=step,
                    note=f"attempt {repairs}: {e}",
                ))
                # Feed the *specific* parse error back and re-ask (repair path).
                # The error text tells the model what was wrong, so the retry is
                # informed rather than a blind re-roll. Then loop to re-parse.
                messages.append({
                    "role": "user",
                    "content": f"Your previous reply could not be parsed. {e} "
                               "Reply again with exactly one valid JSON object.",
                })
                reply = await self._think(messages)
                messages.append({"role": "assistant", "content": reply})

    @staticmethod
    def _append_observation(messages: list[Message], observation: str) -> None:
        # Observations enter memory as `user` turns tagged with an OBSERVATION:
        # prefix, so the model can clearly tell tool output apart from its own
        # prior decisions and from the original task.
        messages.append({"role": "user", "content": f"OBSERVATION:\n{observation}"})


@dataclass
class _UnknownToolOutcome:
    """Carries an unknown-tool decision through to the observation path."""

    thought: str
    tool: str
    tool_input: dict
    message: str

    @classmethod
    def from_error(cls, reply: str, err: UnknownTool) -> "_UnknownToolOutcome":
        # The reply already parsed cleanly (UnknownTool is raised *after* JSON
        # validation), so we re-parse here only to salvage thought/tool_input for
        # a richer trace entry. It's best-effort: any hiccup falls back to empties
        # since err.message (the tool-not-found text) is what actually goes back
        # to the model as the observation.
        import json
        thought, tool_input = "", {}
        try:
            obj = json.loads(reply.strip().strip("`"))
            if isinstance(obj, dict):
                # Guard each field's type so a malformed value can't crash the trace.
                thought = obj.get("thought", "") if isinstance(
                    obj.get("thought", ""), str) else ""
                ti = obj.get("tool_input", {})
                tool_input = ti if isinstance(ti, dict) else {}
        except Exception:
            pass
        return cls(thought=thought, tool=err.tool, tool_input=tool_input,
                   message=str(err))

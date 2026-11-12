"""Session 10: the Computer-Use skill — cascade wrapper around the OS drivers.

Translates the orchestrator's NodeSpec contract into the typed
ComputerOutput / AgentResult contract, and owns the layer cascade:

    Layer 1  — AX text read            (no LLM, no vision)
    Layer 2a — deterministic hotkeys   (no LLM, no vision)
    Layer 2b — AXDriver                (text-only, V9 /v1/chat)
    Layer 2c — page tool over CDP      (structured, no vision) [Electron]
    Layer 3  — VisionDriver            (vision, V9 /v1/vision)

Escalation rule, identical to the browser skill's: a layer escalates when
its output is empty or evidently insufficient, and the skill stops at the
first layer that produces a useful answer. Cost rises monotonically down
that list, so stopping early is the whole point.

On the ordering of 2c. It sits below 2b by number but is *tried before it*
when `electron_debugging_port` is set, because for an Electron target a
real DOM read is both cheaper and more reliable than an AX walk of a
Chromium tree — Electron AX trees are enormous and largely unnamed. The
number reflects its structural kinship with Layer 1 (structured, no model);
the ordering reflects cost. `_plan_layers()` is the single place that
ordering is decided, so it can be read in one screenful.

Permission failures are first-class, mirroring how the browser skill treats
gateway blocks: missing Accessibility or Screen Recording rights are not
"the task failed", they are `permission_denied` with the exact grant needed.
The distinction matters because the recovery path should prompt a human,
not re-plan.
"""
from __future__ import annotations

import time
from pathlib import Path

from schemas import AgentResult, ComputerOutput, NodeSpec

from browser.client import V9Client

from . import input as osinput
from .ax import ax_available, enumerate_ui
from .cdp import CDPError, open_page
from .driver import AXDriver, DriverConfig, DriverResult, VisionDriver
from .recorder import Recorder, start_recording


class ComputerSkill:
    NAME = "computer"

    def __init__(self, *, gateway_url: str = "http://localhost:8109",
                 agent_tag: str = "computer",
                 ax_provider_pin: str | None = "gemini",
                 vision_provider_pin: str | None = None,
                 trajectories_root: str | None = None,
                 max_steps_ax: int = 12,
                 max_steps_vision: int = 12,
                 session: str | None = None):
        self.gateway_url = gateway_url
        self.agent_tag = agent_tag
        self.ax_provider_pin = ax_provider_pin
        self.vision_provider_pin = vision_provider_pin
        self.trajectories_root = trajectories_root
        self.max_steps_ax = max_steps_ax
        self.max_steps_vision = max_steps_vision
        self.session = session

    # ── layer planning ─────────────────────────────────────────────────────
    def _plan_layers(self, node: NodeSpec) -> list[str]:
        """Decide which layers to try, in order. Single source of truth for
        cascade ordering.

        `force_path` is the escape hatch the browser skill has for the same
        reason: proving that Layer 3 works requires a way to reach it even
        when an earlier layer would have answered."""
        force = node.metadata.get("force_path")
        if force:
            return [force]

        layers = ["extract"]
        if node.metadata.get("keys") or node.metadata.get("applescript"):
            layers.append("deterministic")
        if node.metadata.get("electron_debugging_port"):
            # Cheaper and sturdier than AX for Chromium trees — see module doc.
            layers.append("page")
        layers += ["ax", "vision"]
        return layers

    # ── public entry point ─────────────────────────────────────────────────
    async def run(self, node: NodeSpec) -> AgentResult:
        app = node.metadata.get("app") or ""
        goal = node.metadata.get("goal") or "inspect the screen"
        task = node.metadata.get("task") or (app or "computer").lower().replace(" ", "_")

        if not app:
            return self._pack_error(app, goal, "interaction_failed",
                                    "no app given (metadata.app)")

        t0 = time.time()
        rec = start_recording(task, goal, root=self.trajectories_root)
        client = V9Client(base_url=self.gateway_url, agent=self.agent_tag,
                          session=self.session)

        layers = self._plan_layers(node)
        rec.log("plan", layers=layers, app=app,
                electron_port=node.metadata.get("electron_debugging_port"))

        # Bring the target forward once, up front. Every layer below reads or
        # drives the frontmost window, so this is a precondition of all of
        # them rather than any one layer's business.
        if node.metadata.get("activate", True):
            ok, err = osinput.activate_app(app)
            rec.log("activate", app=app, ok=ok, detail=err)
            if not ok:
                rec.finish(success=False, path="extract",
                           note=f"could not activate {app}: {err}")
                return self._pack_error(app, goal, "app_unavailable",
                                        f"could not activate {app!r}: {err}",
                                        elapsed=time.time() - t0)

        last_note = ""
        for layer in layers:
            handler = getattr(self, f"_layer_{layer}")
            try:
                result = await handler(node, app, goal, client, rec)
            except PermissionError as e:
                result = e            # handled as terminal just below
                rec.log("layer_error", layer=layer, error=str(e))
            except Exception as e:                       # noqa: BLE001
                result = None
                last_note = f"{layer}: {type(e).__name__}: {e}"
                rec.log("layer_error", layer=layer, error=last_note)

            if isinstance(result, PermissionError):
                # Terminal, not escalatable: no later layer can succeed
                # without the grant either, and re-planning cannot obtain
                # one. Surface it to a human immediately.
                rec.finish(success=False, path=layer, note=str(result))
                return self._pack_error(app, goal, "permission_denied",
                                        str(result),
                                        elapsed=time.time() - t0,
                                        trajectory=rec.root)
            if result is None:
                continue
            if isinstance(result, str):
                # A layer declined and handed back its reason. Recording it
                # is what makes the trajectory explain *why* the cascade
                # escalated, rather than just showing that it did.
                last_note = result
                rec.log("layer_escalate", layer=layer, reason=result)
                continue
            if isinstance(result, AgentResult):
                # A layer returning AgentResult has decided the run outright
                # (success, or a terminal failure like a denied permission).
                rec.finish(success=result.success, path=layer,
                           note=result.error or "ok")
                return result
            last_note = result

        rec.finish(success=False, path=layers[-1] if layers else "extract",
                   note=f"all layers exhausted; last: {last_note}")
        return self._pack_error(app, goal, "interaction_failed",
                                f"all layers exhausted; last: {last_note}",
                                elapsed=time.time() - t0, trajectory=rec.root)

    # ── Layer 1: AX text read, no LLM ──────────────────────────────────────
    async def _layer_extract(self, node, app, goal, client, rec):
        """Pure read. Answers goals that are questions about on-screen state
        and nothing more. Returns a note (escalate) or AgentResult (done)."""
        if not ax_available():
            return "extract: accessibility permission not granted"
        d = rec.enter_layer("extract")
        snap = enumerate_ui(app)
        dump = snap.text_dump()
        rec.artifact("extract", "ui_text.txt", dump)

        expect = node.metadata.get("expect")
        # A read-only layer may only *answer*; it can never satisfy a goal
        # that asks to change something. `expect` is the caller's assertion
        # about the post-state, so its presence means this is a verification
        # read and a match is a genuine completion.
        if expect and expect in dump:
            return self._pack(app, goal, "extract", turns=0, content=dump,
                              trajectory=rec.root,
                              note=f"expected value {expect!r} already present")
        if node.metadata.get("read_only") and dump:
            return self._pack(app, goal, "extract", turns=0, content=dump,
                              trajectory=rec.root)
        return f"extract: read {len(snap.elements)} elements, goal needs action"

    # ── Layer 2a: deterministic hotkeys, no LLM ────────────────────────────
    async def _layer_deterministic(self, node, app, goal, client, rec):
        """Caller-supplied key sequence or AppleScript. Never guesses — the
        same discipline the browser skill applies to selectors. Guessing here
        would recreate exactly the brittleness Layer 2b exists to absorb."""
        rec.enter_layer("deterministic")
        keys = node.metadata.get("keys") or []
        script = node.metadata.get("applescript")

        if script:
            ok, out = osinput.osascript(script)
            rec.artifact("deterministic", "applescript.txt",
                         f"{script}\n\n-> ok={ok}\n{out}")
            if not ok:
                return f"deterministic: applescript failed: {out}"
            content = out
        else:
            out = osinput.press_sequence([str(k) for k in keys])
            rec.artifact("deterministic", "keys.txt",
                         f"{keys}\n\n-> {out}")
            if out.startswith("error"):
                return f"deterministic: {out}"
            content = ""

        # Verification is mandatory here, not optional. A key sequence that
        # was *delivered* is not a task that *worked*: the app may have been
        # in a different mode, or swallowed a keystroke. So we re-read the AX
        # tree and require the caller's `expect` string to appear.
        expect = node.metadata.get("expect")
        if expect is not None:
            if not ax_available():
                return ("deterministic: cannot verify without accessibility "
                        "permission")
            time.sleep(float(node.metadata.get("settle", 0.6)))
            snap = enumerate_ui(app)
            dump = snap.text_dump()
            rec.artifact("deterministic", "verify_ui_text.txt", dump)
            if expect not in dump:
                return (f"deterministic: sequence ran but verification failed "
                        f"(expected {expect!r} on screen)")
            content = dump

        return self._pack(app, goal, "deterministic",
                          turns=len(keys) or 1, content=content or None,
                          trajectory=rec.root,
                          note="verified" if node.metadata.get("expect") else "")

    # ── Layer 2c: the page tool (Electron, CDP) ────────────────────────────
    async def _layer_page(self, node, app, goal, client, rec):
        """Electron path. Reads the real DOM over `electron_debugging_port`,
        and optionally evaluates caller-supplied JS."""
        port = int(node.metadata.get("electron_debugging_port"))
        rec.enter_layer("page")
        try:
            session, target = await open_page(port, hint=node.metadata.get("page_hint", ""))
        except CDPError as e:
            # Distinct from a task failure: the app simply was not launched
            # with the debugging flag. Say so precisely — this is the single
            # most common way the Electron path fails, and a vague message
            # sends people hunting in the wrong place.
            return f"page: {e}"

        async with session:
            title = await session.title()
            rec.log("page_target", title=target.title, url=target.url[:200],
                    type=target.type)

            script = node.metadata.get("page_script")
            value = None
            if script:
                value = await session.evaluate(script)
                rec.artifact("page", "script.js",
                             f"{script}\n\n// -> {value!r}")

            text = await session.text()
            rec.artifact("page", "page_text.txt",
                         f"TITLE: {title}\nURL: {target.url}\n\n{text}")

            expect = node.metadata.get("expect")
            haystack = f"{title}\n{text}\n{value!r}"
            if expect is not None and expect not in haystack:
                return (f"page: read DOM but verification failed "
                        f"(expected {expect!r})")

            content = value if isinstance(value, str) and value else text
            return self._pack(app, goal, "page", turns=1, content=content,
                              trajectory=rec.root,
                              note=f"target={target.title!r}")

    # ── independent verification ───────────────────────────────────────────
    def _verify(self, node, rec, layer: str) -> str | None:
        """Check the world, not the model's claim. Returns None when the
        post-state is confirmed (or when the caller asked for no check), else
        a failure note.

        A driver's `done(success=true)` is a *claim*. When metadata supplies
        `verify_applescript` + `expect_verify`, the claim is tested against
        state read back out of the application — and a model driving the UI
        cannot influence that read. Without this gate, a confidently wrong
        model produces a trajectory that looks exactly like a success."""
        script = node.metadata.get("verify_applescript")
        expect = node.metadata.get("expect_verify")
        if not script or expect is None:
            return None
        ok, out = osinput.osascript(script)
        rec.artifact(layer, "verification.txt",
                     f"{script}\n\n-> ok={ok}\n{out}\n\nexpected: {expect!r}")
        rec.log("verify", layer=layer, ok=ok, got=out[:200], expected=expect)
        if not ok:
            return f"verification script failed: {out}"
        if expect not in out:
            return f"verification failed: expected {expect!r}, got {out!r}"
        return None

    # ── Layer 2b: AX tree + text LLM ───────────────────────────────────────
    async def _layer_ax(self, node, app, goal, client, rec):
        if not ax_available():
            return "ax: accessibility permission not granted"
        rec.enter_layer("ax")
        cfg = DriverConfig(goal=goal, app=app,
                           max_steps=int(node.metadata.get("max_steps_ax",
                                                           self.max_steps_ax)),
                           provider=self.ax_provider_pin)
        drv = AXDriver(client, cfg, rec)
        res: DriverResult = await drv.run()
        if not res.success:
            return f"ax: {res.note}"
        failed = self._verify(node, rec, "ax")
        if failed:
            return f"ax: {failed}"
        return self._pack_driver(app, goal, "ax", res, rec)

    # ── Layer 3: vision ────────────────────────────────────────────────────
    async def _layer_vision(self, node, app, goal, client, rec):
        rec.enter_layer("vision")
        cfg = DriverConfig(goal=goal, app=app,
                           max_steps=int(node.metadata.get(
                               "max_steps_vision", self.max_steps_vision)),
                           provider=self.vision_provider_pin)
        drv = VisionDriver(client, cfg, rec)
        res: DriverResult = await drv.run()
        if not res.success:
            return f"vision: {res.note}"
        failed = self._verify(node, rec, "vision")
        if failed:
            return f"vision: {failed}"
        return self._pack_driver(app, goal, "vision", res, rec)

    # ── packers ────────────────────────────────────────────────────────────
    def _pack(self, app, goal, path, *, turns, content=None, actions=None,
              elapsed=0.0, trajectory=None, note="") -> AgentResult:
        out = ComputerOutput(
            app=app, goal=goal, path=path, turns=turns, content=content,
            actions=actions or [], trajectory_dir=str(trajectory or ""),
            note=note,
        )
        return AgentResult(success=True, agent_name=self.NAME,
                           output=out.model_dump(), elapsed_s=elapsed)

    def _pack_driver(self, app, goal, path, res: DriverResult,
                     rec: Recorder) -> AgentResult:
        out = ComputerOutput(
            app=app, goal=goal, path=path, turns=res.turns,
            content=res.extracted or None, actions=res.actions,
            trajectory_dir=str(rec.root), note=res.note,
            vision_calls=rec.vision_calls,
        )
        return AgentResult(success=True, agent_name=self.NAME,
                           output=out.model_dump())

    def _pack_error(self, app, goal, code, msg, *, elapsed=0.0,
                    trajectory=None) -> AgentResult:
        out = ComputerOutput(
            app=app or "", goal=goal, path="extract", turns=0, content=None,
            trajectory_dir=str(trajectory or ""),
        )
        return AgentResult(success=False, agent_name=self.NAME,
                           output=out.model_dump(), error=msg,
                           error_code=code, elapsed_s=elapsed)

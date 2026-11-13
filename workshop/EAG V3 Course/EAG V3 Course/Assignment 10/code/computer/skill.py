"""Session 10 catalogue wrapper: cheap paths first, recorded cua-driver execution.

Extraction, supplied hotkeys, Electron page, AX judgment, and vision are cost
paths. The catalogue Planner decomposes goals; this skill interprets observations,
sequences actions, handles failures, and verifies the resulting state.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from pathlib import Path

from schemas import AgentResult, ComputerOutput, NodeSpec

from browser.client import V9Client
from gateway import GATEWAY_URL

from . import input as osinput
from .ax import ax_available, bind_app, enumerate_ui
from .backend import CuaDriver, CuaError, driver_scope, get_driver
from .cdp import CDPError, open_page
from .driver import AXDriver, DriverConfig, DriverResult, VisionDriver
from .recorder import Recorder, start_recording

_DESKTOP_LOCK = asyncio.Lock()


class ComputerSkill:
    NAME = "computer"

    def __init__(self, *, gateway_url: str | None = None,
                 agent_tag: str = "computer",
                 ax_provider_pin: str | None = "gemini",
                 vision_provider_pin: str | None = "gemini",
                 trajectories_root: str | None = None,
                 max_steps_ax: int = 12,
                 max_steps_vision: int = 12,
                 session: str | None = None, backend=None):
        self.gateway_url = gateway_url or GATEWAY_URL
        self.agent_tag = agent_tag
        self.ax_provider_pin = ax_provider_pin
        self.vision_provider_pin = vision_provider_pin
        self.trajectories_root = trajectories_root
        self.max_steps_ax = max_steps_ax
        self.max_steps_vision = max_steps_vision
        self.session = session
        self.backend = backend

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
    async def run(self, node: NodeSpec, *, setup=None) -> AgentResult:
        # The desktop and native recording are shared resources, even when
        # the catalogue orchestrator has several ready nodes.
        async with _DESKTOP_LOCK:
            return await self._run_recorded(node, setup)

    async def _run_recorded(self, node, setup):
        app = node.metadata.get("app", "")
        goal = node.metadata.get("goal", "inspect the screen")
        task = node.metadata.get("task", app or "computer")
        if not app:
            return self._pack_error(app, goal, "interaction_failed", "no app given (metadata.app)")
        if node.metadata.get("force_path") not in (None, "extract", "deterministic", "page", "ax", "vision"):
            return self._pack_error(app, goal, "interaction_failed", "unknown force_path")
        rec = start_recording(task, goal, root=self.trajectories_root)
        driver = self.backend or CuaDriver(session=rec.root.name)
        driver.session = rec.root.name
        started = False
        t0 = time.time()
        with driver_scope(driver):
            try:
                driver.require_daemon()
                permissions = driver.call("check_permissions", {"prompt": False})
                if (not permissions.get("accessibility") or not permissions.get("screen_recording")
                        or not permissions.get("screen_recording_capturable", True)):
                    raise PermissionError("Grant Accessibility and Screen Recording to CuaDriver.app before a recorded run")
                driver.call("start_session", {"session": driver.session})
                started = True
                driver.call("set_agent_cursor_enabled", {"enabled": True, "cursor_id": driver.session})
                rec.begin(driver)
                if setup:
                    ok, note = setup(node.metadata)
                    rec.log("setup", ok=ok, note=note)
                    if not ok:
                        raise CuaError(f"setup failed: {note}")
                    app = node.metadata["app"]
                if node.metadata.get("activate", True):
                    ok, detail = osinput.activate_app(app, pid=node.metadata.get("pid"))
                    if not ok:
                        raise CuaError(f"could not activate {app}: {detail}")
                bind_app(app, pid=node.metadata.get("pid"), window_id=node.metadata.get("window_id"))
                result = await self._cascade(node, rec)
            except PermissionError as exc:
                result = self._pack_error(app, goal, "permission_denied", str(exc), trajectory=rec.root)
            except CuaError as exc:
                result = self._pack_error(app, goal, "app_unavailable", str(exc), trajectory=rec.root)
            except Exception as exc:
                result = self._pack_error(app, goal, "interaction_failed",
                                          f"{type(exc).__name__}: {exc}", trajectory=rec.root)
            try:
                result.elapsed_s = time.time() - t0
                result.output["vision_calls"] = rec.vision_calls
                result.output["trajectory_dir"] = str(rec.root)
                rec.finish(success=result.success, path=result.output.get("path", "extract"),
                           turns=result.output.get("turns", 0), note=result.error or "verified")
            except Exception as exc:
                result.success = False
                result.error_code = "interaction_failed"
                result.error = f"Evidence could not be finalized: {exc}"
                # stop() has already cleared its active flag if it failed.
                try:
                    rec.finish(success=False, path=result.output.get("path", "extract"),
                               turns=result.output.get("turns", 0), note=result.error)
                except OSError:
                    pass  # The returned failure explicitly reports missing evidence.
            finally:
                if started:
                    try:
                        driver.call("end_session", {"session": driver.session})
                    except Exception as exc:
                        result.success = False
                        result.error_code = "interaction_failed"
                        result.error = f"Session cleanup failed: {exc}"
                        rec.finish(success=False, path=result.output.get("path", "extract"),
                                   turns=result.output.get("turns", 0), note=result.error)
            return result

    async def _cascade(self, node, rec) -> AgentResult:
        app = node.metadata.get("app") or ""
        goal = node.metadata.get("goal") or "inspect the screen"
        task = node.metadata.get("task") or (app or "computer").lower().replace(" ", "_")

        if not app:
            return self._pack_error(app, goal, "interaction_failed",
                                    "no app given (metadata.app)")

        t0 = time.time()
        client = V9Client(base_url=self.gateway_url, agent=self.agent_tag,
                          session=self.session)

        layers = self._plan_layers(node)
        rec.log("plan", layers=layers, app=app,
                electron_port=node.metadata.get("electron_debugging_port"))

        last_note = ""
        for layer in layers:
            handler = getattr(self, f"_layer_{layer}")
            try:
                result = await handler(node, app, goal, client, rec)
            except PermissionError as e:
                result = e            # handled as terminal just below
                rec.log("layer_error", layer=layer, error=str(e))
            except (CuaError, OSError):
                raise
            except Exception as e:                       # noqa: BLE001
                result = None
                last_note = f"{layer}: {type(e).__name__}: {e}"
                rec.log("layer_error", layer=layer, error=last_note)

            if isinstance(result, PermissionError):
                # Terminal, not escalatable: no later layer can succeed
                # without the grant either, and re-planning cannot obtain
                # one. Surface it to a human immediately.
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
                return result
            last_note = result

        return self._pack_error(app, goal, "interaction_failed",
                                f"all layers exhausted; last: {last_note}",
                                elapsed=time.time() - t0, trajectory=rec.root)

    # ── Layer 1: AX text read, no LLM ──────────────────────────────────────
    async def _layer_extract(self, node, app, goal, client, rec):
        """Pure read. Answers goals that are questions about on-screen state
        and nothing more. Returns a note (escalate) or AgentResult (done)."""
        rec.enter_layer("extract")
        if not ax_available():
            return "extract: accessibility permission not granted"
        snap = enumerate_ui(app)
        dump = snap.text_dump()
        rec.artifact("extract", "ui_text.txt", dump)

        expect = node.metadata.get("expect")
        # A read-only layer may only *answer*; it can never satisfy a goal
        # that asks to change something. `expect` is the caller's assertion
        # about the post-state, so its presence means this is a verification
        # read and a match is a genuine completion.
        if (node.metadata.get("read_only") and expect and expect in dump
                and not node.metadata.get("electron_debugging_port")):
            return self._pack(app, goal, "extract", turns=0, content=dump,
                              trajectory=rec.root,
                              note=f"expected value {expect!r} already present")
        if node.metadata.get("read_only") and dump and (expect is None or expect in dump):
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
            # Re-scan after each key, preserving scan → act → verify.
            for index, key in enumerate(keys):
                osinput.press_key(str(key))
                time.sleep(float(node.metadata.get("settle", 0.12)))
                snap = enumerate_ui(app)
                rec.artifact("deterministic", f"key_{index:02d}_verify.txt", snap.text_dump())
            out = "ok"
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
            if not self._matches(expect, dump):
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

            text = "" if script else await session.text()
            rec.artifact("page", "page_text.txt",
                         f"TITLE: {title}\nURL: {target.url}\n\n{text}")

            expect = node.metadata.get("expect")
            expected_tab = node.metadata.get("expect_active_tab")
            if expected_tab:
                parsed_value = json.loads(value) if isinstance(value, str) else value
                if not isinstance(parsed_value, dict) or parsed_value.get("active_tab") != expected_tab:
                    return f"page: active tab is not {expected_tab!r}"
                rec.artifact("page", "verification.json", json.dumps(parsed_value, indent=2))
            haystack = f"{title}\n{text}\n{value!r}"
            if expect is not None and expect not in haystack:
                return (f"page: read DOM but verification failed "
                        f"(expected {expect!r})")

            content = value if isinstance(value, str) else json.dumps(value) if value is not None else text
            return self._pack(app, goal, "page", turns=1, content=content,
                              trajectory=rec.root,
                              note=f"target={target.title!r}")

    @staticmethod
    def _matches(expected, text):
        if str(expected).isdigit():
            return re.search(rf"(?<![\w.]){re.escape(str(expected))}(?![\w.])", text) is not None
        return str(expected) in text

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
        expected_title = node.metadata.get("expect_window_title")
        if expected_title:
            driver = get_driver()
            windows = driver.call("list_windows", {"pid": driver.target["pid"]}).get("windows", [])
            target = next((w for w in windows if w["window_id"] == driver.target["window_id"]), {})
            title = target.get("title", "")
            rec.artifact(layer, "verification.txt", f"Window title: {title}\nExpected: {expected_title}")
            rec.artifact(layer, "verification.json", json.dumps({"actual": title, "expected": expected_title,
                                                                  "success": expected_title in title}))
            if expected_title not in title:
                return f"verification failed: expected title {expected_title!r}, got {title!r}"
            return None
        script = node.metadata.get("verify_applescript")
        expect = node.metadata.get("expect_verify")
        if not script or expect is None:
            expected = node.metadata.get("expect")
            if expected is None:
                return "no independent postcondition supplied"
            return None if self._matches(expected, enumerate_ui(node.metadata["app"]).text_dump()) else "expected state absent"
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
        rec.enter_layer("ax")
        if not ax_available():
            return "ax: accessibility permission not granted"
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

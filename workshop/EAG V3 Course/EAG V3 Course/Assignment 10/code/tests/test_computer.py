"""Assignment examples, with a fake desktop so tests never operate the Mac."""
import asyncio
import base64
import io
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from jsonschema import validate
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from schemas import NodeSpec
from computer.backend import CuaDriver, CuaError, driver_scope
from computer.ax import bind_app, enumerate_ui
from computer.driver import ACTION_SCHEMA, dispatch
from computer.recorder import start_recording
from computer.skill import ComputerSkill
from computer import run as runner

DRIVER_SCHEMAS = yaml.safe_load((Path(__file__).parent / "fixtures/cua_driver_0_5_2.yaml").read_text())["tools"]


@pytest.fixture(autouse=True)
def no_real_desktop_or_network(monkeypatch):
    import httpx
    def forbidden(*args, **kwargs):
        pytest.fail("Offline tests must not invoke real processes or HTTP requests")
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(httpx, "get", forbidden)
    monkeypatch.setattr(httpx, "post", forbidden)
    monkeypatch.setattr(httpx.AsyncClient, "post", forbidden)


class FakeDesktop(CuaDriver):
    def __init__(self):
        self.calls = []
        self.session = "test"
        self.target = None
        self.recording = False
        self.tree = '- [element_index 19] AXButton "Equals"\n- AXStaticText = "0"'
        self.title = "CANVAS-GAME: READY"
        self.keys = []
        image = io.BytesIO()
        Image.new("RGB", (720, 440), "#1a2030").save(image, format="PNG")
        self.image = base64.b64encode(image.getvalue()).decode()
        self.permissions = {"accessibility": True, "screen_recording": True}

    def require_daemon(self):
        pass

    def call(self, tool, args=None):
        args = args or {}
        validate(args, DRIVER_SCHEMAS[tool])
        self.calls.append((tool, dict(args)))
        if tool == "check_permissions":
            assert args == {"prompt": False}
            return self.permissions
        if tool == "get_recording_state":
            return {"enabled": self.recording}
        if tool == "start_recording":
            self.recording = True
            return {"enabled": True}
        if tool == "stop_recording":
            self.recording = False
            return {"enabled": False, "last_error": None}
        if tool == "list_windows":
            return {"windows": [{"pid": 42, "window_id": 7, "app_name": "Test",
                                  "title": self.title, "is_on_screen": True}]}
        if tool == "launch_app":
            return {"pid": 42, "windows": [{"window_id": 7}]}
        if tool == "get_window_state":
            snapshot = {"pid": 42, "window_id": 7, "element_count": 1,
                        "tree_markdown": self.tree}
            if args.get("capture_mode") != "ax":
                snapshot.update(screenshot_png_b64=self.image,
                                screenshot_width=720, screenshot_height=440)
            return snapshot
        if tool == "press_key":
            self.keys.append("*" if args["key"] == "8" and args.get("modifiers") == ["shift"] else args["key"])
            if args["key"] == "=":
                self.tree = '- AXStaticText = "611"'
        if tool == "page":
            assert args["action"] == "execute_javascript"
            return json.dumps({"active_tab": "s10_marker.txt", "title": "Test"})
        if tool == "click":
            self.title = "CANVAS-GAME: HIT"
        return {}


def node(**metadata):
    return NodeSpec(skill="computer", metadata={"app": "Test", "goal": "test", **metadata})


def test_transport_requires_a_daemon_before_any_action():
    commands = []
    def run(args, **kwargs):
        commands.append(args)
        return subprocess.CompletedProcess(args, 1, "", "daemon unavailable")
    driver = CuaDriver(binary="fake-driver", run=run)
    with pytest.raises(CuaError, match="daemon"):
        driver.call("click", {"pid": 42, "x": 20, "y": 30})
    assert commands == [["fake-driver", "status"]]


def test_transport_passes_json_and_rejects_in_process_fallback():
    commands = []
    def run(args, **kwargs):
        commands.append(args)
        if args[1] == "status":
            return subprocess.CompletedProcess(args, 0, "running", "")
        return subprocess.CompletedProcess(args, 0, '{}', "running 'click' in-process")
    driver = CuaDriver(binary="fake-driver", run=run, session="s10")
    with pytest.raises(CuaError, match="in-process"):
        driver.call("click", {"pid": 42, "window_id": 7, "element_index": 19})
    payload = json.loads(commands[-1][-1])
    assert payload == {"pid": 42, "window_id": 7, "element_index": 19, "session": "s10"}


def test_ax_preserves_driver_indices():
    desktop = FakeDesktop()
    with driver_scope(desktop):
        bind_app("Test", pid=42)
        snap = enumerate_ui("Test")
    assert snap.by_id(19).name == "Equals"
    assert snap.by_id(1) is None
    assert snap.pid == 42 and snap.window_id == 7


def test_coordinate_click_reaches_canvas():
    desktop = FakeDesktop()
    with driver_scope(desktop):
        bind_app("Test", pid=42)
        snap = enumerate_ui("Test")
        assert dispatch({"type": "click", "x": 525, "y": 175}, snap) == "ok"
    assert desktop.calls[-1] == ("click", {"pid": 42, "window_id": 7, "x": 525, "y": 175})
    props = ACTION_SCHEMA["properties"]["actions"]["items"]["properties"]
    assert "x" in props and "y" in props


@pytest.mark.asyncio
async def test_calculator_611_uses_no_model_and_records_turns(tmp_path):
    desktop = FakeDesktop()
    result = await ComputerSkill(trajectories_root=str(tmp_path), backend=desktop).run(
        node(task="calculator", pid=42, keys=["4", "7", "*", "1", "3", "="],
             expect="611", activate=False, settle=0))
    assert result.success, result.error
    assert result.output["path"] == "deterministic"
    assert result.output["vision_calls"] == 0
    manifest = json.loads((Path(result.output["trajectory_dir"]) / "manifest.json").read_text())
    assert manifest["turns"] == 6
    assert manifest["layers_attempted"] == ["extract", "deterministic"]
    assert manifest["driver_recording"] is True
    tools = [name for name, _ in desktop.calls]
    assert tools.index("start_recording") < tools.index("press_key") < tools.index("stop_recording")
    assert tools[-1] == "end_session"
    assert not desktop.recording


@pytest.mark.asyncio
async def test_electron_requires_active_marker_not_any_open_tab(tmp_path):
    desktop = FakeDesktop()
    result = await ComputerSkill(trajectories_root=str(tmp_path), backend=desktop).run(
        node(pid=42, task="vscode", electron_debugging_port=9222,
             page_script="read-active-tab", expect="s10_marker.txt",
             expect_active_tab="s10_marker.txt", activate=False))
    assert result.success, result.error
    assert result.output["path"] == "page"
    assert result.output["vision_calls"] == 0
    assert any(tool == "page" for tool, _ in desktop.calls)


@pytest.mark.asyncio
async def test_missing_accessibility_stops_before_setup_or_input(tmp_path):
    desktop = FakeDesktop()
    desktop.permissions["accessibility"] = False
    def setup(meta):
        pytest.fail("Setup must not run without permission")
    result = await ComputerSkill(trajectories_root=str(tmp_path), backend=desktop).run(
        node(pid=42, keys=["4"], activate=False), setup=setup)
    assert not result.success
    assert result.error_code == "permission_denied"
    assert not any(tool in {"press_key", "click", "launch_app"} for tool, _ in desktop.calls)


@pytest.mark.asyncio
async def test_failed_setup_still_finishes_recording(tmp_path):
    desktop = FakeDesktop()
    result = await ComputerSkill(trajectories_root=str(tmp_path), backend=desktop).run(
        node(pid=42, activate=False), setup=lambda meta: (False, "test failure"))
    assert not result.success
    assert result.error_code == "app_unavailable"
    assert not desktop.recording
    assert (Path(result.output["trajectory_dir"]) / "manifest.json").exists()


def test_recorder_never_reuses_a_directory(tmp_path):
    first = start_recording("calculator", "47 * 13", root=tmp_path)
    second = start_recording("calculator", "47 * 13", root=tmp_path)
    assert first.root != second.root


def test_recording_errors_are_not_silently_accepted(tmp_path):
    recorder = start_recording("test", "test", root=tmp_path)
    # An invalid destination must be reported rather than inventing evidence.
    (recorder.root / "blocked").write_text("file")
    with pytest.raises(OSError):
        recorder.artifact("blocked/child", "proof.txt", "test")


@pytest.mark.asyncio
async def test_unknown_task_cannot_launch_all_tasks(monkeypatch):
    monkeypatch.setattr(runner, "preflight", lambda: pytest.fail("Unexpected desktop check"))
    assert await runner.main(["caluclator"]) == 2


def test_constraints_require_three_distinct_tasks():
    results = [{"task": "calculator", "success": True, "layer": "deterministic", "vision_calls": 0}]
    assert not runner.constraints_pass(results)
    results += [{"task": "vscode", "success": True, "layer": "page", "vision_calls": 0},
                {"task": "canvas", "success": True, "layer": "vision", "vision_calls": 1}]
    assert runner.constraints_pass(results)


@pytest.mark.asyncio
async def test_existing_611_cannot_bypass_computation(tmp_path):
    desktop = FakeDesktop()
    desktop.tree = '- AXStaticText = "611"'
    result = await ComputerSkill(trajectories_root=str(tmp_path), backend=desktop).run(
        node(pid=42, keys=["4", "7", "*", "1", "3", "="], expect="611", activate=False, settle=0))
    assert result.success
    assert desktop.keys == ["4", "7", "*", "1", "3", "="]
    assert result.output["path"] == "deterministic"


@pytest.mark.asyncio
async def test_wrong_active_tab_fails_even_if_marker_is_open(tmp_path):
    desktop = FakeDesktop()
    original = desktop.call
    def call(tool, args=None):
        if tool == "page":
            return {"active_tab": "wrong.txt", "tabs": ["s10_marker.txt"]}
        return original(tool, args)
    desktop.call = call
    result = await ComputerSkill(trajectories_root=str(tmp_path), backend=desktop).run(
        node(pid=42, force_path="page", electron_debugging_port=9222,
             page_script="read-active-tab", expect_active_tab="s10_marker.txt", activate=False))
    assert not result.success
    assert "active tab" in result.error


def model_result(actions):
    return SimpleNamespace(parsed={"thinking": "test", "actions": actions}, text="",
                           provider="test", model="test", latency_ms=0, input_tokens=0, output_tokens=0)


@pytest.mark.asyncio
async def test_canvas_naturally_escalates_then_verifies_title(tmp_path, monkeypatch):
    from browser.client import V9Client
    desktop = FakeDesktop()
    vision_turns = []
    async def chat(*args, **kwargs):
        return model_result([{"type": "escalate", "note": "canvas target is absent from AX"}])
    async def vision(*args, **kwargs):
        vision_turns.append(True)
        return model_result([{"type": "click", "x": 525, "y": 175}] if len(vision_turns) == 1
                            else [{"type": "done", "success": True}])
    monkeypatch.setattr(V9Client, "chat", chat)
    monkeypatch.setattr(V9Client, "vision", vision)
    result = await ComputerSkill(trajectories_root=str(tmp_path), backend=desktop).run(
        node(pid=42, task="canvas", expect_window_title="CANVAS-GAME: HIT", activate=False))
    assert result.success, result.error
    assert result.output["path"] == "vision"
    assert result.output["vision_calls"] == 2
    manifest = json.loads((Path(result.output["trajectory_dir"]) / "manifest.json").read_text())
    assert manifest["layers_attempted"] == ["extract", "ax", "vision"]
    assert manifest["text_llm_calls"] == 1
    calls = [name for name, _ in desktop.calls]
    click = calls.index("click")
    assert calls[click - 1] == "get_window_state"
    assert calls[click + 1] == "get_window_state"


@pytest.mark.asyncio
async def test_model_success_is_not_proof_of_canvas_success(tmp_path, monkeypatch):
    from browser.client import V9Client
    async def vision(*args, **kwargs):
        return model_result([{"type": "done", "success": True}])
    monkeypatch.setattr(V9Client, "vision", vision)
    result = await ComputerSkill(trajectories_root=str(tmp_path), backend=FakeDesktop()).run(
        node(pid=42, force_path="vision", expect_window_title="CANVAS-GAME: HIT", activate=False))
    assert not result.success
    assert "verification failed" in result.error


@pytest.mark.asyncio
async def test_action_batch_is_rejected_before_clicking(tmp_path, monkeypatch):
    from browser.client import V9Client
    desktop = FakeDesktop()
    async def vision(*args, **kwargs):
        return model_result([{"type": "click", "x": 525, "y": 175},
                             {"type": "done", "success": True}])
    monkeypatch.setattr(V9Client, "vision", vision)
    result = await ComputerSkill(trajectories_root=str(tmp_path), backend=desktop).run(
        node(pid=42, force_path="vision", expect_window_title="CANVAS-GAME: HIT", activate=False))
    assert not result.success
    assert not any(tool == "click" for tool, _ in desktop.calls)


def test_screenshot_annotation_preserves_coordinate_space():
    from computer.screen import annotate
    original = io.BytesIO()
    Image.new("RGB", (2880, 1800)).save(original, format="PNG")
    marked = annotate(original.getvalue())
    assert Image.open(io.BytesIO(marked)).size == (2880, 1800)


@pytest.mark.asyncio
async def test_dry_run_never_checks_or_operates_desktop(monkeypatch, capsys):
    monkeypatch.setattr(runner, "preflight", lambda: pytest.fail("No preflight in plan mode"))
    monkeypatch.setattr(runner, "run_task", lambda name: pytest.fail("No task in plan mode"))
    assert await runner.main(["--dry-run"]) == 0
    assert "PLAN ONLY" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_existing_recording_is_not_overwritten(tmp_path):
    desktop = FakeDesktop()
    desktop.recording = True
    result = await ComputerSkill(trajectories_root=str(tmp_path), backend=desktop).run(
        node(pid=42, activate=False))
    assert not result.success
    assert desktop.recording
    assert not any(tool in {"start_recording", "stop_recording"} for tool, _ in desktop.calls)


@pytest.mark.asyncio
async def test_recording_finalization_failure_marks_run_failed(tmp_path):
    desktop = FakeDesktop()
    original = desktop.call
    def call(tool, args=None):
        if tool == "stop_recording":
            original(tool, args)
            return {"enabled": False, "last_error": "screenshot write failed"}
        return original(tool, args)
    desktop.call = call
    result = await ComputerSkill(trajectories_root=str(tmp_path), backend=desktop).run(
        node(pid=42, keys=["="], expect="611", activate=False, settle=0))
    assert not result.success
    manifest = json.loads((Path(result.output["trajectory_dir"]) / "manifest.json").read_text())
    assert manifest["success"] is False


@pytest.mark.asyncio
async def test_computer_is_registered_and_dispatches_through_catalogue(monkeypatch):
    from schemas import AgentResult
    from skills import SkillRegistry, run_skill
    registry = SkillRegistry()
    assert "computer" in registry.names()
    assert "computer" in registry.get("planner").prompt_template()
    received = []
    async def fake_run(self, spec):
        received.append(spec)
        return AgentResult(success=True, agent_name="computer", output={"content": "611"})
    monkeypatch.setattr(ComputerSkill, "run", fake_run)
    graph = {"n:1": {"inputs": [], "metadata": {"app": "Calculator", "goal": "47 * 13", "expect": "611"}}}
    result, _ = await run_skill(registry.get("computer"), "n:1", graph, "offline-test", "47 * 13", None)
    assert result.success and received[0].metadata["expect"] == "611"


@pytest.mark.parametrize("code", ["permission_denied", "app_unavailable"])
def test_setup_errors_do_not_trigger_planner_recovery(code):
    from recovery import plan_recovery
    result = plan_recovery(failed_skill="computer", error_text="setup required",
                           failed_node_id="n:1", error_code=code)
    assert result.action == "skip"
    assert result.failure_report is None


def test_evidence_checker_reports_missing_live_runs(tmp_path):
    from computer.evidence import check
    errors = check(tmp_path)
    assert len(errors) == 1 and "live-run summary" in errors[0]


def test_evidence_checker_rejects_path_escape(tmp_path):
    from computer.evidence import check
    (tmp_path / "summary.json").write_text(json.dumps([
        {"task": task, "trajectory_dir": "../outside"} for task in TASK_NAMES]))
    errors = check(tmp_path)
    assert len(errors) == 3 and all("relative path" in error for error in errors)


TASK_NAMES = ["calculator", "vscode", "canvas"]


def test_multiply_uses_shift_8_supported_by_the_pinned_driver():
    from computer.input import press_key
    desktop = FakeDesktop()
    with driver_scope(desktop):
        bind_app("Test", pid=42)
        press_key("*")
    assert desktop.calls[-1] == ("press_key", {"pid": 42, "window_id": 7,
                                              "key": "8", "modifiers": ["shift"]})


@pytest.mark.parametrize("actual", ['AXStaticText = "1611"', 'AXStaticText = "611.5"'])
def test_calculator_verification_rejects_partial_numeric_matches(actual):
    assert not ComputerSkill._matches("611", actual)


def test_driver_path_can_come_from_dotenv_environment(monkeypatch):
    monkeypatch.setenv("CUA_DRIVER_PATH", "/example/CuaDriver.app/Contents/MacOS/cua-driver")
    assert CuaDriver().binary == "/example/CuaDriver.app/Contents/MacOS/cua-driver"


def test_evidence_checker_accepts_complete_fixture_and_rejects_counter_tampering(tmp_path):
    # Synthetic evidence exists only in pytest's temporary directory.
    from computer.evidence import check, LAYERS
    from computer.tasks import TASKS
    from computer.input import key_arguments
    rows = []
    for task in TASK_NAMES:
        directory = tmp_path / task
        native = directory / "driver"
        native.mkdir(parents=True)
        calls = 2 if task == "canvas" else 0
        turns = len(TASKS[task]["keys"]) if task == "calculator" else 2 if task == "canvas" else 1
        manifest = {"success": True, "resolved_at_layer": LAYERS[task], "vision_calls": calls,
                    "turns": turns, "driver_recording": True}
        (directory / "manifest.json").write_text(json.dumps(manifest))
        (directory / "driver_recording_state.json").write_text(json.dumps({"enabled": False, "last_error": None}))
        events = [{"kind": "llm_call", "layer": "vision"}] * calls
        (directory / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events))
        if task == "calculator":
            for i, key in enumerate(TASKS[task]["keys"], 1):
                turn = native / f"turn-{i:05d}"
                turn.mkdir()
                (turn / "action.json").write_text(json.dumps({"tool": "press_key", "arguments": key_arguments(key)}))
                Image.new("RGB", (4, 4)).save(turn / "screenshot.png")
        else:
            layer = directory / ("layer_2c_page" if task == "vscode" else "layer_3_vision")
            layer.mkdir()
            proof = {"active_tab": "s10_marker.txt"} if task == "vscode" else {"actual": "CANVAS-GAME: HIT", "success": True}
            (layer / "verification.json").write_text(json.dumps(proof))
            if task == "canvas":
                Image.new("RGB", (4, 4)).save(layer / "turn_01_screen.png")
        rows.append({"task": task, "success": True, "layer": LAYERS[task], "vision_calls": calls,
                     "turns": turns, "trajectory_dir": task})
    (tmp_path / "summary.json").write_text(json.dumps(rows))
    assert check(tmp_path) == []
    manifest_path = tmp_path / "canvas/manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["vision_calls"] = 0
    manifest_path.write_text(json.dumps(manifest))
    assert any("counters disagree" in error for error in check(tmp_path))


@pytest.mark.asyncio
async def test_full_run_fails_if_all_tasks_pass_without_required_vision(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "preflight", lambda: {"driver": True, "accessibility": True, "screen_recording": True})
    monkeypatch.setattr(runner, "TRAJ_ROOT", tmp_path)
    async def task(name):
        return {"task": name, "success": True, "layer": "page" if name == "vscode" else "deterministic", "vision_calls": 0}
    monkeypatch.setattr(runner, "run_task", task)
    assert await runner.main([]) == 1


def test_canvas_uses_a_new_profile_for_each_run(tmp_path, monkeypatch):
    desktop = FakeDesktop()
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner.time, "sleep", lambda seconds: None)
    with driver_scope(desktop):
        assert runner.setup_canvas({})[0]
        assert runner.setup_canvas({})[0]
    profiles = [args["additional_arguments"][0] for tool, args in desktop.calls if tool == "launch_app"]
    assert len(profiles) == 2 and profiles[0] != profiles[1]


def test_editor_run_moves_to_the_next_free_port_when_the_usual_one_is_busy(tmp_path, monkeypatch):
    """A previous editor run leaves its window open and its port in use."""
    desktop = FakeDesktop()
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(runner.Path, "exists", lambda self: True)
    monkeypatch.setattr(runner, "_port_free", lambda port: port != 9222)
    meta = {"electron_debugging_port": 9222}
    with driver_scope(desktop):
        ok, note = runner.setup_vscode(meta)
    assert ok and "9223" in note
    assert meta["electron_debugging_port"] == 9223
    launch = next(args for tool, args in desktop.calls if tool == "launch_app")
    assert launch["electron_debugging_port"] == 9223


def test_editor_run_never_attaches_to_a_busy_port(tmp_path, monkeypatch):
    desktop = FakeDesktop()
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "_port_free", lambda port: False)
    with driver_scope(desktop):
        ok, note = runner.setup_vscode({"electron_debugging_port": 9222})
    assert not ok
    assert not any(tool == "launch_app" for tool, _ in desktop.calls)


@pytest.mark.asyncio
async def test_single_task_rerun_keeps_the_other_tasks_in_the_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "preflight", lambda: {"driver": True, "accessibility": True, "screen_recording": True})
    monkeypatch.setattr(runner, "TRAJ_ROOT", tmp_path)
    (tmp_path / "summary.json").write_text(json.dumps([
        {"task": name, "success": True, "trajectory_dir": f"{name}_old"} for name in ("calculator", "vscode", "canvas")]))
    async def task(name):
        return {"task": name, "success": True, "layer": "deterministic", "vision_calls": 0,
                "trajectory_dir": str(tmp_path / f"{name}_new")}
    monkeypatch.setattr(runner, "run_task", task)
    assert await runner.main(["calculator"]) == 0
    rows = {row["task"]: row["trajectory_dir"] for row in json.loads((tmp_path / "summary.json").read_text())}
    assert rows == {"calculator": "calculator_new", "vscode": "vscode_old", "canvas": "canvas_old"}

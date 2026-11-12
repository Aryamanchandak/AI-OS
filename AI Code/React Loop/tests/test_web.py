import json

from fastapi.testclient import TestClient

from react_loop.loop import LoopResult
from react_loop.trace import TraceEntry, Trajectory
from react_loop.web import _session, app


def setup_function():
    _session["runs"] = []
    app.state._state.pop("run_task", None)
    app.state._state.pop("run_loop", None)


def test_root_serves_frontend():
    client = TestClient(app)

    res = client.get("/")

    assert res.status_code == 200
    assert "React Loop" in res.text


def test_run_uses_injected_runner_and_stores_state():
    async def fake_runner(task: str) -> LoopResult:
        trajectory = Trajectory(task)
        trajectory.add(TraceEntry(
            kind="action",
            step=1,
            thought="use a tool",
            tool="calculator",
            tool_input={"expression": "2+2"},
            observation="4",
        ))
        trajectory.add(TraceEntry(
            kind="final",
            step=2,
            thought="done",
            final_answer="The answer is 4.",
        ))
        return LoopResult("The answer is 4.", "final_answer", trajectory)

    app.state.run_task = fake_runner
    client = TestClient(app)

    res = client.post("/api/run", json={"task": "what is 2+2?"})

    assert res.status_code == 200
    data = res.json()
    assert data["final_answer"] == "The answer is 4."
    assert data["stop_reason"] == "final_answer"
    assert data["trajectory"][0]["tool"] == "calculator"

    state = client.get("/api/state").json()
    assert len(state["runs"]) == 1
    assert state["runs"][0]["task"] == "what is 2+2?"


def test_new_session_clears_run_history():
    _session["runs"] = [{"task": "old"}]
    client = TestClient(app)

    res = client.post("/api/new_session")

    assert res.status_code == 200
    assert res.json() == {"runs": []}
    assert client.get("/api/state").json() == {"runs": []}


def test_latest_ui_returns_404_when_snapshot_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("CRUD_FILES_DIR", str(tmp_path))
    client = TestClient(app)

    res = client.get("/ui/latest")

    assert res.status_code == 404
    assert "No UI has been generated yet" in res.text


def test_latest_ui_serves_generated_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("CRUD_FILES_DIR", str(tmp_path))
    from simple_server.tools.generative_ui import render_ui

    render_ui("""
from prefab_ui.app import PrefabApp
from prefab_ui.components import Column, Text

with PrefabApp() as app:
    with Column():
        Text("latest-route-check")
""")
    client = TestClient(app)

    res = client.get("/ui/latest")

    assert res.status_code == 200
    assert "latest-route-check" in res.text


def test_run_ui_returns_404_for_unknown_run_id(tmp_path, monkeypatch):
    monkeypatch.setenv("CRUD_FILES_DIR", str(tmp_path))
    client = TestClient(app)

    res = client.get("/ui/runs/deadbeef0000")

    assert res.status_code == 404


def test_run_ui_rejects_malformed_run_id(tmp_path, monkeypatch):
    monkeypatch.setenv("CRUD_FILES_DIR", str(tmp_path))
    client = TestClient(app)

    res = client.get("/ui/runs/../../etc/passwd")

    assert res.status_code == 404


def test_run_payload_has_null_ui_snapshot_without_a_render_ui_call():
    async def fake_runner(task: str) -> LoopResult:
        trajectory = Trajectory(task)
        trajectory.add(TraceEntry(kind="final", step=1, thought="done", final_answer="42"))
        return LoopResult("42", "final_answer", trajectory)

    app.state.run_task = fake_runner
    client = TestClient(app)

    res = client.post("/api/run", json={"task": "what is 6*7?"})

    data = res.json()
    assert data["ui_snapshot"] is None
    assert data["run_id"]


def test_run_persists_and_serves_its_own_ui_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("CRUD_FILES_DIR", str(tmp_path))
    from simple_server.tools.generative_ui import render_ui

    render_ui("""
from prefab_ui.app import PrefabApp
from prefab_ui.components import Column, Text

with PrefabApp() as app:
    with Column():
        Text("run-snapshot-check")
""")

    async def fake_runner(task: str) -> LoopResult:
        trajectory = Trajectory(task)
        trajectory.add(TraceEntry(
            kind="action",
            step=1,
            thought="build it",
            tool="render_ui",
            tool_input={"code": "..."},
            observation="UI rendered successfully.\nView it: http://x/ui/latest",
        ))
        trajectory.add(TraceEntry(kind="final", step=2, thought="done", final_answer="Built it."))
        return LoopResult("Built it.", "final_answer", trajectory)

    app.state.run_task = fake_runner
    client = TestClient(app)

    res = client.post("/api/run", json={"task": "build a dashboard"})
    data = res.json()

    assert data["ui_snapshot"] == f"/ui/runs/{data['run_id']}"

    ui_res = client.get(data["ui_snapshot"])
    assert ui_res.status_code == 200
    assert "run-snapshot-check" in ui_res.text


def test_run_stream_yields_steps_then_a_final_line_with_ui_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv("CRUD_FILES_DIR", str(tmp_path))
    from simple_server.tools.generative_ui import render_ui

    render_ui("""
from prefab_ui.app import PrefabApp
from prefab_ui.components import Column, Text

with PrefabApp() as app:
    with Column():
        Text("stream-snapshot-check")
""")

    async def fake_run_loop(task, on_entry):
        trajectory = Trajectory(task)
        step = TraceEntry(
            kind="action",
            step=1,
            thought="build it",
            tool="render_ui",
            tool_input={"code": "..."},
            observation="UI rendered successfully.\nView it: http://x/ui/latest",
        )
        trajectory.add(step)
        if on_entry:
            on_entry(step)
        final = TraceEntry(kind="final", step=2, thought="done", final_answer="Built it.")
        trajectory.add(final)
        if on_entry:
            on_entry(final)
        return LoopResult("Built it.", "final_answer", trajectory)

    app.state.run_loop = fake_run_loop
    client = TestClient(app)

    with client.stream("POST", "/api/run/stream", json={"task": "build a dashboard"}) as res:
        lines = [json.loads(line) for line in res.iter_lines() if line]

    assert res.status_code == 200
    assert [line["type"] for line in lines] == ["step", "step", "final"]
    assert lines[0]["entry"]["tool"] == "render_ui"

    final = lines[-1]
    assert final["final_answer"] == "Built it."
    assert final["ui_snapshot"] == f"/ui/runs/{final['run_id']}"

    ui_res = client.get(final["ui_snapshot"])
    assert "stream-snapshot-check" in ui_res.text

    state = client.get("/api/state").json()
    assert state["runs"][-1]["run_id"] == final["run_id"]


def test_run_stream_surfaces_errors_as_an_error_line():
    async def failing_run_loop(task, on_entry):
        raise RuntimeError("OPENAI_API_KEY is not set.")

    app.state.run_loop = failing_run_loop
    client = TestClient(app)

    with client.stream("POST", "/api/run/stream", json={"task": "anything"}) as res:
        lines = [json.loads(line) for line in res.iter_lines() if line]

    assert len(lines) == 1
    assert lines[0]["type"] == "error"
    assert "OPENAI_API_KEY" in lines[0]["detail"]

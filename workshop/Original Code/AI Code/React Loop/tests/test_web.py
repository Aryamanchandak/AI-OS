from fastapi.testclient import TestClient

from react_loop.loop import LoopResult
from react_loop.trace import TraceEntry, Trajectory
from react_loop.web import _session, app


def setup_function():
    _session["runs"] = []
    app.state._state.pop("run_task", None)


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

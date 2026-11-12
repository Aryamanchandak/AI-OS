from __future__ import annotations

from pathlib import Path

import s13code.routes as agent_route
from s13code.core.memory.embeddings import DeterministicEmbedder


PROMPT = (
    "My mom's birthday is 15 May 2026. Remember that and give me a calendar "
    "reminder for two weeks before and on the day."
)
SCOPE = {"tenant_id": "synthetic-acme", "project_id": "synthetic-family", "user_id": "student-01"}


def _start_waiting_run(app_client):
    app_client.app.state.s13_runtime.memory.embedder = DeterministicEmbedder(128)
    response = app_client.post("/v1/agent/runs", json={**SCOPE, "prompt": PROMPT})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "waiting_for_approval"
    assert body["graph"]["nodes"]["approval"]["state"] == "waiting"
    assert "reminder" not in body["graph"]["nodes"]
    return body


def test_side_effect_is_created_only_after_bound_human_approval(app_client, monkeypatch):
    async def fake_gateway(_app, _prompt, _system):
        return {"text": "The approved calendar reminders were created.",
                "provider": "deterministic-proof", "model": "fixture-v1"}

    monkeypatch.setattr(agent_route, "gateway_text_llm", fake_gateway)
    waiting = _start_waiting_run(app_client)
    approval = waiting["approvals"][0]
    request = {**SCOPE, "decision": "approved", "reviewer_id": "reviewer-01",
               "idempotency_key": "approval-proof-0001",
               "expected_sequence": approval["expected_sequence"]}
    response = app_client.post(
        f"/v1/agent/runs/{waiting['run_id']}/approvals/approval", json=request
    )
    assert response.status_code == 200
    completed = response.json()
    assert completed["status"] == "completed"
    assert completed["approval_event"] == {"accepted": True, "duplicate": False}
    assert completed["graph"]["nodes"]["reminder"]["state"] == "succeeded"
    artifacts = completed["graph"]["nodes"]["reminder"]["result"]["artifacts"]
    assert len(artifacts) == 2
    assert all(Path(uri.removeprefix("file://")).is_file() for uri in artifacts)
    approval_event_index = next(i for i, event in enumerate(completed["events"])
                                if event["node_id"] == "approval" and event["kind"] == "task_succeeded")
    reminder_add_index = next(i for i, event in enumerate(completed["events"])
                              if event["kind"] == "graph_patched" and event["payload"]["add"] == ["reminder"])
    assert approval_event_index < reminder_add_index


def test_duplicate_approval_replay_is_suppressed_without_new_events(app_client, monkeypatch):
    async def fake_gateway(_app, _prompt, _system):
        return {"text": "Created.", "provider": "deterministic-proof", "model": "fixture-v1"}

    monkeypatch.setattr(agent_route, "gateway_text_llm", fake_gateway)
    waiting = _start_waiting_run(app_client)
    request = {**SCOPE, "decision": "approved", "reviewer_id": "reviewer-01",
               "idempotency_key": "approval-proof-0002",
               "expected_sequence": waiting["approvals"][0]["expected_sequence"]}
    url = f"/v1/agent/runs/{waiting['run_id']}/approvals/approval"
    first = app_client.post(url, json=request).json()
    replay = app_client.post(url, json=request)
    assert replay.status_code == 200
    assert replay.json()["approval_event"] == {"accepted": False, "duplicate": True}
    assert len(replay.json()["events"]) == len(first["events"])
    assert replay.json()["graph"]["nodes"]["reminder"]["result"] == first["graph"]["nodes"]["reminder"]["result"]


def test_wrong_scope_and_stale_approval_cannot_advance_graph(app_client):
    waiting = _start_waiting_run(app_client)
    sequence = waiting["approvals"][0]["expected_sequence"]
    url = f"/v1/agent/runs/{waiting['run_id']}/approvals/approval"
    wrong_scope = app_client.post(url, json={**SCOPE, "tenant_id": "synthetic-competitor",
        "decision": "approved", "reviewer_id": "reviewer-evil",
        "idempotency_key": "approval-attack-01", "expected_sequence": sequence})
    assert wrong_scope.status_code == 403
    stale = app_client.post(url, json={**SCOPE, "decision": "approved", "reviewer_id": "reviewer-01",
        "idempotency_key": "approval-attack-02", "expected_sequence": sequence - 1})
    assert stale.status_code == 409
    persisted = app_client.get(f"/v1/agent/runs/{waiting['run_id']}").json()
    assert persisted["nodes"]["approval"]["state"] == "waiting"
    assert "reminder" not in persisted["nodes"]

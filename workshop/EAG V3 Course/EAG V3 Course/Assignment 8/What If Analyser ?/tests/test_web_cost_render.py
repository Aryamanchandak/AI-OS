"""Render-level checks for the completed-run cost disclosure."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient

import web.app as web_app
from engine.presentation import all_assignments, scenario_name
from engine.propagate import propagate
from engine.schema import (
    AdjudicationReport,
    Edge,
    Graph,
    GraphCritique,
    GraphDiff,
    Node,
    Unknown,
)


def _analysis() -> dict:
    graph = Graph(
        nodes=[
            Node("n1", "Intervention", "intervention"),
            Node("n2", "Transmission", "intermediate"),
            Node("n3", "Outcome", "outcome"),
        ],
        edges=[
            Edge("n1", "n2", 1, "high", "Intervention moves transmission."),
            Edge("n2", "n3", 1, "med", "Transmission moves the outcome."),
        ],
        unknowns=[
            Unknown("u1", "Does transmission persist?", "n2"),
            Unknown("u2", "Does the outcome respond?", "n3"),
        ],
    )
    assignments = all_assignments(graph)
    resolved = [propagate(graph, assignment) for assignment in assignments]
    return {
        "brief": "A policy changes",
        "mode": "quick",
        "sources": [],
        "claims": [],
        "research_error": "",
        "candidate_graph": graph,
        "graph": graph,
        "critique": GraphCritique(role="causal", summary="Checked.", findings=[]),
        "report": AdjudicationReport(),
        "diff": GraphDiff(),
        "debate_error": "",
        "verification_error": "",
        "assignments": assignments,
        "impacts": [],
        "names": [scenario_name(graph, assignment) for assignment in assignments],
        "resolved": resolved,
        "narratives": ["A concise scenario note."] * 4,
        "usage": {
            "calls": 12,
            "completed_calls": 12,
            "input_tokens": 24_000,
            "cached_input_tokens": 0,
            "output_tokens": 3_000,
            "thinking_tokens": 1_000,
            "total_tokens": 28_000,
            "cost_usd": 0.012947,
            "cost_inr": 1.23,
            "usd_to_inr": 95.0,
            "max_calls": 30,
            "pricing_note": "Paid-tier estimate for this test.",
        },
    }


def test_completed_result_discloses_run_cost() -> None:
    previous = web_app._last_completed
    web_app._last_completed = _analysis()
    try:
        response = TestClient(web_app.app).get("/")
    finally:
        web_app._last_completed = previous

    assert response.status_code == 200
    assert "₹1.23" in response.text
    assert "12" in response.text
    assert "Gemini calls" in response.text
    assert "Paid-tier estimate for this test." in response.text
    assert 'class="cost-disclosure"' in response.text
    assert 'id="run-cost"' in response.text


if __name__ == "__main__":
    test_completed_result_discloses_run_cost()
    print("  ok  test_completed_result_discloses_run_cost")
    print("\n1/1 passed")

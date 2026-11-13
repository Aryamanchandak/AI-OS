"""Failure-semantics tests for the framework-neutral pipeline."""

from __future__ import annotations

import copy
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import engine.pipeline as pipeline
from engine.schema import (
    AdjudicationReport,
    Edge,
    Graph,
    GraphCritique,
    Node,
    Unknown,
)


def _graph() -> Graph:
    return Graph(
        nodes=[
            Node("n1", "Intervention", "intervention"),
            Node("n2", "Demand", "intermediate"),
            Node("n3", "Outcome", "outcome"),
        ],
        edges=[
            Edge(
                "n1",
                "n2",
                1,
                "high",
                "The intervention raises demand.",
                evidence_status="supported",
                supporting_claim_ids=["c1"],
            ),
            Edge("n2", "n3", 1, "med", "Demand raises the outcome."),
        ],
        unknowns=[
            Unknown("u1", "Does demand hold?", "n2"),
            Unknown("u2", "Does the intervention persist?", "n1"),
        ],
    )


def _common_patches():
    candidate = _graph()
    critique = GraphCritique(role="causal", summary="Review complete.", findings=[])
    return (
        candidate,
        critique,
        patch.object(pipeline, "extract_graph", return_value=candidate),
        patch.object(pipeline, "select_critic_role", return_value="causal"),
        patch.object(pipeline, "critique_graph", return_value=critique),
        patch.object(
            pipeline,
            "adjudicate_graph",
            return_value=(candidate, AdjudicationReport()),
        ),
        patch.object(pipeline, "synthesize_all", return_value=["Note."] * 4),
    )


def test_research_failure_degrades_to_brief_only() -> None:
    candidate, _, *patches = _common_patches()
    events = []
    with ExitStack() as stack:
        stack.enter_context(
            patch.object(
                pipeline,
                "plan_research",
                side_effect=RuntimeError("offline"),
            )
        )
        for mocked_stage in patches:
            stack.enter_context(mocked_stage)
        result = pipeline.run_pipeline(
            "A policy changes",
            "Quick",
            lambda step, message: events.append((step, message)),
        )

    assert result["candidate_graph"] is candidate
    assert [(edge.src, edge.dst) for edge in result["graph"].edges] == [
        (edge.src, edge.dst) for edge in candidate.edges
    ]
    assert result["sources"] == []
    assert result["claims"] == []
    assert result["research_error"] == "offline"
    assert any(step == "research_degraded" for step, _ in events)


def test_debate_failure_keeps_builder_graph_and_exposes_failure() -> None:
    candidate, _, extract_patch, role_patch, _, _, synth_patch = _common_patches()
    with (
        patch.object(pipeline, "plan_research", return_value=object()),
        patch.object(pipeline, "retrieve_sources", return_value=[]),
        patch.object(pipeline, "extract_claims", return_value=[]),
        extract_patch,
        role_patch,
        patch.object(pipeline, "critique_graph", side_effect=RuntimeError("critic down")),
        synth_patch,
    ):
        result = pipeline.run_pipeline("A policy changes", "deep", lambda *_: None)

    assert result["candidate_graph"] is candidate
    assert [(edge.src, edge.dst) for edge in result["graph"].edges] == [
        (edge.src, edge.dst) for edge in candidate.edges
    ]
    assert "critic down" in result["debate_error"]
    assert result["report"].unresolved == ["critic down"]
    assert result["critique"].role == "causal"


def test_verification_failure_clears_every_evidence_label() -> None:
    candidate, _, *patches = _common_patches()
    with ExitStack() as stack:
        for mocked_stage in (
            patch.object(pipeline, "plan_research", return_value=object()),
            patch.object(pipeline, "retrieve_sources", return_value=[]),
            patch.object(pipeline, "extract_claims", return_value=[]),
            *patches,
            patch.object(
                pipeline,
                "verify_load_bearing_edges",
                side_effect=RuntimeError("verifier down"),
            ),
        ):
            stack.enter_context(mocked_stage)
        result = pipeline.run_pipeline("A policy changes", "quick", lambda *_: None)

    assert result["graph"] is not candidate
    assert result["verification_error"] == "verifier down"
    assert all(edge.evidence_status == "unverified" for edge in result["graph"].edges)
    assert all(not edge.supporting_claim_ids for edge in result["graph"].edges)
    # The builder graph remains untouched for debate/diff auditability.
    assert copy.deepcopy(candidate).edges[0].evidence_status == "supported"


if __name__ == "__main__":
    tests = [
        value
        for name, value in sorted(globals().items())
        if name.startswith("test_")
    ]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")

"""Offline contract tests for the slim research/debate implementation."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.debate import (
    adjudicate_graph,
    critique_graph,
    graph_diff,
    select_critic_role,
    verify_load_bearing_edges,
)
from engine.extract import build_graph, extract_graph
from engine.propagate import propagate
from engine.research import extract_claims, plan_research
from engine.schema import (
    Edge,
    EdgeEvidenceIn,
    EdgeEvidenceOut,
    AdjudicationOut,
    AdjudicationReportIn,
    CausalGraphOut,
    CritiqueFindingIn,
    EvidenceClaim,
    EvidenceClaimIn,
    EvidenceClaimsOut,
    Graph,
    GraphCritiqueOut,
    Node,
    ResearchPlanOut,
    ResearchQueryGroupIn,
    SourceRecord,
    Unknown,
)
from engine.sensitivity import load_bearing_edges


class _FakeModels:
    def __init__(self, parsed_items):
        self._parsed_items = list(parsed_items)

    def generate_content(self, **kwargs):
        return SimpleNamespace(parsed=self._parsed_items.pop(0))


class _FakeClient:
    def __init__(self, *parsed_items):
        self.models = _FakeModels(parsed_items)


class _CapturingModels(_FakeModels):
    def __init__(self, parsed_items):
        super().__init__(parsed_items)
        self.calls = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        return super().generate_content(**kwargs)


def _chain() -> Graph:
    return Graph(
        nodes=[
            Node("n1", "Intervention", "intervention"),
            Node("n2", "Transmission", "intermediate"),
            Node("n3", "Outcome", "outcome"),
        ],
        edges=[
            Edge("n1", "n2", 1, "high", "The intervention moves transmission."),
            Edge("n2", "n3", 1, "high", "Transmission moves the outcome."),
        ],
        unknowns=[
            Unknown("u1", "Does transmission persist?", "n2"),
            Unknown("u2", "Does the outcome respond?", "n3"),
        ],
    )


def _valid_graph_out() -> CausalGraphOut:
    return CausalGraphOut.model_validate(
        {
            "nodes": [
                {"id": "n1", "label": "Root", "node_type": "intervention"},
                {"id": "n2", "label": "Channel A", "node_type": "intermediate"},
                {"id": "n3", "label": "Channel B", "node_type": "intermediate"},
                {"id": "n4", "label": "Driver A", "node_type": "intermediate"},
                {"id": "n5", "label": "Driver B", "node_type": "intermediate"},
                {"id": "n6", "label": "Outcome A", "node_type": "outcome"},
                {"id": "n7", "label": "Outcome B", "node_type": "outcome"},
                {"id": "n8", "label": "Outcome C", "node_type": "outcome"},
            ],
            "edges": [
                {"src": "n1", "dst": "n2", "sign": 1, "strength": "high", "mechanism": "Root moves A."},
                {"src": "n1", "dst": "n3", "sign": 1, "strength": "high", "mechanism": "Root moves B."},
                {"src": "n2", "dst": "n4", "sign": 1, "strength": "med", "mechanism": "A moves its driver."},
                {"src": "n3", "dst": "n5", "sign": 1, "strength": "med", "mechanism": "B moves its driver."},
                {"src": "n4", "dst": "n6", "sign": 1, "strength": "med", "mechanism": "Driver A moves outcome A."},
                {"src": "n4", "dst": "n7", "sign": -1, "strength": "low", "mechanism": "Driver A lowers outcome B."},
                {"src": "n5", "dst": "n8", "sign": 1, "strength": "med", "mechanism": "Driver B moves outcome C."},
            ],
            "unknowns": [
                {"id": "u1", "question": "Does A persist?", "affects_node_id": "n2"},
                {"id": "u2", "question": "Does B persist?", "affects_node_id": "n3"},
            ],
        }
    )


def _invalid_deep_graph_out() -> CausalGraphOut:
    payload = _valid_graph_out().model_dump()
    by_id = {node["id"]: node for node in payload["nodes"]}
    by_id["n5"]["node_type"] = "outcome"
    payload["edges"] = [
        {"src": "n1", "dst": "n2", "sign": 1, "strength": "high", "mechanism": "Root moves A."},
        {"src": "n2", "dst": "n3", "sign": 1, "strength": "med", "mechanism": "A moves B."},
        {"src": "n3", "dst": "n5", "sign": 1, "strength": "med", "mechanism": "B moves C."},
        {"src": "n5", "dst": "n6", "sign": 1, "strength": "low", "mechanism": "C moves outcome A."},
        {"src": "n2", "dst": "n7", "sign": 1, "strength": "low", "mechanism": "A moves outcome B."},
        {"src": "n2", "dst": "n8", "sign": -1, "strength": "low", "mechanism": "A lowers outcome C."},
    ]
    return CausalGraphOut.model_validate(payload)


def test_extraction_repairs_the_actual_rejected_graph() -> None:
    models = _CapturingModels([_invalid_deep_graph_out(), _valid_graph_out()])
    client = SimpleNamespace(models=models)

    graph = extract_graph("Root changes", client=client)

    assert len(graph.nodes) == 8
    assert len(models.calls) == 2
    repair_prompt = models.calls[1]["contents"]
    assert "Rejected graph to repair" in repair_prompt
    assert '"id": "n5"' in repair_prompt
    assert "outgoing edges (not a leaf)" in repair_prompt


def test_four_hop_outcomes_do_not_trigger_paid_retries() -> None:
    payload = _valid_graph_out().model_dump()
    payload["edges"] = [
        {"src": "n1", "dst": "n2", "sign": 1, "strength": "high", "mechanism": "Root moves A."},
        {"src": "n2", "dst": "n3", "sign": 1, "strength": "med", "mechanism": "A moves B."},
        {"src": "n3", "dst": "n4", "sign": 1, "strength": "med", "mechanism": "B moves C."},
        {"src": "n4", "dst": "n6", "sign": 1, "strength": "low", "mechanism": "C moves outcome A."},
        {"src": "n4", "dst": "n7", "sign": 1, "strength": "low", "mechanism": "C moves outcome B."},
        {"src": "n4", "dst": "n8", "sign": -1, "strength": "low", "mechanism": "C lowers outcome C."},
    ]
    four_hop = CausalGraphOut.model_validate(payload)
    models = _CapturingModels([four_hop])

    graph = extract_graph(
        "Root changes through three mechanisms",
        client=SimpleNamespace(models=models),
    )

    assert len(graph.nodes) == 8
    assert len(models.calls) == 1


def test_expanded_edge_payload_defaults_and_fields():
    payload = {
        "nodes": [
            {"id": "n1", "label": "Root", "node_type": "intervention"},
            {"id": "n2", "label": "Outcome", "node_type": "outcome"},
        ],
        "edges": [
            {
                "src": "n1",
                "dst": "n2",
                "sign": 1,
                "strength": "high",
                "mechanism": "Root moves outcome.",
                "confidence": "high",
                "time_lag": "one quarter",
                "conditions": ["policy holds"],
                "evidence_status": "supported",
                "supporting_claim_ids": ["c1"],
            }
        ],
        "unknowns": [],
    }
    edge = build_graph(payload).edges[0]
    assert edge.confidence == "high"
    assert edge.time_lag == "one quarter"
    assert edge.supporting_claim_ids == ["c1"]


def test_research_planner_keeps_counterevidence():
    parsed = ResearchPlanOut(
        query_groups=[
            ResearchQueryGroupIn(
                theme="mechanism",
                intent="evidence",
                queries=["policy transmission evidence"],
            ),
            ResearchQueryGroupIn(
                theme="challenge",
                intent="counterevidence",
                queries=["policy transmission failure"],
            ),
        ]
    )
    plan = plan_research("Policy changes outcomes", client=_FakeClient(parsed))
    assert sum(
        group.intent == "counterevidence" for group in plan.query_groups
    ) >= 2


def test_critic_and_adjudicator_are_one_structured_round():
    graph_out = _valid_graph_out()
    graph = build_graph(graph_out.model_dump())
    critique_out = GraphCritiqueOut(
        summary="One material condition is missing.",
        findings=[
            CritiqueFindingIn(
                src="n1",
                dst="n2",
                issue="The channel is conditional.",
                recommendation="Add the condition.",
                severity="med",
            )
        ],
    )
    critique = critique_graph(
        "Root changes",
        graph,
        [],
        "causal",
        client=_FakeClient(critique_out),
    )
    adjudication_out = AdjudicationOut(
        graph=graph_out,
        report=AdjudicationReportIn(
            accepted=["The condition matters."],
            changed=["n1 → n2 condition clarified."],
        ),
    )
    final_graph, report = adjudicate_graph(
        "Root changes",
        graph,
        critique,
        [],
        client=_FakeClient(adjudication_out),
    )
    assert critique.role == "causal"
    assert len(critique.findings) == 1
    assert len(final_graph.nodes) == 8
    assert report.changed == ["n1 → n2 condition clarified."]


def test_claim_extraction_links_source_and_passage():
    parsed = EvidenceClaimsOut(
        claims=[
            EvidenceClaimIn(
                text="The measured outcome rose.",
                source_id="s1",
                supporting_passage="The measured outcome rose by ten percent.",
                claim_type="fact",
                stance="supports",
                confidence="high",
            )
        ]
    )
    source = SourceRecord(
        id="s1",
        url="https://example.com/report",
        title="Report",
        publisher="example.com",
        retrieved_at="2026-01-01T00:00:00+00:00",
        extracted_text="The measured outcome rose by ten percent.",
    )
    claims = extract_claims("What changed?", [source], client=_FakeClient(parsed))
    assert claims[0].id == "c1"
    assert claims[0].source_id == "s1"
    assert claims[0].supporting_passage


def test_strength_weights_direction_vote():
    nodes = [Node("root", "Root", "intervention")]
    nodes += [Node(name, name, "intermediate") for name in ("a", "b", "c", "d")]
    nodes.append(Node("out", "Outcome", "outcome"))
    edges = [
        Edge("root", name, 1, "high", f"Root moves {name}.")
        for name in ("a", "b", "c", "d")
    ]
    edges += [
        Edge("a", "out", 1, "low", "A nudges outcome."),
        Edge("b", "out", 1, "low", "B nudges outcome."),
        Edge("c", "out", 1, "low", "C nudges outcome."),
        Edge("d", "out", -1, "high", "D strongly lowers outcome."),
    ]
    graph = Graph(nodes, edges, [])
    outcome = next(node for node in propagate(graph, {}).nodes if node.id == "out")
    assert outcome.sign == 0
    assert outcome.contested


def test_load_bearing_edges_are_named_and_bounded():
    impacts = load_bearing_edges(_chain(), assignments=[{}])
    assert impacts
    assert {(impact.src, impact.dst) for impact in impacts} <= {
        ("n1", "n2"),
        ("n2", "n3"),
    }
    assert len(impacts) <= 6


def test_verification_updates_only_selected_edges():
    graph = _chain()
    impacts = load_bearing_edges(graph, assignments=[{}], limit=1)
    selected = graph.edges[impacts[0].edge_index]
    parsed = EdgeEvidenceOut(
        edges=[
            EdgeEvidenceIn(
                src=selected.src,
                dst=selected.dst,
                evidence_status="supported",
                supporting_claim_ids=["c1"],
                explanation="Direct support.",
            )
        ]
    )
    claims = [
        EvidenceClaim(
            id="c1",
            text="A direct causal estimate.",
            source_id="s1",
            supporting_passage="Estimate passage.",
            claim_type="fact",
            stance="supports",
        )
    ]
    verified = verify_load_bearing_edges(
        graph, impacts, claims, client=_FakeClient(parsed)
    )
    statuses = {
        (edge.src, edge.dst): edge.evidence_status for edge in verified.edges
    }
    assert statuses[(selected.src, selected.dst)] == "supported"
    assert list(statuses.values()).count("unverified") == len(graph.edges) - 1


def test_role_selection_and_graph_diff_are_deterministic():
    assert select_critic_role("Government raises a tariff by 10%", []) == "contrarian"
    before = _chain()
    after = _chain()
    after.edges[0].strength = "low"
    diff = graph_diff(before, after)
    assert diff.changed == ["n1 → n2: strength"]


if __name__ == "__main__":
    tests = [
        value for name, value in sorted(globals().items())
        if name.startswith("test_")
    ]
    for test in tests:
        test()
        print(f"  ok  {test.__name__}")
    print(f"\n{len(tests)}/{len(tests)} passed")

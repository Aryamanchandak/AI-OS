"""Deterministic exact-edge sensitivity used by verification and the UI.

Not every edge in the graph actually matters to the four scenario outcomes —
many are redundant with other paths or too weak to flip a sign. This module
finds the ones that do matter by brute force: flip one edge's sign at a time
and re-run the free, deterministic propagate() across all four scenarios,
recording which edges change at least one outcome's sign. Two consumers use
that short list instead of the full edge set:
- the UI's "structural sensitivity" panel, so a reader can see exactly which
  causal links the conclusion actually depends on;
- debate.verify_load_bearing_edges(), which spends its one evidence-checking
  LLM call only on these edges instead of the whole graph.

No LLM calls here — propagate() is pure arithmetic, so this is just a loop.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

from engine.propagate import propagate
from engine.schema import Graph


@dataclass(frozen=True)
class EdgeImpact:
    """Observed outcome changes caused by flipping one exact graph edge."""

    edge_index: int
    src: str
    dst: str
    changed_outcomes: tuple[str, ...]
    changed_scenarios: int


def load_bearing_edges(
    graph: Graph,
    assignments: list[dict[str, int]],
    limit: int = 6,
) -> list[EdgeImpact]:
    """Return consequential edge flips, ranked across all four scenarios."""
    outcome_ids = [node.id for node in graph.nodes if node.node_type == "outcome"]
    # Compute each unmodified scenario once; every edge perturbation is compared
    # against these same baselines.
    baselines = [
        {node.id: node.sign for node in propagate(graph, assignment).nodes}
        for assignment in assignments
    ]
    impacts: list[EdgeImpact] = []
    for edge_index, edge in enumerate(graph.edges):
        changed: set[str] = set()
        changed_scenarios = 0
        # Flip direction on a copy so the original graph and later trials remain
        # untouched.
        perturbed = copy.deepcopy(graph)
        perturbed.edges[edge_index].sign *= -1
        for assignment, baseline in zip(assignments, baselines):
            resolved = {
                node.id: node.sign
                for node in propagate(perturbed, assignment).nodes
            }
            scenario_changed = False
            for outcome_id in outcome_ids:
                if resolved[outcome_id] != baseline[outcome_id]:
                    changed.add(outcome_id)
                    scenario_changed = True
            changed_scenarios += int(scenario_changed)
        if changed:
            impacts.append(
                EdgeImpact(
                    edge_index=edge_index,
                    src=edge.src,
                    dst=edge.dst,
                    changed_outcomes=tuple(sorted(changed)),
                    changed_scenarios=changed_scenarios,
                )
            )
    impacts.sort(
        # Prefer links that matter in more scenarios, then links affecting more
        # distinct outcomes. The original edge order is the final tie-breaker.
        key=lambda item: (
            item.changed_scenarios,
            len(item.changed_outcomes),
            -item.edge_index,
        ),
        reverse=True,
    )
    return impacts[:limit]

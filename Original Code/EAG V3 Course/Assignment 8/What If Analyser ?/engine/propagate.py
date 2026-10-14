"""Sign + magnitude propagation over a causal graph.

PURE FUNCTION. No LLM. No I/O. No network. This is what makes the tool
auditable and scenario re-runs free. If you ever find yourself importing an
LLM client here, that is a bug (see Rule 2 in Ideas.md).

Propagation is: sign is multiplication, magnitude is a lookup. Both are
deterministic and instant.
"""

from __future__ import annotations

import copy

import networkx as nx

from engine.schema import Graph

# Magnitudes are ordinal buckets. The inverse table turns arithmetic results
# back into the strings stored on Node objects.
_LEVELS = {"low": 0, "med": 1, "high": 2}
_INV_LEVELS = {v: k for k, v in _LEVELS.items()}
_DIRECTION_WEIGHT = {"low": 1, "med": 2, "high": 3}


def _sign_char(sign: int) -> str:
    """Return the compact sign glyph used in audit traces."""
    return {1: "+", -1: "-", 0: "0"}[sign]


def _decay(strength: str, hop_distance: int) -> str:
    """Strongest incoming edge strength, decayed one bucket per hop.

    The first hop off the intervention keeps its edge strength; each additional
    hop decays one bucket (high -> med -> low), floored at low. This lets a
    high-strength chain step cleanly high -> med -> low across three hops.
    """
    decay_steps = max(0, hop_distance - 1)
    new_level = max(0, _LEVELS[strength] - decay_steps)
    return _INV_LEVELS[new_level]


def propagate(graph: Graph, assignment: dict[str, int]) -> Graph:
    """Resolve every node's sign/magnitude/contested/trace for one assignment.

    ``assignment`` maps unknown id -> +1 or -1, e.g. {"u1": +1, "u2": -1}.
    The input graph is never mutated; a fully resolved deep copy is returned.
    """
    # Scenario runs must be independent, so every mutable node/edge is copied.
    g = copy.deepcopy(graph)

    # Repeated graph lookups are keyed once to keep the propagation loop simple.
    nodes_by_id = {n.id: n for n in g.nodes}

    # Build a structural view for topological ordering and shortest hop counts.
    dg = nx.DiGraph()
    for n in g.nodes:
        dg.add_node(n.id)
    for e in g.edges:
        dg.add_edge(e.src, e.dst)

    # Preserve source edge order so generated audit traces remain deterministic.
    incoming: dict[str, list] = {n.id: [] for n in g.nodes}
    for e in g.edges:
        incoming[e.dst].append(e)

    # --- Seed the exogenous nodes ---------------------------------------
    intervention = next(
        (n for n in g.nodes if n.node_type == "intervention"), None
    )
    seeded: set[str] = set()

    if intervention is not None:
        # "Up" means the stated intervention occurs; every scenario shares it.
        intervention.sign = 1
        intervention.magnitude = "high"
        intervention.contested = False
        intervention.trace = ["intervention (graph root), forced +1 / high"]
        seeded.add(intervention.id)

    # Apply the assignment: each unknown fixes the sign of one node.
    unknown_by_id = {u.id: u for u in g.unknowns}
    for uid, value in assignment.items():
        u = unknown_by_id.get(uid)
        if u is None:
            # Ignore extra assignment keys so callers may reuse larger mappings.
            continue
        node = nodes_by_id.get(u.affects_node_id)
        if node is None:
            # Extraction validation should prevent this, but propagation remains
            # defensive when called with a hand-built graph.
            continue
        node.sign = 1 if value >= 0 else -1
        node.magnitude = "high"
        node.contested = False
        node.trace = [
            f"seeded by {uid}={_sign_char(node.sign)}: {u.question}"
        ]
        seeded.add(node.id)

    # Hop distance from the intervention (shortest path length in edges).
    if intervention is not None:
        hop = nx.single_source_shortest_path_length(dg, intervention.id)
    else:
        hop = {}

    # --- Walk in topological order --------------------------------------
    # Every parent is resolved before its children, so a single pass suffices.
    for node_id in nx.topological_sort(dg):
        node = nodes_by_id[node_id]
        if node_id in seeded:
            continue

        in_edges = incoming[node_id]
        if not in_edges:
            # Unforced root: stays neutral.
            node.sign = 0
            node.contested = False
            node.trace = []
            continue

        # Direction is a three-bucket integer vote. This prevents several weak
        # links automatically outvoting fewer high-strength mechanisms (C5).
        contributions = []  # (edge, parent_sign, contribution)
        for e in in_edges:
            parent = nodes_by_id[e.src]
            contribution = (
                parent.sign * e.sign * _DIRECTION_WEIGHT[e.strength]
            )
            contributions.append((e, parent.sign, contribution))

        # Equal-weight pushes vote by direction. Ties resolve to neutral but
        # are marked contested below so neutrality is not mistaken for no effect.
        nonzero = [c for (_, _, c) in contributions if c != 0]
        total = sum(c for (_, _, c) in contributions)

        if total > 0:
            node.sign = 1
        elif total < 0:
            node.sign = -1
        else:
            node.sign = 0

        # Contested: net zero despite real pushes, OR mixed-sign pushes.
        has_pos = any(c > 0 for c in nonzero)
        has_neg = any(c < 0 for c in nonzero)
        node.contested = (total == 0 and len(nonzero) > 0) or (
            has_pos and has_neg
        )

        # Magnitude is intentionally independent of the sign vote: take the
        # strongest incoming link, then attenuate it by causal distance.
        strongest = max(
            (e.strength for (e, _, _) in contributions),
            key=lambda s: _LEVELS[s],
        )
        node.magnitude = _decay(strongest, hop.get(node_id, 1))

        # Record every push, including neutral parents, for a complete audit trail.
        node.trace = []
        for e, parent_sign, _ in contributions:
            node.trace.append(
                f"{e.src}({_sign_char(parent_sign)}) "
                f"--[{e.sign:+d}: {e.mechanism}]--> "
                f"{node_id}({_sign_char(node.sign)})"
            )

    return g

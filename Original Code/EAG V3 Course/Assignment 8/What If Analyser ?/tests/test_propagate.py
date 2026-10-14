"""Tests for propagate.py — the deterministic core.

Run: .venv/bin/python -m pytest test_propagate.py -q
(or plain: .venv/bin/python test_propagate.py  -> runs a tiny self-check)

Fixtures are hand-built graphs, per Ideas.md step 1.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.schema import Edge, Graph, Node, Unknown
from engine.propagate import propagate


# A linear fixture isolates sign multiplication and hop-based magnitude decay.
def _chain_graph(mid_edge_sign: int = 1) -> Graph:
    """n1(intervention) -> n2 -> n3 -> n4(outcome), all high edges.

    ``mid_edge_sign`` sets the sign of the n2->n3 edge so tests can flip it.
    """
    nodes = [
        Node("n1", "intervention", "intervention"),
        Node("n2", "hop1", "intermediate"),
        Node("n3", "hop2", "intermediate"),
        Node("n4", "hop3 outcome", "outcome"),
    ]
    edges = [
        Edge("n1", "n2", 1, "high", "n1 drives n2"),
        Edge("n2", "n3", mid_edge_sign, "high", "n2 drives n3"),
        Edge("n3", "n4", 1, "high", "n3 drives n4"),
    ]
    unknowns = [
        Unknown("u1", "does X hold?", "n2"),
        Unknown("u2", "does Y hold?", "n3"),
    ]
    return Graph(nodes, edges, unknowns)


def _diamond_graph() -> Graph:
    """n1 -> a(+), n1 -> b(-), a & b -> c. Opposite contributions at c."""
    # The two terminal pushes are equal and opposite by construction.
    nodes = [
        Node("n1", "intervention", "intervention"),
        Node("a", "up push", "intermediate"),
        Node("b", "down push", "intermediate"),
        Node("c", "conflicted outcome", "outcome"),
    ]
    edges = [
        Edge("n1", "a", 1, "high", "n1 raises a"),
        Edge("n1", "b", 1, "high", "n1 raises b"),
        Edge("a", "c", 1, "high", "a raises c"),
        Edge("b", "c", -1, "high", "b lowers c"),
    ]
    unknowns = [
        Unknown("u1", "q1", "a"),
        Unknown("u2", "q2", "b"),
    ]
    return Graph(nodes, edges, unknowns)


def _by_id(g: Graph) -> dict[str, Node]:
    """Index nodes for concise, readable assertions."""
    return {n.id: n for n in g.nodes}


# --- Tests -----------------------------------------------------------------

def test_single_chain_all_positive():
    """Positive edges preserve the intervention sign along the full chain."""
    g = propagate(_chain_graph(), assignment={})
    n = _by_id(g)
    assert n["n1"].sign == 1
    assert n["n2"].sign == 1
    assert n["n3"].sign == 1
    assert n["n4"].sign == 1
    assert not n["n4"].contested


def test_negative_edge_flips_downstream():
    """One inverse edge flips itself and all later positive descendants."""
    # Flip the n2->n3 edge to -1: n3 and n4 should go negative, n2 stays +.
    g = propagate(_chain_graph(mid_edge_sign=-1), assignment={})
    n = _by_id(g)
    assert n["n2"].sign == 1
    assert n["n3"].sign == -1
    assert n["n4"].sign == -1


def test_opposite_parents_contested():
    """Equal opposing contributions produce a contested neutral outcome."""
    g = propagate(_diamond_graph(), assignment={})
    n = _by_id(g)
    # a=+1, b=+1; a->c is +1, b->c is -1: contributions +1 and -1 => net 0.
    assert n["c"].contested is True
    assert n["c"].sign == 0


def test_magnitude_decays_across_three_hops():
    """High strength attenuates to medium and low with causal distance."""
    g = propagate(_chain_graph(), assignment={})
    n = _by_id(g)
    # Intervention high; then decay one bucket per additional hop.
    assert n["n1"].magnitude == "high"  # hop 0, seeded
    assert n["n2"].magnitude == "high"  # hop 1, full edge strength
    assert n["n3"].magnitude == "med"   # hop 2
    assert n["n4"].magnitude == "low"   # hop 3, floored


def test_assignment_seeds_sign():
    """Unknown assignments override upstream pushes at their affected nodes."""
    # Seed n2 negative via u1; n2's own sign is fixed, downstream follows.
    g = propagate(_chain_graph(), assignment={"u1": -1, "u2": +1})
    n = _by_id(g)
    assert n["n2"].sign == -1  # seeded, not overwritten by parent n1(+)
    assert n["n3"].sign == 1   # seeded by u2
    assert n["n4"].sign == 1   # n3(+) --[+1]--> n4


def test_original_graph_untouched():
    """Propagation resolves a copy and leaves its input reusable."""
    g0 = _chain_graph()
    propagate(g0, assignment={})
    assert all(node.sign == 0 for node in g0.nodes)  # inputs default to 0


def test_trace_is_populated():
    """Resolved outcomes retain at least one auditable mechanism line."""
    g = propagate(_chain_graph(), assignment={})
    n = _by_id(g)
    assert n["n4"].trace, "outcome node must have a trace"
    assert "-->" in n["n4"].trace[0]


def test_runs_fast():
    """The deterministic core stays comfortably within an interactive budget."""
    g = _chain_graph()
    start = time.perf_counter()
    propagate(g, assignment={})
    elapsed = time.perf_counter() - start
    assert elapsed < 0.01, f"propagation too slow: {elapsed*1000:.2f}ms"


if __name__ == "__main__":
    # Lightweight self-check without pytest: discover test functions by name and
    # run them in deterministic alphabetical order.
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print(f"  ok  {fn.__name__}")
    print(f"\n{passed}/{len(fns)} passed")

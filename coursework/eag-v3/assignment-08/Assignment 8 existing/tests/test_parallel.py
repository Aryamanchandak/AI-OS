"""Proves the parallel-layer claim: a layer's wall-clock is the MAX of its
branches, not the SUM.

Uses a sleeping fake skill so the assertion is about the Executor's scheduling,
not about how fast any real tool happens to be.
"""

import pathlib
import time

from agent.executor import Executor
from agent.graph import Graph, Node
from agent.skills import Skill

DELAY = 0.4


class SleepyLLM:
    """Every 'llm' node sleeps, so branch time is known and controlled."""

    def complete(self, system, user):
        time.sleep(DELAY)
        return "done"


def _skills():
    return {
        "worker": Skill(name="worker", runtime="llm", prompt="worker", description=""),
        "critic": Skill(name="critic", runtime="llm", prompt="critic", description=""),
    }


def _node(nid, deps=()):
    return Node(id=nid, skill="worker", input=nid, depends_on=list(deps))


def test_three_branch_layer_is_max_not_sum(tmp_path):
    graph = Graph([_node("a"), _node("b"), _node("c"),
                   _node("join", ["a", "b", "c"])])
    ex = Executor(_skills(), SleepyLLM(), tmp_path, replan=None)

    log = ex.run(graph, "parallel fan-out")

    fan_out = log.layer_seconds[0]
    branch_sum = sum(log.node_seconds[n] for n in ("a", "b", "c"))

    # The three branches each take ~DELAY. Serial would be ~3*DELAY.
    assert branch_sum > DELAY * 2.5, "branches did not each do the work"
    assert fan_out < DELAY * 1.8, (
        f"fan-out layer took {fan_out:.2f}s; expected ~{DELAY}s (max of "
        f"branches), not {branch_sum:.2f}s (sum of branches)"
    )


def test_serial_chain_is_the_sum(tmp_path):
    graph = Graph([_node("a"), _node("b", ["a"]), _node("c", ["b"])])
    ex = Executor(_skills(), SleepyLLM(), tmp_path, replan=None)

    log = ex.run(graph, "serial chain")

    assert len(log.layers) == 3
    assert log.total_seconds > DELAY * 2.5, (
        "a dependency chain must not be parallelised"
    )


def test_layer_membership_matches_the_dag(tmp_path):
    graph = Graph([_node("a"), _node("b"), _node("join", ["a", "b"])])
    ex = Executor(_skills(), SleepyLLM(), tmp_path, replan=None)

    log = ex.run(graph, "shape")

    assert sorted(log.layers[0]) == ["a", "b"]
    assert log.layers[1] == ["join"]

"""DAG representation and layering.

The Planner emits nodes; this module turns them into execution layers.
Every node in a layer is independent, which is what lets the Executor run a
layer concurrently and makes the parallel wall-clock claim testable.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Node:
    id: str
    skill: str
    input: str
    depends_on: list[str] = field(default_factory=list)
    critic: bool = False          # flagged producer -> Critic runs after it
    critic_property: str = ""     # what the Critic must verify

    @staticmethod
    def from_dict(d: dict) -> "Node":
        return Node(
            id=d["id"],
            skill=d["skill"],
            input=d.get("input", ""),
            depends_on=list(d.get("depends_on", [])),
            critic=bool(d.get("critic", False)),
            critic_property=d.get("critic_property", ""),
        )


class Graph:
    def __init__(self, nodes: list[Node]):
        self.nodes = {n.id: n for n in nodes}
        if len(self.nodes) != len(nodes):
            raise ValueError("duplicate node ids in plan")
        self._validate()

    def _validate(self) -> None:
        for node in self.nodes.values():
            for dep in node.depends_on:
                if dep not in self.nodes:
                    raise ValueError(f"node {node.id!r} depends on unknown node {dep!r}")

    def layers(self) -> list[list[Node]]:
        """Kahn's algorithm, grouped by level. Raises on a cycle."""
        indegree = {nid: len(n.depends_on) for nid, n in self.nodes.items()}
        remaining = dict(self.nodes)
        layers: list[list[Node]] = []

        while remaining:
            ready = [nid for nid in remaining if indegree[nid] == 0]
            if not ready:
                raise ValueError(f"cycle in plan among nodes: {sorted(remaining)}")
            ready.sort()
            layers.append([remaining[nid] for nid in ready])
            for nid in ready:
                del remaining[nid]
            for nid in remaining:
                deps = self.nodes[nid].depends_on
                indegree[nid] = sum(1 for d in deps if d in remaining)

        return layers

    def successors(self, node_id: str) -> list[Node]:
        return [n for n in self.nodes.values() if node_id in n.depends_on]

    def splice(self, new_nodes: list[Node], rewire: dict[str, list[str]]) -> None:
        """Insert recovery nodes and repoint dependencies.

        `rewire` maps an existing node id -> its replacement dependency list.
        This is how a Critic failure gets a Planner-authored fix into the
        running graph without restarting the whole plan.
        """
        for node in new_nodes:
            if node.id in self.nodes:
                raise ValueError(f"splice would clobber existing node {node.id!r}")
            self.nodes[node.id] = node
        for node_id, deps in rewire.items():
            self.nodes[node_id].depends_on = list(deps)
        self._validate()
        self.layers()  # fail fast if the splice introduced a cycle

"""Seed graph loading, validation, and neighborhood queries.

The graph is a hand-curated YAML file (graph/india_macro.yaml). LLM-proposed
edges never live here — they are quarantined in run artifacts and only enter
the graph through explicit human curation (`mirfish graph review-proposed`).
"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path

import yaml
from pydantic import ValidationError
from rapidfuzz import fuzz, process

from mirfish.schemas import Edge, Node

DEFAULT_GRAPH_PATH = Path("graph/india_macro.yaml")


class GraphError(Exception):
    """Raised when the graph file fails validation. Message lists all problems."""


class Graph:
    def __init__(self, nodes: list[Node], edges: list[Edge], review_flags: int = 0):
        self.nodes: dict[str, Node] = {n.node_id: n for n in nodes}
        self.edges: list[Edge] = edges
        self.review_flags = review_flags
        self._out: dict[str, list[Edge]] = defaultdict(list)
        self._in: dict[str, list[Edge]] = defaultdict(list)
        for e in edges:
            self._out[e.src].append(e)
            self._in[e.dst].append(e)
        # alias index: lowercased alias/name/node_id -> node_id
        self._alias_index: dict[str, str] = {}
        for n in nodes:
            for alias in [n.node_id, n.name, *n.aliases]:
                self._alias_index[alias.lower().strip()] = n.node_id

    # ------------------------------------------------------------------ load

    @classmethod
    def load(cls, path: str | Path = DEFAULT_GRAPH_PATH) -> Graph:
        path = Path(path)
        raw_text = path.read_text()
        data = yaml.safe_load(raw_text)
        problems: list[str] = []

        nodes: list[Node] = []
        for i, nd in enumerate(data.get("nodes", [])):
            try:
                nodes.append(Node.model_validate(nd))
            except ValidationError as exc:
                problems.append(f"nodes[{i}]: {exc.errors()[0]['msg']} ({nd.get('node_id')})")

        edges: list[Edge] = []
        for i, ed in enumerate(data.get("edges", [])):
            try:
                edges.append(Edge.model_validate(ed))
            except ValidationError as exc:
                problems.append(
                    f"edges[{i}]: {exc.errors()[0]['msg']} "
                    f"({ed.get('src')} -> {ed.get('dst')})"
                )

        if problems:
            raise GraphError("graph schema errors:\n  " + "\n  ".join(problems))

        review_flags = raw_text.count("# REVIEW")
        graph = cls(nodes, edges, review_flags=review_flags)
        graph.validate(node_list=nodes)
        return graph

    # -------------------------------------------------------------- validate

    def validate(self, node_list: list[Node] | None = None) -> None:
        """Raise GraphError listing every structural problem found."""
        problems: list[str] = []
        node_list = node_list if node_list is not None else list(self.nodes.values())

        # duplicate node ids
        id_counts = Counter(n.node_id for n in node_list)
        for node_id, count in id_counts.items():
            if count > 1:
                problems.append(f"duplicate node_id: {node_id} ({count}x)")

        # duplicate aliases across nodes (aliases + names + node_ids share one namespace)
        alias_owner: dict[str, str] = {}
        for n in node_list:
            for alias in [n.node_id, n.name, *n.aliases]:
                key = alias.lower().strip()
                owner = alias_owner.get(key)
                if owner is not None and owner != n.node_id:
                    problems.append(f"duplicate alias '{alias}' on {owner} and {n.node_id}")
                alias_owner[key] = n.node_id

        # dangling edges and self-loops
        for e in self.edges:
            if e.src not in self.nodes:
                problems.append(f"dangling edge src: {e.src} -> {e.dst}")
            if e.dst not in self.nodes:
                problems.append(f"dangling edge dst: {e.src} -> {e.dst}")
            if e.src == e.dst:
                problems.append(f"self-loop edge: {e.src}")

        # duplicate edges (same src/dst/channel)
        edge_counts = Counter((e.src, e.dst, e.channel) for e in self.edges)
        for (src, dst, channel), count in edge_counts.items():
            if count > 1:
                problems.append(f"duplicate edge: {src} -> {dst} [{channel}] ({count}x)")

        if problems:
            raise GraphError("graph validation errors:\n  " + "\n  ".join(problems))

    # --------------------------------------------------------------- queries

    def out_edges(self, node_id: str) -> list[Edge]:
        return list(self._out.get(node_id, []))

    def in_edges(self, node_id: str) -> list[Edge]:
        return list(self._in.get(node_id, []))

    def neighborhood(self, node_id: str) -> dict:
        """Node plus its curated edge neighborhood, for propagate-stage prompts."""
        if node_id not in self.nodes:
            raise KeyError(node_id)
        return {
            "node": self.nodes[node_id],
            "out_edges": self.out_edges(node_id),
            "in_edges": self.in_edges(node_id),
        }

    def resolve(self, text: str, fuzzy_threshold: float = 88.0) -> str | None:
        """Resolve free text to a node_id: exact alias match, then fuzzy."""
        key = text.lower().strip()
        if key in self._alias_index:
            return self._alias_index[key]
        match = process.extractOne(
            key,
            self._alias_index.keys(),
            scorer=fuzz.WRatio,
            score_cutoff=fuzzy_threshold,
        )
        if match is None:
            return None
        return self._alias_index[match[0]]

    def isolated_nodes(self) -> list[str]:
        return sorted(
            node_id
            for node_id in self.nodes
            if not self._out.get(node_id) and not self._in.get(node_id)
        )

    def stats(self) -> dict:
        nodes_by_type = Counter(n.type.value for n in self.nodes.values())
        edges_by_channel = Counter(e.channel.value for e in self.edges)
        degrees = [len(self._out.get(n, [])) + len(self._in.get(n, [])) for n in self.nodes]
        return {
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "nodes_by_type": dict(sorted(nodes_by_type.items())),
            "edges_by_channel": dict(sorted(edges_by_channel.items())),
            "avg_degree": round(sum(degrees) / len(degrees), 2) if degrees else 0.0,
            "isolated_nodes": self.isolated_nodes(),
            "review_flags": self.review_flags,
        }

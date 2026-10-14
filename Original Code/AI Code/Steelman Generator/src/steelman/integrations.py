from __future__ import annotations

from collections import defaultdict, deque
from typing import Any

from steelman.models import ArgumentGraph


class LocalMirfishAdapter:
    """Local second-order cascade analysis compatible with a future external adapter."""

    def cascade(self, graph: ArgumentGraph, start_node_id: str) -> list[list[str]]:
        children: dict[str, list[str]] = defaultdict(list)
        for edge in graph.edges:
            children[edge.source_id].append(edge.target_id)
        queue = deque([(start_node_id, [start_node_id])])
        paths = []
        while queue:
            node, path = queue.popleft()
            if not children[node]:
                paths.append(path)
            for child in children[node]:
                if child not in path:
                    queue.append((child, path + [child]))
        return paths


class Neo4jGraphStore:
    """Configurable Neo4j persistence; driver injection keeps it testable offline."""

    def __init__(self, uri: str, username: str, password: str, driver: Any | None = None) -> None:
        if driver is None:
            try:
                from neo4j import GraphDatabase
            except ImportError as exc:
                raise RuntimeError("Install the 'neo4j' extra to enable Neo4j persistence") from exc
            driver = GraphDatabase.driver(uri, auth=(username, password))
        self.driver = driver

    def save_graph(self, graph: ArgumentGraph) -> None:
        with self.driver.session() as session:
            session.run("MERGE (c:Claim {hash: $hash})", hash=graph.claim_hash)
            for node in graph.nodes:
                session.run(
                    "MATCH (c:Claim {hash: $hash}) MERGE (n:Premise {id: $id}) "
                    "SET n.text=$text, n.type=$type, n.load_bearing=$load MERGE (n)-[:BELONGS_TO]->(c)",
                    hash=graph.claim_hash, id=node.id, text=node.text, type=node.type.value, load=node.load_bearing,
                )
            for edge in graph.edges:
                session.run(
                    "MATCH (a:Premise {id:$a}), (b:Premise {id:$b}) MERGE (a)-[:SUPPORTS {relation:$r}]->(b)",
                    a=edge.source_id, b=edge.target_id, r=edge.relation,
                )


from __future__ import annotations

from typing import Any

from knowledge_graph.kg_store import KGStore


def _node_to_dict(node: Any) -> dict[str, Any] | None:
    return None if node is None else node.model_dump()


def _graph_hit_to_dict(hit: Any) -> dict[str, Any]:
    return {
        "id": hit.id,
        "canonical_name": hit.canonical_name,
        "domain": hit.domain,
    }


def _edge_to_dict(edge: Any) -> dict[str, Any]:
    return edge.model_dump()


def kg_search_concepts(query: str, limit: int = 20) -> list[dict[str, Any]]:
    store = KGStore()
    try:
        return [_graph_hit_to_dict(hit) for hit in store.search_by_name(query=query, limit=limit)]
    finally:
        store.close()


def kg_get_concept(node_id: str) -> dict[str, Any] | None:
    store = KGStore()
    try:
        return _node_to_dict(store.get_node(node_id))
    finally:
        store.close()


def kg_neighbors(node_id: str, direction: str = "both", relation: str | None = None) -> list[dict[str, Any]]:
    store = KGStore()
    try:
        return [
            _graph_hit_to_dict(hit)
            for hit in store.neighbors(node_id=node_id, direction=direction, relation=relation)
        ]
    finally:
        store.close()


def kg_reachable(node_id: str, direction: str = "outgoing", max_hops: int = 10) -> list[dict[str, Any]]:
    store = KGStore()
    try:
        return [
            _graph_hit_to_dict(hit)
            for hit in store.reachable(node_id=node_id, direction=direction, max_hops=max_hops)
        ]
    finally:
        store.close()


def kg_edges_for_node(node_id: str, direction: str = "both", relation: str | None = None) -> list[dict[str, Any]]:
    store = KGStore()
    try:
        return [
            _edge_to_dict(edge)
            for edge in store.edges_for_node(node_id=node_id, direction=direction, relation=relation)
        ]
    finally:
        store.close()

from tool_registry import register
from .logic import (
    kg_search_concepts,
    kg_get_concept,
    kg_neighbors,
    kg_reachable,
    kg_edges_for_node,
)

for _fn in (kg_search_concepts, kg_get_concept, kg_neighbors, kg_reachable, kg_edges_for_node):
    register(group="knowledge_graph")(_fn)

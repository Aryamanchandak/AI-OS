from __future__ import annotations

import copy
import json
import uuid

import networkx as nx

from ..config import Settings
from ..models import CausalEdge, CausalGraph, CausalNode, GraphOperation, GraphPatch, GraphRevision
from ..providers.model import ModelClient


class GraphValidationError(ValueError):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


def validate_graph(graph: CausalGraph, settings: Settings, *, require_indian_path: bool = False, claim_ids: set[str] | None = None) -> list[str]:
    problems: list[str] = []
    node_ids = [n.id for n in graph.nodes]
    edge_ids = [e.id for e in graph.edges]
    assumption_ids = [a.id for a in graph.assumptions]
    estimate_ids = [e.id for e in graph.estimates]
    for name, ids in (("node", node_ids), ("edge", edge_ids), ("assumption", assumption_ids), ("estimate", estimate_ids)):
        if len(ids) != len(set(ids)): problems.append(f"duplicate {name} IDs")
    if len(graph.nodes) > settings.max_graph_nodes: problems.append("graph node limit exceeded")
    if len(graph.edges) > settings.max_graph_edges: problems.append("graph edge limit exceeded")
    active_nodes = {n.id: n for n in graph.nodes if n.status == "active"}
    active_edges = [e for e in graph.edges if e.status != "rejected" and e.src in active_nodes and e.dst in active_nodes]
    seeds = [n for n in active_nodes.values() if n.node_type == "news_seed"]
    if len(seeds) != 1: problems.append(f"expected exactly one active news_seed, found {len(seeds)}")
    for edge in graph.edges:
        if edge.src not in set(node_ids) or edge.dst not in set(node_ids): problems.append(f"edge {edge.id} has missing endpoint")
        if not edge.mechanism.strip(): problems.append(f"edge {edge.id} has empty mechanism")
        if not set(edge.assumption_ids) <= set(assumption_ids): problems.append(f"edge {edge.id} references missing assumption")
        if not set(edge.estimate_ids) <= set(estimate_ids): problems.append(f"edge {edge.id} references missing estimate")
        if claim_ids is not None and not set(edge.supporting_claim_ids + edge.contradicting_claim_ids) <= claim_ids: problems.append(f"edge {edge.id} references missing claim")
    for assumption in graph.assumptions:
        if not set(assumption.required_for_edge_ids) <= set(edge_ids): problems.append(f"assumption {assumption.id} references missing edge")
        if claim_ids is not None and not set(assumption.supporting_claim_ids + assumption.contradicting_claim_ids) <= claim_ids: problems.append(f"assumption {assumption.id} references missing claim")
    for estimate in graph.estimates:
        if not set(estimate.input_estimate_ids) <= set(estimate_ids): problems.append(f"estimate {estimate.id} references missing input")
        if claim_ids is not None and not set(estimate.source_claim_ids) <= claim_ids: problems.append(f"estimate {estimate.id} references missing claim")
    dag = nx.DiGraph()
    dag.add_nodes_from(active_nodes)
    dag.add_edges_from((e.src, e.dst) for e in active_edges)
    if not nx.is_directed_acyclic_graph(dag): problems.append("active graph contains a cycle")
    if seeds and dag.in_degree(seeds[0].id): problems.append("news_seed root has incoming edges")
    outcomes = [n for n in active_nodes.values() if n.node_type in {"company_metric", "sector_metric", "market_outcome"}]
    if seeds:
        reachable = nx.descendants(dag, seeds[0].id)
        for outcome in outcomes:
            if outcome.id not in reachable: problems.append(f"orphan outcome {outcome.id}")
    for edge in active_edges:
        if active_nodes[edge.src].node_type == "news_seed" and active_nodes[edge.dst].node_type == "market_outcome" and "stock price" in active_nodes[edge.dst].label.casefold():
            problems.append(f"direct news_seed to stock price edge {edge.id} is invalid")
    if require_indian_path:
        indian = [n.id for n in outcomes if "india" in (n.geography or "").casefold() or n.entity_ids]
        if not seeds or not any(nx.has_path(dag, seeds[0].id, target) for target in indian): problems.append("no active path reaches an Indian equity outcome")
        generic = {"stock is affected", "company is affected", "share price impact"}
        for target in indian:
            if active_nodes[target].label.strip().casefold() in generic: problems.append(f"outcome {target} is not a concrete metric")
            incoming = [e for e in active_edges if e.dst == target]
            if incoming and not any(e.estimate_ids for e in incoming): problems.append(f"outcome {target} has no quantified or directional estimate")
    return problems


def topological_graph(graph: CausalGraph) -> CausalGraph:
    active = {n.id for n in graph.nodes if n.status == "active"}
    dag = nx.DiGraph((e.src, e.dst) for e in graph.edges if e.status != "rejected" and e.src in active and e.dst in active)
    dag.add_nodes_from(active)
    order = list(nx.topological_sort(dag))
    position = {node_id: i for i, node_id in enumerate(order)}
    return graph.model_copy(update={"nodes": sorted(graph.nodes, key=lambda n: (n.status != "active", position.get(n.id, 10**6)))})


def _replace(items, target_id, value, schema):
    found = False; result = []
    for item in items:
        if item.id == target_id:
            data = item.model_dump(); data.update(value or {}); result.append(schema.model_validate(data)); found = True
        else: result.append(item)
    if not found: raise KeyError(target_id)
    return result


def apply_patch(graph: CausalGraph, patch: GraphPatch, settings: Settings, *, require_indian_path: bool = False) -> CausalGraph:
    result = copy.deepcopy(graph)
    for operation in patch.operations:
        op, value = operation.op, operation.value or {}
        if op == "add_node": result.nodes.append(CausalNode.model_validate({**value, "id": operation.target_id}))
        elif op == "update_node": result.nodes = _replace(result.nodes, operation.target_id, value, CausalNode)
        elif op == "reject_node": result.nodes = _replace(result.nodes, operation.target_id, {"status": "rejected"}, CausalNode)
        elif op == "add_edge": result.edges.append(CausalEdge.model_validate({**value, "id": operation.target_id}))
        elif op == "update_edge": result.edges = _replace(result.edges, operation.target_id, value, CausalEdge)
        elif op == "reject_edge": result.edges = _replace(result.edges, operation.target_id, {"status": "rejected"}, CausalEdge)
        elif op.startswith("add_assumption"):
            from ..models import Assumption
            result.assumptions.append(Assumption.model_validate({**value, "id": operation.target_id}))
        elif op.startswith("update_assumption"):
            from ..models import Assumption
            result.assumptions = _replace(result.assumptions, operation.target_id, value, Assumption)
        elif op.startswith("add_estimate"):
            from ..models import Estimate
            result.estimates.append(Estimate.model_validate({**value, "id": operation.target_id}))
        elif op.startswith("update_estimate"):
            from ..models import Estimate
            result.estimates = _replace(result.estimates, operation.target_id, value, Estimate)
    result.version += 1
    problems = validate_graph(result, settings, require_indian_path=require_indian_path)
    if problems: raise GraphValidationError(problems)
    return result


def revise_graph(run_id: str, graph: CausalGraph, patch: GraphPatch, settings: Settings, model_call_id: str | None = None) -> tuple[CausalGraph, GraphRevision]:
    revised = apply_patch(graph, patch, settings)
    revision = GraphRevision(id="R" + uuid.uuid4().hex[:10], run_id=run_id, model_call_id=model_call_id, reason=patch.reason, evidence_ids=patch.evidence_ids, before_version=graph.version, after_version=revised.version, operations=patch.operations)
    return revised, revision


def build_initial_graph(run_id: str, seed, model: ModelClient, settings: Settings) -> CausalGraph:
    graph = model.generate(run_id=run_id, stage="initial_graph", prompt_name="graph/initial_graph_builder.md", prompt_data=seed.model_dump_json(), schema=CausalGraph, model_tier="reasoning")
    graph = graph.model_copy(update={"version": 1})
    problems = validate_graph(graph, settings)
    if not problems: return graph
    repaired = model.generate(run_id=run_id, stage="initial_graph_repair", prompt_name="graph/initial_graph_builder.md", prompt_data=json.dumps({"rejected_graph": graph.model_dump(mode="json"), "validation_errors": problems}), schema=CausalGraph, model_tier="reasoning", retry_count=1)
    repaired = repaired.model_copy(update={"version": 1})
    remaining = validate_graph(repaired, settings)
    if remaining: raise GraphValidationError(remaining)
    return repaired

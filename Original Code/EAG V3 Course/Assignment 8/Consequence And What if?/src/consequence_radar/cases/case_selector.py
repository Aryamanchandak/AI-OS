from __future__ import annotations

import json

from ..models import CaseSelection, CausalGraph, EvidenceClaim
from ..providers.model import ModelClient


class CaseSelectionError(ValueError): pass


def validate_cases(selection: CaseSelection, graph: CausalGraph, claim_ids: set[str] | None = None) -> None:
    edges = {e.id: e for e in graph.edges if e.status not in {"rejected", "contradicted"}}
    nodes = {n.id for n in graph.nodes if n.status == "active"}
    assumptions = {a.id: a for a in graph.assumptions}
    estimates = {e.id for e in graph.estimates}
    central = selection.central_case
    if not central.central: raise CaseSelectionError("central case must be marked central")
    if not central.path_edge_ids or not set(central.path_edge_ids) <= set(edges): raise CaseSelectionError("central case uses missing or inactive edges")
    if not set(central.path_node_ids) <= nodes: raise CaseSelectionError("central case uses missing or inactive nodes")
    if not set(central.required_assumption_ids) <= set(assumptions): raise CaseSelectionError("central case references missing assumptions")
    if not set(central.estimate_ids) <= estimates: raise CaseSelectionError("central case references missing estimates")
    if all(edges[e].status == "assumption_only" for e in central.path_edge_ids): raise CaseSelectionError("central case depends entirely on unsupported assumptions")
    path_edges = [edges[e] for e in central.path_edge_ids]
    if any(left.dst != right.src for left, right in zip(path_edges, path_edges[1:])): raise CaseSelectionError("central path edges are not a coherent ordered chain")
    # Every other artefact that reaches the report has its claim references
    # checked against verified evidence (validate_graph takes claim_ids), but a
    # case did not -- and a case's claim IDs are carried straight into the report
    # context.  An invented ID reached the writer unchallenged, because
    # validate_report only checks the [S..] source markers, never claim lineage.
    for case in (central, *selection.material_alternatives):
        if claim_ids is not None and not set(case.supporting_claim_ids + case.contradicting_claim_ids) <= claim_ids:
            raise CaseSelectionError(f"case {case.id} cites a claim absent from verified evidence")
        if not set(case.estimate_ids) <= estimates:
            raise CaseSelectionError(f"case {case.id} references missing estimates")
    for alternative in selection.material_alternatives:
        if not any(assumptions[a].material for a in alternative.required_assumption_ids if a in assumptions):
            raise CaseSelectionError(f"alternative {alternative.id} is not caused by a material assumption")


def select_cases(run_id: str, graph: CausalGraph, claims: list[EvidenceClaim], model: ModelClient) -> CaseSelection:
    selection = model.generate(run_id=run_id, stage="case_selection", prompt_name="cases/case_selector.md", prompt_data=json.dumps({"graph": graph.model_dump(mode="json"), "claims": [c.model_dump(mode="json") for c in claims]}), schema=CaseSelection, model_tier="reasoning")
    validate_cases(selection, graph, {c.id for c in claims})
    return selection

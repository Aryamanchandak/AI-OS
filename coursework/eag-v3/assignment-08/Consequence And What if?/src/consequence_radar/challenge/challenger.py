from __future__ import annotations

import json

from ..config import Settings
from ..graph import apply_patch
from ..models import AdjudicationResult, ChallengeResult, CausalGraph, EvidenceClaim, GraphPatch
from ..providers.model import ModelClient


def whole_graph_review(run_id: str, graph: CausalGraph, claims: list[EvidenceClaim], model: ModelClient) -> GraphPatch:
    return model.generate(run_id=run_id, stage="whole_graph_review", prompt_name="challenge/whole_graph_reviewer.md", prompt_data=json.dumps({"graph": graph.model_dump(mode="json"), "claims": [c.model_dump(mode="json") for c in claims]}), schema=GraphPatch, model_tier="reasoning")


def challenge(run_id: str, graph: CausalGraph, claims: list[EvidenceClaim], failures: list[str], model: ModelClient) -> ChallengeResult:
    return model.generate(run_id=run_id, stage="challenge", prompt_name="challenge/challenger.md", prompt_data=json.dumps({"graph": graph.model_dump(mode="json"), "claims": [c.model_dump(mode="json") for c in claims], "research_failures": failures}), schema=ChallengeResult, model_tier="reasoning")


def adjudicate(run_id: str, graph: CausalGraph, findings: ChallengeResult, claims: list[EvidenceClaim], model: ModelClient, settings: Settings) -> tuple[CausalGraph, AdjudicationResult]:
    result = model.generate(run_id=run_id, stage="adjudication", prompt_name="challenge/adjudicator.md", prompt_data=json.dumps({"graph": graph.model_dump(mode="json"), "findings": findings.model_dump(mode="json"), "claims": [c.model_dump(mode="json") for c in claims]}), schema=AdjudicationResult, model_tier="reasoning")
    operations = [operation for decision in result.decisions if decision.decision.startswith("accept_") for operation in decision.operations]
    if not operations: return graph, result
    patch = GraphPatch(operations=operations, reason="Accepted challenger findings", evidence_ids=sorted({cid for f in findings.findings for cid in f.claim_ids}))
    return apply_patch(graph, patch, settings), result


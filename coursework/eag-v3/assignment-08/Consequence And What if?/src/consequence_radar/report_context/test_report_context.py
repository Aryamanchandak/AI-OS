import pytest

from consequence_radar.models import Case, CandidateSeed, CaseSelection, EvidenceClaim, FactualStatus, SourceRecord, SELECTION_DIMENSIONS
from consequence_radar.report_context import ContextBudgetError, compile_context


def central_case():
    return Case(id="K1", name="Cost compression", path_node_ids=["N0","N1","N2"], path_edge_ids=["E1","E2"], required_assumption_ids=["A1"], supporting_claim_ids=["C1"], contradicting_claim_ids=[], equity_implication_direction="negative", estimate_ids=["Q1"], quantification_status="directional_only", time_horizon="12 months", weakening_observation="Policy delayed", central=True)

def test_context_compiles_and_enforces_token_budget(graph):
    seed = CandidateSeed(id="X", source_item_ids=["N"], reported_premise="Policy announced", factual_status=FactualStatus.ANNOUNCEMENT, possible_immediate_effect="Imported cost changes", possible_indian_equity_route="Indian sector EBITDA", grades={k:"high" for k in SELECTION_DIMENSIONS}, rationale="Strong route")
    claim = EvidenceClaim(id="C1", source_id="S1", claim="Policy announced", exact_passage="Policy announced today", claim_type="fact", stance="supports", concepts=[], passage_verified=True)
    source = SourceRecord(id="S1", url="https://example.com", title="Official", publisher="example.com", extracted_text="Policy announced today")
    context = compile_context(seed=seed, graph=graph, cases=CaseSelection(central_case=central_case()), claims=[claim], sources=[source], findings=[], decisions=[], gaps=[], failures=[], token_budget=10000)
    assert context.sources and context.assumptions
    with pytest.raises(ContextBudgetError): compile_context(seed=seed, graph=graph, cases=CaseSelection(central_case=central_case()), claims=[claim], sources=[source], findings=[], decisions=[], gaps=[], failures=[], token_budget=1)

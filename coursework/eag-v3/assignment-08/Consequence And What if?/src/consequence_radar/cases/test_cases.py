import pytest

from consequence_radar.cases import CaseSelectionError, validate_cases
from consequence_radar.models import Case, CaseSelection


def central_case():
    return Case(id="K1", name="Cost compression", path_node_ids=["N0","N1","N2"], path_edge_ids=["E1","E2"], required_assumption_ids=["A1"], supporting_claim_ids=["C1"], contradicting_claim_ids=[], equity_implication_direction="negative", estimate_ids=["Q1"], quantification_status="directional_only", time_horizon="12 months", weakening_observation="Policy delayed", central=True)

def test_central_case_and_alternative_rules(graph):
    selection = CaseSelection(central_case=central_case())
    validate_cases(selection, graph)
    bad_alt = central_case().model_copy(update={"id":"K2","central":False,"required_assumption_ids":[]})
    with pytest.raises(CaseSelectionError): validate_cases(CaseSelection(central_case=central_case(), material_alternatives=[bad_alt]), graph)

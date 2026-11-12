from consequence_radar.models import Case, CandidateSeed, CaseSelection, EvidenceClaim, FactualStatus, NewsletterReport, SourceRecord, SELECTION_DIMENSIONS
from consequence_radar.report import validate_report
from consequence_radar.report_context import compile_context


def central_case():
    return Case(id="K1", name="Cost compression", path_node_ids=["N0","N1","N2"], path_edge_ids=["E1","E2"], required_assumption_ids=["A1"], supporting_claim_ids=["C1"], contradicting_claim_ids=[], equity_implication_direction="negative", estimate_ids=["Q1"], quantification_status="directional_only", time_horizon="12 months", weakening_observation="Policy delayed", central=True)

def test_context_and_invalid_citation_fail_closed(graph):
    seed = CandidateSeed(id="X", source_item_ids=["N"], reported_premise="Policy announced", factual_status=FactualStatus.ANNOUNCEMENT, possible_immediate_effect="Imported cost changes", possible_indian_equity_route="Indian sector EBITDA", grades={k:"high" for k in SELECTION_DIMENSIONS}, rationale="Strong route")
    claim = EvidenceClaim(id="C1", source_id="S1", claim="Policy announced", exact_passage="Policy announced today", claim_type="fact", stance="supports", concepts=[], passage_verified=True)
    source = SourceRecord(id="S1", url="https://example.com", title="Official", publisher="example.com", extracted_text="Policy announced today")
    context = compile_context(seed=seed, graph=graph, cases=CaseSelection(central_case=central_case()), claims=[claim], sources=[source], findings=[], decisions=[], gaps=[], failures=[], token_budget=10000)
    report = NewsletterReport(headline="Impact", dek="A careful consequence", why_this_matters="This matters because Indian sector earnings absorb the cost.", article_markdown=("careful analysis "*55)+"[S9]", central_case_summary="The supported mechanism makes this the coherent central path.", key_assumptions=["The policy is implemented on schedule"], what_changes_the_view=["Delay"], source_ids_used=["S9"])
    errors = validate_report(report, context, 50, 200)
    assert any("unknown source" in e for e in errors)

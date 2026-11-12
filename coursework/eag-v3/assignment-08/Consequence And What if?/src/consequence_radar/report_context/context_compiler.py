from __future__ import annotations

from ..graph import topological_graph
from ..models import AdjudicationDecision, CandidateSeed, CaseSelection, ChallengeFinding, CausalGraph, EvidenceClaim, ReportContext, SourceRecord


class ContextBudgetError(ValueError): pass

# A verified claim already carries the exact passage it rests on, so the report
# writer needs a source's identity for citation markers -- not its article body.
# An untrimmed body is up to 80,000 characters, roughly 20,000 approximate
# tokens, so a single source consumed most of the default budget and every
# multi-source run failed here after paying for the whole pipeline. The full
# text stays in the persisted "sources" artifact, so the audit trail is intact.
SOURCE_EXCERPT_CHARS = 600

# The same argument applies to a claim's exact_passage. It is the receipt for a
# verification that already happened in verify_claims -- passage_verified is the
# durable result, and the untruncated passage stays in the persisted
# accepted_claims artifact. Left whole it becomes the largest term once source
# bodies are excerpted: a graph at the configured edge limit citing two claims
# an edge still exceeded the budget, and those claims are all load-bearing, so
# dropping background evidence could not recover it. The claim text itself --
# what the writer actually reasons over -- is never truncated.
CLAIM_PASSAGE_EXCERPT_CHARS = 400


def _excerpt(source: SourceRecord) -> SourceRecord:
    return source.model_copy(update={"extracted_text": source.extracted_text[:SOURCE_EXCERPT_CHARS]})


def _excerpt_claim(claim: EvidenceClaim) -> EvidenceClaim:
    return claim.model_copy(update={"exact_passage": claim.exact_passage[:CLAIM_PASSAGE_EXCERPT_CHARS]})


def approximate_tokens(context: ReportContext) -> int:
    return len(context.model_dump_json()) // 4


def compile_context(*, seed: CandidateSeed, graph: CausalGraph, cases: CaseSelection, claims: list[EvidenceClaim], sources: list[SourceRecord], findings: list[ChallengeFinding], decisions: list[AdjudicationDecision], gaps: list[str], failures: list[str], token_budget: int) -> ReportContext:
    active_edge_claims = {cid for edge in graph.edges if edge.status != "rejected" for cid in edge.supporting_claim_ids + edge.contradicting_claim_ids}
    case_claims = set(cases.central_case.supporting_claim_ids + cases.central_case.contradicting_claim_ids)
    for case in cases.material_alternatives: case_claims.update(case.supporting_claim_ids + case.contradicting_claim_ids)
    load_bearing = active_edge_claims | case_claims
    accepted = [_excerpt_claim(c) for c in claims if c.passage_verified and c.stance != "contradicts"]
    contradicting = [_excerpt_claim(c) for c in claims if c.passage_verified and c.stance == "contradicts"]
    source_ids = {c.source_id for c in accepted + contradicting}
    context = ReportContext(selected_premise=seed.reported_premise, factual_status=seed.factual_status, indian_equity_focus=seed.possible_indian_equity_route, graph=topological_graph(graph), central_case=cases.central_case, material_alternatives=cases.material_alternatives, assumptions=[a for a in graph.assumptions if any(e.status != "rejected" and e.id in a.required_for_edge_ids for e in graph.edges)], accepted_claims=accepted, contradicting_claims=contradicting, estimates=graph.estimates, challenge_findings=findings, adjudication_decisions=decisions, known_gaps=gaps, research_failures=failures, sources=[_excerpt(s) for s in sources if s.id in source_ids])
    if approximate_tokens(context) <= token_budget: return context
    context = context.model_copy(update={"accepted_claims": [c for c in accepted if c.id in load_bearing]})
    kept_sources = {c.source_id for c in context.accepted_claims + context.contradicting_claims}
    context = context.model_copy(update={"sources": [_excerpt(s) for s in sources if s.id in kept_sources]})
    if approximate_tokens(context) > token_budget: raise ContextBudgetError("canonical report context exceeds token budget after removing non-load-bearing background evidence")
    return context


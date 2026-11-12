"""Framework-neutral orchestration for one complete scenario analysis.

This is the one file that imports and calls every other engine/ module, in
the fixed stage order documented in docs/WORKFLOW.md. It exists so both UI
shells run the identical pipeline instead of each reimplementing the call
order — a change to the pipeline shape only has to happen here.

The pipeline is deliberately synchronous. UI shells decide where it runs:
Streamlit calls it directly, while the FastAPI app runs it in a worker thread.
Progress is reported through a small callback instead of a UI dependency.
"""

from __future__ import annotations

import copy
from collections.abc import Callable

from engine.debate import (
    adjudicate_graph,
    critique_graph,
    graph_diff,
    select_critic_role,
    verify_load_bearing_edges,
)
from engine.extract import extract_graph
from engine.metering import MeteredGeminiClient, UsageLedger
from engine.presentation import all_assignments, scenario_name
from engine.propagate import propagate
from engine.research import extract_claims, plan_research, retrieve_sources
from engine.schema import AdjudicationReport, GraphCritique
from engine.sensitivity import load_bearing_edges
from engine.synth import synthesize_all

ProgressCallback = Callable[[str, str], None]


def _unverified_copy(graph):
    """Return a graph whose evidence fields do not imply verification."""
    result = copy.deepcopy(graph)
    for edge in result.edges:
        edge.evidence_status = "unverified"
        edge.supporting_claim_ids = []
        edge.contradicting_claim_ids = []
    return result


def run_pipeline(
    brief: str,
    mode: str,
    on_progress: ProgressCallback,
    on_usage: Callable[[dict], None] | None = None,
    model_client=None,
) -> dict:
    """Run the fixed analysis pipeline and return its complete UI payload.

    Recoverable research, debate, and verification failures remain visible in
    the returned payload. Builder or synthesis failures escape to the caller,
    which is responsible for retaining any previously completed result.
    """
    normalized_brief = brief.strip()
    if not normalized_brief:
        raise ValueError("A situation is required.")
    normalized_mode = mode.strip().casefold()
    if normalized_mode not in {"quick", "deep"}:
        raise ValueError("Mode must be either 'quick' or 'deep'.")

    # One shared wrapper meters every model call, including calls made from the
    # research and narrative thread pools. It is lazy so offline tests that
    # replace model stages do not require credentials or network access.
    usage_ledger = UsageLedger(on_update=on_usage)
    client = model_client or MeteredGeminiClient(usage_ledger)

    # Research is a recoverable stage: if search/fetch/claim-extraction fails
    # for any reason (network, rate limit, no sources found), the pipeline
    # still builds a graph from the brief alone rather than aborting the run.
    sources, claims, research_plan = [], [], None
    research_error = ""
    try:
        on_progress("research_plan", "Planning evidence and counterevidence")
        research_plan = plan_research(
            normalized_brief, mode=normalized_mode, client=client
        )
        on_progress("research_retrieve", "Retrieving and ranking public sources")
        sources = retrieve_sources(
            research_plan,
            normalized_brief,
            mode=normalized_mode,
            client=client,
        )
        on_progress("research_claims", "Extracting the evidence ledger")
        claims = extract_claims(normalized_brief, sources, client=client)
    except Exception as exc:
        research_error = str(exc)
        on_progress(
            "research_degraded",
            "Research unavailable; continuing from the brief alone",
        )

    on_progress("graph_build", "Building the research-aware causal graph")
    candidate_graph = extract_graph(normalized_brief, claims=claims, client=client)

    # Exactly one critic and one adjudication round — see engine/debate.py for
    # why this is capped rather than looped.
    critic_role = select_critic_role(normalized_brief, claims)
    critique = None
    debate_error = ""
    on_progress("graph_critique", f"Challenging the graph with a {critic_role} critic")
    try:
        critique = critique_graph(
            normalized_brief,
            candidate_graph,
            claims,
            critic_role,
            client=client,
        )
        on_progress("graph_adjudicate", "Adjudicating once and repairing the graph")
        graph, report = adjudicate_graph(
            normalized_brief,
            candidate_graph,
            critique,
            claims,
            client=client,
        )
    except Exception as exc:
        debate_error = (
            "The structured debate could not finish; the builder graph is shown "
            f"unchanged. {exc}"
        )
        graph = candidate_graph
        critique = critique or GraphCritique(
            role=critic_role,
            summary="The selected critic did not return a usable challenge.",
            findings=[],
        )
        report = AdjudicationReport(unresolved=[str(exc)])
        on_progress("debate_degraded", "Debate unavailable; retaining the builder graph")

    diff = graph_diff(candidate_graph, graph)
    assignments = all_assignments(graph)
    impacts = load_bearing_edges(graph, assignments)
    verification_error = ""
    on_progress(
        "edge_verification",
        f"Verifying {len(impacts)} load-bearing relationships",
    )
    try:
        graph = verify_load_bearing_edges(graph, impacts, claims, client=client)
    except Exception as exc:
        # Verification is all-or-nothing in the UI. A failed verifier must not
        # leak builder guesses or partial evidence labels.
        verification_error = str(exc)
        graph = _unverified_copy(graph)
        on_progress(
            "verification_degraded",
            "Verification unavailable; keeping every edge unverified",
        )

    on_progress("scenario_resolve", "Resolving four deterministic worlds")
    names = [scenario_name(graph, assignment) for assignment in assignments]
    resolved = [propagate(graph, assignment) for assignment in assignments]
    on_progress("scenario_narrate", "Writing four analyst narratives in parallel")
    narratives = synthesize_all(list(zip(names, resolved)), client=client)

    return {
        "brief": normalized_brief,
        "mode": normalized_mode,
        "research_plan": research_plan,
        "sources": sources,
        "claims": claims,
        "research_error": research_error,
        "candidate_graph": candidate_graph,
        "graph": graph,
        "critique": critique,
        "report": report,
        "diff": diff,
        "debate_error": debate_error,
        "verification_error": verification_error,
        "assignments": assignments,
        "impacts": impacts,
        "names": names,
        "resolved": resolved,
        "narratives": narratives,
        "usage": usage_ledger.snapshot(),
    }

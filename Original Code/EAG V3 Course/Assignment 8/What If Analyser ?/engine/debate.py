"""One-round graph challenge, adjudication, diff, and evidence verification.

extract.py's output is one LLM's first pass and is treated as a draft, not a
verdict: one role-selected critic tries to break it, one adjudicator repairs
it, and then the pipeline stops. There is deliberately no send-back to the
critic and no second round — an unbounded critique/repair loop would make
cost and latency unpredictable without reliably producing a better graph.

graph_diff() and verify_load_bearing_edges() close the audit loop: diff shows
exactly what adjudication changed, and verification re-checks only the small
set of edges sensitivity.py flagged as actually load-bearing, rather than
spending one LLM call per edge on the whole graph.
"""

from __future__ import annotations

import copy
import json
import os
import re

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()

from engine.extract import _validate, build_graph
from engine.schema import (
    AdjudicationOut,
    AdjudicationReport,
    CritiqueFinding,
    EdgeEvidenceOut,
    EvidenceClaim,
    Graph,
    GraphCritique,
    GraphCritiqueOut,
    GraphDiff,
)
from engine.sensitivity import EdgeImpact

MODEL = "gemini-3.1-pro-preview"


class DebateError(RuntimeError):
    """A structured debate stage could not complete."""


def _client(client: genai.Client | None) -> genai.Client:
    """Return an injected client or construct the default authenticated client."""
    if client is not None:
        return client
    if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
        raise DebateError("GEMINI_API_KEY is not set.")
    return genai.Client()


def _edge_payload(edge) -> dict:
    """Serialize an internal Edge without its scenario-specific runtime state."""
    return {
        "src": edge.src,
        "dst": edge.dst,
        "sign": edge.sign,
        "strength": edge.strength,
        "mechanism": edge.mechanism,
        "confidence": edge.confidence,
        "time_lag": edge.time_lag,
        "conditions": edge.conditions,
        "evidence_status": edge.evidence_status,
        "supporting_claim_ids": edge.supporting_claim_ids,
        "contradicting_claim_ids": edge.contradicting_claim_ids,
    }


def graph_payload(graph: Graph) -> dict:
    """Convert a graph into the JSON-safe shape used in debate prompts."""
    return {
        "nodes": [
            {"id": node.id, "label": node.label, "node_type": node.node_type}
            for node in graph.nodes
        ],
        "edges": [_edge_payload(edge) for edge in graph.edges],
        "unknowns": [
            {
                "id": unknown.id,
                "question": unknown.question,
                "affects_node_id": unknown.affects_node_id,
            }
            for unknown in graph.unknowns
        ],
    }


def _claims_payload(claims: list[EvidenceClaim]) -> list[dict]:
    """Keep only claim metadata needed to evaluate graph relationships."""
    return [
        {
            "id": claim.id,
            "text": claim.text,
            "source_id": claim.source_id,
            "type": claim.claim_type,
            "stance": claim.stance,
            "confidence": claim.confidence,
        }
        for claim in claims
    ]


def select_critic_role(situation: str, claims: list[EvidenceClaim]) -> str:
    """Choose one lens from the brief using a transparent fixed heuristic.

    A model-selected role would cost another LLM call and be harder to audit
    than a fixed rule, so this stays a plain keyword/regex classifier.
    """
    value = situation.casefold()
    policy_words = {
        "policy", "regulation", "government", "ban", "subsidy", "tax",
        "tariff", "law", "mandate", "central bank", "rbi", "fed",
    }
    quantitative = bool(
        re.search(r"(?:\d|%|\bbp\b|\bbps\b|₹|\$|€|£)", situation)
    )
    if any(word in value for word in policy_words):
        return "contrarian"
    if quantitative and claims:
        return "evidence"
    return "causal"


def critique_graph(
    situation: str,
    graph: Graph,
    claims: list[EvidenceClaim],
    role: str,
    client: genai.Client | None = None,
) -> GraphCritique:
    """Challenge the graph once with exactly one named role."""
    prompt = f"""Situation:
{situation}

Candidate graph:
{json.dumps(graph_payload(graph), ensure_ascii=False)}

Evidence ledger:
{json.dumps(_claims_payload(claims), ensure_ascii=False)}

Act only as the {role} critic. Identify the few material weaknesses that could
change conclusions. Aim every finding at existing node IDs; do not rewrite the
graph. Cite claim IDs only when they genuinely bear on the finding."""
    # Keep the generated client alive until the request has completed.
    model_client = _client(client)
    response = model_client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=(
                "You are an independent graph critic. Be specific, skeptical, "
                "and concise. A finding is not a repair."
            ),
            response_mime_type="application/json",
            response_schema=GraphCritiqueOut,
            max_output_tokens=5000,
            thinking_config=types.ThinkingConfig(thinking_level="MEDIUM"),
        ),
    )
    if response.parsed is None:
        raise DebateError("critic returned no structured findings")
    findings = [
        CritiqueFinding(
            id=f"f{index}",
            src=item.src,
            dst=item.dst,
            issue=item.issue,
            recommendation=item.recommendation,
            severity=item.severity,
            claim_ids=list(item.claim_ids),
        )
        for index, item in enumerate(response.parsed.findings, start=1)
    ]
    return GraphCritique(role=role, summary=response.parsed.summary, findings=findings)


def adjudicate_graph(
    situation: str,
    candidate: Graph,
    critique: GraphCritique,
    claims: list[EvidenceClaim],
    client: genai.Client | None = None,
) -> tuple[Graph, AdjudicationReport]:
    """Repair at most once. There is deliberately no send-back or retry loop."""
    prompt = f"""Situation:
{situation}

Candidate graph:
{json.dumps(graph_payload(candidate), ensure_ascii=False)}

Single {critique.role} critique:
{json.dumps({
    "summary": critique.summary,
    "findings": [finding.__dict__ for finding in critique.findings],
}, ensure_ascii=False)}

Evidence ledger:
{json.dumps(_claims_payload(claims), ensure_ascii=False)}

Return one final graph plus a decision record. Preserve graph invariants:
8-15 nodes, one root intervention, 3-5 leaf outcomes, exactly two useful
unknowns, DAG, max three causal hops. Accept good objections, reject weak ones,
and expose genuinely unresolved disagreements. This is the only repair round."""
    # Keep the generated client alive until the request has completed.
    model_client = _client(client)
    response = model_client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=(
                "You are the adjudicator. Repair the graph once and explain each "
                "decision; never initiate another critique round."
            ),
            response_mime_type="application/json",
            response_schema=AdjudicationOut,
            max_output_tokens=18000,
            thinking_config=types.ThinkingConfig(thinking_level="HIGH"),
        ),
    )
    if response.parsed is None:
        raise DebateError("adjudicator returned no structured result")
    graph = build_graph(response.parsed.graph.model_dump())
    problems = _validate(graph)
    if problems:
        raise DebateError("adjudicated graph is invalid: " + "; ".join(problems))
    data = response.parsed.report
    report = AdjudicationReport(
        accepted=list(data.accepted),
        changed=list(data.changed),
        rejected=list(data.rejected),
        unresolved=list(data.unresolved),
    )
    return graph, report


def graph_diff(before: Graph, after: Graph) -> GraphDiff:
    """Compare edge sets without another model call."""
    # Keying by endpoints turns edge additions/removals into set operations and
    # lets field-level edits be reported separately for shared relationships.
    old = {(edge.src, edge.dst): edge for edge in before.edges}
    new = {(edge.src, edge.dst): edge for edge in after.edges}
    old_keys, new_keys = set(old), set(new)
    added = [f"{src} → {dst}" for src, dst in sorted(new_keys - old_keys)]
    removed = [f"{src} → {dst}" for src, dst in sorted(old_keys - new_keys)]
    changed = []
    for src, dst in sorted(old_keys & new_keys):
        left, right = old[(src, dst)], new[(src, dst)]
        fields = []
        for field in ("sign", "strength", "mechanism", "confidence", "time_lag"):
            if getattr(left, field) != getattr(right, field):
                fields.append(field)
        if left.conditions != right.conditions:
            fields.append("conditions")
        if fields:
            changed.append(f"{src} → {dst}: {', '.join(fields)}")
    return GraphDiff(added=added, removed=removed, changed=changed)


def verify_load_bearing_edges(
    graph: Graph,
    impacts: list[EdgeImpact],
    claims: list[EvidenceClaim],
    client: genai.Client | None = None,
) -> Graph:
    """Verify only sensitivity-selected links in one batched structured call."""
    # Verification produces a fresh evidence view. Clearing inherited labels
    # prevents builder guesses from being presented as verifier conclusions.
    verified = copy.deepcopy(graph)
    for edge in verified.edges:
        edge.evidence_status = "unverified"
        edge.supporting_claim_ids = []
        edge.contradicting_claim_ids = []
    if not impacts or not claims:
        return verified

    selected = [
        {
            **_edge_payload(verified.edges[impact.edge_index]),
            "changed_outcomes": impact.changed_outcomes,
            "changed_scenarios": impact.changed_scenarios,
        }
        for impact in impacts
        if impact.edge_index < len(verified.edges)
    ]
    prompt = f"""Load-bearing causal edges:
{json.dumps(selected, ensure_ascii=False)}

Evidence ledger:
{json.dumps(_claims_payload(claims), ensure_ascii=False)}

Verify each listed relationship against only this ledger. "supported" requires
direct support, "contradicted" credible opposite evidence, "mixed" both,
"assumption" a plausible inference without direct support, and "unverified"
insufficient material. Return every listed edge exactly once."""
    # Keep the generated client alive until the request has completed.
    model_client = _client(client)
    response = model_client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=(
                "You are an evidence verifier. Do not infer that relevance is "
                "support, and never cite a claim ID not supplied."
            ),
            response_mime_type="application/json",
            response_schema=EdgeEvidenceOut,
            max_output_tokens=5000,
            thinking_config=types.ThinkingConfig(thinking_level="LOW"),
        ),
    )
    if response.parsed is None:
        raise DebateError("edge verification returned no structured result")
    claim_ids = {claim.id for claim in claims}
    updates = {(edge.src, edge.dst): edge for edge in response.parsed.edges}
    selected_keys = {(item["src"], item["dst"]) for item in selected}
    for edge in verified.edges:
        key = (edge.src, edge.dst)
        update = updates.get(key)
        if key not in selected_keys or update is None:
            continue
        # Ignore hallucinated claim IDs even if the structured response itself
        # is otherwise valid.
        edge.evidence_status = update.evidence_status
        edge.supporting_claim_ids = [
            claim_id for claim_id in update.supporting_claim_ids
            if claim_id in claim_ids
        ]
        edge.contradicting_claim_ids = [
            claim_id for claim_id in update.contradicting_claim_ids
            if claim_id in claim_ids
        ]
    return verified

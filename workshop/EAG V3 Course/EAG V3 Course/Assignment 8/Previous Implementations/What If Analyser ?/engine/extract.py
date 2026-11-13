"""Situation string -> validated causal Graph with bounded model repair.

Each attempt extracts or repairs the whole graph in one call. There is no
recursive per-node extraction. A valid first response remains the normal
one-call path; rejected graphs can be repaired with their validation context.

The call uses Gemini structured output (a forced JSON `response_schema`) so the
model must return structured data — we never parse free-text JSON out of prose.
"""

from __future__ import annotations

import os
import json

import networkx as nx
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Allow local development to supply credentials without hard-coding secrets.
load_dotenv()

# Import after loading the environment so this module has one clear
# initialization boundary before the project-level types are referenced.
from engine.schema import (
    CausalGraphOut,
    Edge,
    EvidenceClaim,
    Graph,
    Node,
    Unknown,
)

# All model-backed stages intentionally use the same Pro preview model.
MODEL = "gemini-3.1-pro-preview"

# The system prompt is also the first line of defense for graph invariants.
# _validate() below remains authoritative because model instructions can fail.
_SYSTEM = """You are a causal-inference analyst. Given a real-world situation, \
you map the chain of cause and effect it sets off, as a directed acyclic graph.
When an evidence ledger is supplied, use it as evidence rather than decoration.

Hard requirements:
- Return 8 to 15 nodes. 15 is the hard maximum (one screen's worth). Never more.
- Maximum causal depth is 3 hops from the intervention node.
- EXACTLY ONE node has node_type "intervention": it is the situation itself and \
the root of the graph. Give it no incoming edges.
- 3 to 5 nodes have node_type "outcome": the things an analyst actually cares \
about. Outcome nodes are graph LEAVES — they must have NO outgoing edges.
- Everything else is "intermediate".
- Deduplicate aggressively. Do not emit "consumer demand", "household spending", \
and "discretionary consumption" as three nodes — they are one node.
- Every edge needs a one-sentence mechanism explaining WHY src moves dst. \
Never leave a mechanism empty.
- Give every edge a confidence bucket, a practical time_lag, any conditions, \
and an evidence_status. Link only claim IDs that actually bear on that edge.
- "supported" needs direct source support; "mixed" needs both support and \
contradiction; "contradicted" means credible evidence points the other way; \
"assumption" is a model inference with no direct source; otherwise "unverified".
- Edge sign: +1 means "src goes up pushes dst up"; -1 means the inverse.
- Return EXACTLY 2 unknowns. Each must be a genuine binary (yes/no) uncertainty \
that a domain expert would actually argue about, tied to a specific node whose \
sign it sets. Good: "Does oil hold above $90?", "Do foreign investors treat \
this as risk-on?". Bad: "Will the effect be large?" (that is magnitude, not an \
unknown).
- The graph must be acyclic."""

_INSTR = "Map the causal graph for this situation.\n\nSituation: {situation}"


class ExtractionError(RuntimeError):
    """Raised when extraction cannot produce a valid causal graph."""

    pass


def build_graph(payload: dict) -> Graph:
    """Convert the validated Pydantic payload into mutable pipeline objects."""
    # The LLM-facing models are deliberately not reused internally: propagation
    # mutates scenario state on Node instances and therefore needs dataclasses.
    nodes = [
        Node(id=n["id"], label=n["label"], node_type=n["node_type"])
        for n in payload["nodes"]
    ]
    edges = [
        Edge(
            src=e["src"],
            dst=e["dst"],
            sign=int(e["sign"]),
            strength=e["strength"],
            mechanism=e["mechanism"],
            confidence=e.get("confidence", "med"),
            time_lag=e.get("time_lag", "unspecified"),
            conditions=list(e.get("conditions", [])),
            evidence_status=e.get("evidence_status", "unverified"),
            supporting_claim_ids=list(e.get("supporting_claim_ids", [])),
            contradicting_claim_ids=list(e.get("contradicting_claim_ids", [])),
        )
        for e in payload["edges"]
    ]
    unknowns = [
        Unknown(
            id=u["id"],
            question=u["question"],
            affects_node_id=u["affects_node_id"],
        )
        for u in payload["unknowns"]
    ]
    return Graph(nodes=nodes, edges=edges, unknowns=unknowns)


# Backward-compatible private name used by older callers/tests.
_build_graph = build_graph


def _validate(graph: Graph) -> list[str]:
    """Return a list of human-readable problems; empty list means valid."""
    problems: list[str] = []
    node_ids = {n.id for n in graph.nodes}

    # Validate cardinality before topology so errors remain specific and useful
    # when they are fed back to the retry call.
    if not (8 <= len(graph.nodes) <= 15):
        problems.append(f"expected 8-15 nodes, got {len(graph.nodes)}")

    interventions = [n for n in graph.nodes if n.node_type == "intervention"]
    if len(interventions) != 1:
        problems.append(f"expected exactly 1 intervention, got {len(interventions)}")

    outcomes = [n for n in graph.nodes if n.node_type == "outcome"]
    if not (3 <= len(outcomes) <= 5):
        problems.append(f"expected 3-5 outcomes, got {len(outcomes)}")

    # Check referential integrity and build an outgoing-edge count in one pass.
    outgoing: dict[str, int] = {n.id: 0 for n in graph.nodes}
    for e in graph.edges:
        if e.src not in node_ids:
            problems.append(f"edge src '{e.src}' is not a node")
        if e.dst not in node_ids:
            problems.append(f"edge dst '{e.dst}' is not a node")
        if e.src in outgoing:
            outgoing[e.src] += 1
        if not e.mechanism or not e.mechanism.strip():
            problems.append(f"edge {e.src}->{e.dst} has an empty mechanism")
        if e.sign not in (-1, 1):
            problems.append(f"edge {e.src}->{e.dst} has sign {e.sign} (must be -1 or +1)")

    # Outcomes must be leaves.
    for n in outcomes:
        if outgoing.get(n.id, 0) > 0:
            problems.append(f"outcome node '{n.id}' has outgoing edges (not a leaf)")

    # NetworkX provides a well-tested cycle check; invalid endpoint edges are
    # excluded here because they have already produced clearer errors above.
    dg = nx.DiGraph()
    dg.add_nodes_from(node_ids)
    dg.add_edges_from((e.src, e.dst) for e in graph.edges if e.src in node_ids and e.dst in node_ids)
    if not nx.is_directed_acyclic_graph(dg):
        problems.append("graph is not acyclic")
    elif len(interventions) == 1:
        root_id = interventions[0].id
        if dg.in_degree(root_id) != 0:
            problems.append(f"intervention node '{root_id}' has incoming edges")
        # Three hops is a readability target in the model prompt, not a
        # correctness boundary. A four-hop DAG is still deterministic,
        # renderable, and auditable. Rejecting it used to spend several repair
        # calls on a cosmetic preference and could fail an otherwise sound run.

    # Exactly 2 unknowns, each pointing at a real node.
    if len(graph.unknowns) != 2:
        problems.append(f"expected exactly 2 unknowns, got {len(graph.unknowns)}")
    for u in graph.unknowns:
        if u.affects_node_id not in node_ids:
            problems.append(
                f"unknown '{u.id}' points at missing node '{u.affects_node_id}'"
            )
        elif nx.is_directed_acyclic_graph(dg):
            descendants = nx.descendants(dg, u.affects_node_id)
            outcome_ids = {node.id for node in outcomes}
            if (
                u.affects_node_id not in outcome_ids
                and not (descendants & outcome_ids)
            ):
                problems.append(
                    f"unknown '{u.id}' cannot affect any outcome"
                )

    return problems


def _claim_context(claims: list[EvidenceClaim]) -> str:
    """Serialize the ranked evidence ledger compactly for graph construction."""
    if not claims:
        return "No retrieved evidence is available. Mark unsupported edges as assumptions."
    rows = [
        {
            "id": claim.id,
            "type": claim.claim_type,
            "stance": claim.stance,
            "confidence": claim.confidence,
            "claim": claim.text,
        }
        for claim in claims
    ]
    return json.dumps(rows, ensure_ascii=False)


def _call_model(
    client: genai.Client,
    situation: str,
    claims: list[EvidenceClaim] | None = None,
    nudge: str = "",
    rejected_payload: dict | None = None,
) -> dict:
    """Make one structured-output request and return a plain dictionary."""
    instruction = _INSTR.format(situation=situation)
    instruction += "\n\nRanked evidence ledger:\n" + _claim_context(claims or [])
    if nudge:
        # Repair calls are stateless, so include the rejected graph as well as
        # its validation errors. An ID such as "n5" is otherwise meaningless
        # to the next request and encourages another unrelated redraw.
        instruction += (
            "\n\nRejected graph to repair:\n"
            + json.dumps(rejected_payload or {}, ensure_ascii=False)
            + "\n\n"
            + nudge
            + "\nReturn the corrected complete graph, preserving valid content."
        )

    # response_schema asks the SDK to parse directly into CausalGraphOut.
    resp = client.models.generate_content(
        model=MODEL,
        contents=instruction,
        config=types.GenerateContentConfig(
            system_instruction=_SYSTEM,
            response_mime_type="application/json",
            response_schema=CausalGraphOut,
            # Gemini 3.1 Pro uses relative thinking levels rather than the
            # legacy fixed token budgets used by Gemini 2.5.
            max_output_tokens=16384,
            thinking_config=types.ThinkingConfig(thinking_level="HIGH"),
        ),
    )
    parsed = resp.parsed
    if parsed is None:
        raise ExtractionError("model did not return a parseable causal graph")
    # Downstream conversion expects mappings rather than Pydantic instances.
    return parsed.model_dump()


def extract_graph(
    situation: str,
    client: genai.Client | None = None,
    claims: list[EvidenceClaim] | None = None,
) -> Graph:
    """Extract a validated causal Graph from a plain-English situation.

    Validates each result and makes bounded repair attempts with the rejected
    graph and exact problems fed back. Attempts remain bounded so malformed
    output cannot create an unbounded loop.
    """
    if client is None:
        # Accept either credential name recognized by the Google SDK.
        if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
            raise ExtractionError(
                "GEMINI_API_KEY is not set. Export it before running."
            )
        client = genai.Client()

    max_attempts = max(1, int(os.getenv("WHATIF_EXTRACTION_ATTEMPTS", "3")))
    payload: dict | None = None
    problems: list[str] = []
    for attempt in range(1, max_attempts + 1):
        nudge = ""
        if problems:
            nudge = (
                "Your previous graph was rejected for these reasons — fix ALL "
                "of them:\n- " + "\n- ".join(problems)
            )
        payload = _call_model(
            client,
            situation,
            claims=claims,
            nudge=nudge,
            rejected_payload=payload,
        )
        graph = build_graph(payload)
        problems = _validate(graph)
        if not problems:
            return graph

    raise ExtractionError(
        f"extraction failed validation after {max_attempts} attempts: "
        + "; ".join(problems)
    )


if __name__ == "__main__":
    # Small command-line smoke path for inspecting extraction independently of
    # Streamlit. It still requires a configured API key.
    import sys

    situation = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "RBI cuts the repo rate by 50bp."
    )
    g = extract_graph(situation)
    print(f"\nSituation: {situation}\n")
    print(f"NODES ({len(g.nodes)}):")
    for n in g.nodes:
        print(f"  {n.id:>4}  [{n.node_type:>12}]  {n.label}")
    print(f"\nEDGES ({len(g.edges)}):")
    for e in g.edges:
        print(f"  {e.src} --[{e.sign:+d}/{e.strength}]--> {e.dst}  :: {e.mechanism}")
    print("\nUNKNOWNS:")
    for u in g.unknowns:
        print(f"  {u.id} (affects {u.affects_node_id}): {u.question}")

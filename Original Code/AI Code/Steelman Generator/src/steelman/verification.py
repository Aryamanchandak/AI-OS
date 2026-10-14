from __future__ import annotations

import re

from steelman.models import (
    ArgumentGraph,
    PremiseType,
    Source,
    SourceStance,
    SourceTier,
    VerificationGrade,
    VerificationResult,
)


_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = {"the", "a", "an", "and", "or", "to", "of", "in", "is", "are", "with", "that", "this"}


def _tokens(text: str) -> set[str]:
    return {token for token in _TOKEN.findall(text.casefold()) if len(token) > 2 and token not in _STOP}


def _relevant(node_text: str, source: Source, node_id: str) -> bool:
    if node_id in source.supports_node_ids:
        return True
    node_tokens = _tokens(node_text)
    source_tokens = _tokens(f"{source.title} {source.excerpt}")
    minimum = 2 if len(node_tokens) >= 4 else 1
    return len(node_tokens & source_tokens) >= minimum


def verify_graph(graph: ArgumentGraph, sources: list[Source]) -> ArgumentGraph:
    source_ids = {source.id for source in sources}
    results: list[VerificationResult] = []
    warnings: list[str] = []
    updated_nodes = []

    for node in graph.nodes:
        if node.type != PremiseType.EMPIRICAL:
            results.append(
                VerificationResult(
                    node_id=node.id,
                    grade=VerificationGrade.NOT_APPLICABLE,
                    note="This node is not an empirical assertion.",
                )
            )
            updated_nodes.append(node)
            continue

        missing_citations = set(node.cited_source_ids) - source_ids
        relevant = [source for source in sources if _relevant(node.text, source, node.id)]
        contested = [source for source in relevant if source.stance == SourceStance.CONTESTS]
        supporting = [source for source in relevant if source.stance == SourceStance.SUPPORTS]

        if missing_citations:
            grade = VerificationGrade.FABRICATED
            note = f"The node cites unknown source IDs: {', '.join(sorted(missing_citations))}."
            matched = []
        elif contested and not supporting:
            grade = VerificationGrade.CONTESTED
            note = "Relevant supplied evidence contests this premise."
            matched = contested
        elif contested and supporting:
            grade = VerificationGrade.CONTESTED
            note = "Supplied evidence materially disagrees on this premise."
            matched = relevant
        elif supporting:
            grade = (
                VerificationGrade.PRIMARY
                if any(source.tier == SourceTier.PRIMARY for source in supporting)
                else VerificationGrade.SECONDARY
            )
            note = "Matched to user-supplied evidence. Review the source directly before relying on it."
            matched = supporting
        else:
            grade = VerificationGrade.UNSUPPORTED
            note = "No supplied source supports this empirical premise."
            matched = []

        strength = node.strength
        if node.load_bearing and grade in {
            VerificationGrade.UNSUPPORTED,
            VerificationGrade.FABRICATED,
            VerificationGrade.CONTESTED,
        }:
            strength = "downgraded"
            warnings.append(f"Load-bearing premise downgraded ({grade.value}): {node.text}")
        updated_nodes.append(node.model_copy(update={"strength": strength}))
        results.append(
            VerificationResult(
                node_id=node.id,
                grade=grade,
                source_ids=[source.id for source in matched],
                note=note,
            )
        )

    return graph.model_copy(update={"nodes": updated_nodes, "verifications": results, "warnings": warnings})


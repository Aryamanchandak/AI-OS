from __future__ import annotations

from steelman.models import (
    ArgumentGraph,
    ClaimCard,
    ComponentType,
    PremiseEdge,
    PremiseNode,
    PremiseType,
    stable_id,
)


def make_node(text: str, node_type: PremiseType, load_bearing: bool = False) -> PremiseNode:
    return PremiseNode(
        id=stable_id("node", {"text": text.casefold(), "type": node_type.value}),
        text=text,
        type=node_type,
        load_bearing=load_bearing,
    )


def build_deterministic_graph(card: ClaimCard) -> ArgumentGraph:
    root = make_node(f"Conclusion: {card.canonical_claim}", PremiseType.CAUSAL, True)
    nodes = [root]
    edges: list[PremiseEdge] = []

    for component in card.components:
        if component.type == ComponentType.EMPIRICAL:
            premise = make_node(
                f"Observed conditions within {card.scope} are consistent with: {component.text}",
                PremiseType.EMPIRICAL,
                True,
            )
            mechanism = make_node(
                f"A credible mechanism must connect the observed conditions to: {component.text}",
                PremiseType.CAUSAL,
                True,
            )
            nodes.extend([premise, mechanism])
            edges.extend(
                [
                    PremiseEdge(source_id=premise.id, target_id=mechanism.id),
                    PremiseEdge(source_id=mechanism.id, target_id=root.id),
                ]
            )
        elif component.type == ComponentType.NORMATIVE:
            premise = make_node(
                f"The relevant decision-makers give priority to the value judgment: {component.text}",
                PremiseType.NORMATIVE,
                True,
            )
            nodes.append(premise)
            edges.append(PremiseEdge(source_id=premise.id, target_id=root.id))
        else:
            premise = make_node(
                f"The operative definition is accepted and applied consistently: {component.text}",
                PremiseType.DEFINITIONAL,
                True,
            )
            nodes.append(premise)
            edges.append(PremiseEdge(source_id=premise.id, target_id=root.id))

    boundary = make_node(
        f"The claim is evaluated over the stated horizon ({card.time_horizon}) and not beyond it.",
        PremiseType.DEFINITIONAL,
        False,
    )
    nodes.append(boundary)
    edges.append(PremiseEdge(source_id=boundary.id, target_id=root.id, relation="bounds"))
    return ArgumentGraph(claim_hash=card.claim_hash, nodes=nodes, edges=edges)


def graph_to_mermaid(graph: ArgumentGraph) -> str:
    lines = ["flowchart LR"]
    for node in graph.nodes:
        label = node.text.replace('"', "'")
        lines.append(f'  {node.id}["{label}"]')
    for edge in graph.edges:
        lines.append(f"  {edge.source_id} -->|{edge.relation}| {edge.target_id}")
    return "\n".join(lines)


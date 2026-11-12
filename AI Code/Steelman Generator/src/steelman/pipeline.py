from __future__ import annotations

from steelman.claim import create_claim_card
from steelman.models import AnalysisRun, ProponentStatus, Source, VerificationGrade
from steelman.providers import ConstructionProvider, DeterministicProvider
from steelman.verification import verify_graph


class SteelmanPipeline:
    def __init__(self, provider: ConstructionProvider | None = None, verification_cache=None) -> None:
        self.provider = provider or DeterministicProvider()
        self.verification_cache = verification_cache

    def run(
        self,
        claim: str,
        scope: str = "unspecified",
        time_horizon: str = "unspecified",
        sources: list[Source] | None = None,
    ) -> AnalysisRun:
        supplied_sources = sources or []
        card = create_claim_card(claim, scope, time_horizon)
        graph = self.provider.construct(card)
        graph = verify_graph(graph, supplied_sources)
        if self.verification_cache is not None:
            cached_results = []
            for node, result in zip(graph.nodes, graph.verifications):
                cached = self.verification_cache.cache_get(node.text)
                if cached and not supplied_sources:
                    cached_results.append(cached.model_copy(update={"node_id": node.id}))
                else:
                    self.verification_cache.cache_put(node.text, result)
                    cached_results.append(result)
            graph = graph.model_copy(update={"verifications": cached_results})
        proponents = sorted(
            {source.author_or_advocate.strip() for source in supplied_sources if source.author_or_advocate.strip()}
        )
        status = ProponentStatus.SOURCED if proponents else ProponentStatus.CONSTRUCTED
        return AnalysisRun(
            provider=self.provider.name,
            claim_card=card,
            graph=graph,
            sources=supplied_sources,
            proponent_status=status,
            proponent_names=proponents,
            rendered_steelman=self._render(card.canonical_claim, graph, status, proponents),
        )

    @staticmethod
    def _render(claim: str, graph, status: ProponentStatus, proponents: list[str]) -> str:
        verified = {
            result.node_id: result
            for result in graph.verifications
            if result.grade not in {VerificationGrade.NOT_APPLICABLE}
        }
        premises = []
        for node in graph.nodes:
            if node.text.startswith("Conclusion:"):
                continue
            verification = verified.get(node.id)
            suffix = f" [{verification.grade.value}]" if verification else ""
            premises.append(f"- {node.text}{suffix}")
        provenance = ", ".join(proponents) if proponents else status.value
        warnings = "\n".join(f"- {warning}" for warning in graph.warnings) or "- None"
        premise_text = "\n".join(premises)
        return (
            f"## Strongest coherent case\n\n**Claim:** {claim}\n\n"
            f"**Provenance:** {provenance}\n\n"
            f"### Required premises\n\n{premise_text}\n\n"
            f"### Verification gaps\n\n{warnings}"
        )

from __future__ import annotations

import re

from ..models import DedupGroup, DiscoveryExtract, FactualStatus

STOP = {"the", "a", "an", "and", "or", "to", "of", "in", "on", "for", "with", "from", "says", "said"}


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.casefold()) if len(w) > 2 and w not in STOP}


def infer_factual_status(text: str) -> FactualStatus:
    value = text.casefold()
    rules = [
        (FactualStatus.RUMOUR, ("rumour", "sources say", "may consider", "reportedly")),
        (FactualStatus.PROPOSAL, ("proposes", "proposal", "draft", "consultation")),
        (FactualStatus.MEASURED_OUTCOME, ("rose by", "fell by", "data showed", "measured")),
        (FactualStatus.IMPLEMENTED, ("implemented", "took effect", "effective from")),
        (FactualStatus.ENACTED, ("enacted", "signed into law")),
        (FactualStatus.FORMAL_DECISION, ("approved", "formal decision", "voted to")),
        (FactualStatus.ANNOUNCEMENT, ("announced", "launches", "will introduce")),
        (FactualStatus.ANALYSIS_OR_FORECAST, ("forecast", "expects", "could reach", "analysis")),
    ]
    for status, markers in rules:
        if any(marker in value for marker in markers):
            return status
    return FactualStatus.UNCLEAR


def deduplicate(extracts: list[DiscoveryExtract], threshold: float = 0.62) -> list[DedupGroup]:
    clusters: list[list[DiscoveryExtract]] = []
    for extract in extracts:
        tokens = _tokens(f"{extract.headline or ''} {extract.text[:800]}")
        match = None
        for cluster in clusters:
            other = _tokens(f"{cluster[0].headline or ''} {cluster[0].text[:800]}")
            score = len(tokens & other) / max(1, len(tokens | other))
            if score >= threshold:
                match = cluster; break
        if match is not None:
            match.append(extract)
        else:
            clusters.append([extract])
    groups = []
    for index, cluster in enumerate(clusters, 1):
        statuses = [infer_factual_status(x.text) for x in cluster]
        # Resolve disagreement conservatively: the least-settled member wins,
        # so one formal-decision article cannot promote a rumour into fact.
        caution = [FactualStatus.RUMOUR, FactualStatus.PROPOSAL, FactualStatus.ANALYSIS_OR_FORECAST, FactualStatus.UNCLEAR, FactualStatus.ANNOUNCEMENT, FactualStatus.FORMAL_DECISION, FactualStatus.ENACTED, FactualStatus.IMPLEMENTED, FactualStatus.MEASURED_OUTCOME]
        status = min(statuses, key=caution.index)
        authoritative = max(cluster, key=lambda x: (bool(x.text), bool(x.published_at), len(x.text)))
        status_names = sorted({s.value for s in statuses})
        groups.append(DedupGroup(id=f"D{index}", member_item_ids=[x.item_id for x in cluster], authoritative_item_id=authoritative.item_id, publisher_diversity=sorted({x.publisher for x in cluster if x.publisher}), agreement=["Items report substantially the same underlying development"] if len(cluster) > 1 else [], disagreement=[f"Factual-status labels differ: {', '.join(status_names)}"] if len(status_names) > 1 else [], factual_status=status))
    return groups

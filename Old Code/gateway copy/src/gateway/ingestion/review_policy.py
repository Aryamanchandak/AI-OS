from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from gateway.ingestion.models import (
    ClaimProposal,
    ConceptProposal,
    EvidenceRef,
    RelationProposal,
    ReviewSignal,
    SemanticExtraction,
)


ProposalType = Literal["concept", "claim", "relation"]


def _signal(
    code: str,
    *,
    proposal_id: str | None = None,
    proposal_type: ProposalType | None = None,
    detail: str | None = None,
) -> ReviewSignal:
    if proposal_id is None:
        return ReviewSignal(code=code, scope="envelope", detail=detail)
    return ReviewSignal(
        code=code,
        scope="proposal",
        proposal_id=proposal_id,
        proposal_type=proposal_type,
        detail=detail,
    )


def _evidence_signals(
    *,
    source_record_id: str,
    normalized_content: str,
    proposal_id: str,
    proposal_type: ProposalType,
    evidence: Iterable[EvidenceRef],
) -> list[ReviewSignal]:
    refs = list(evidence)
    if not refs:
        return [
            _signal(
                "missing_evidence",
                proposal_id=proposal_id,
                proposal_type=proposal_type,
            )
        ]

    signals: list[ReviewSignal] = []
    for index, ref in enumerate(refs):
        quote = str(getattr(ref, "quote"))
        start = getattr(ref, "normalized_char_start")
        end = getattr(ref, "normalized_char_end")
        detail_prefix = f"evidence[{index}]"

        if getattr(ref, "source_record_id") != source_record_id:
            signals.append(
                _signal(
                    "evidence_source_mismatch",
                    proposal_id=proposal_id,
                    proposal_type=proposal_type,
                    detail=detail_prefix,
                )
            )
        if start is None or end is None:
            signals.append(
                _signal(
                    "evidence_offsets_missing",
                    proposal_id=proposal_id,
                    proposal_type=proposal_type,
                    detail=detail_prefix,
                )
            )
            continue
        if start >= end or end > len(normalized_content):
            signals.append(
                _signal(
                    "evidence_range_invalid",
                    proposal_id=proposal_id,
                    proposal_type=proposal_type,
                    detail=f"{detail_prefix}: {start}:{end}",
                )
            )
            continue
        if normalized_content[start:end] != quote:
            signals.append(
                _signal(
                    "evidence_quote_mismatch",
                    proposal_id=proposal_id,
                    proposal_type=proposal_type,
                    detail=detail_prefix,
                )
            )
        if normalized_content.count(quote) > 1:
            signals.append(
                _signal(
                    "evidence_quote_ambiguous",
                    proposal_id=proposal_id,
                    proposal_type=proposal_type,
                    detail=detail_prefix,
                )
            )
    return signals


def assess_review(
    *,
    source_record_id: str,
    normalized_content: str,
    semantic: SemanticExtraction,
    model_confidence: float,
    model_review_reasons: Iterable[str],
    confidence_threshold: float,
) -> list[ReviewSignal]:
    """Apply deterministic review policy; no LLM or external service is used."""

    signals = [
        _signal(reason, detail="extractor")
        for reason in model_review_reasons
    ]
    proposals: list[
        tuple[ProposalType, ConceptProposal | ClaimProposal | RelationProposal]
    ] = [
        *(("concept", proposal) for proposal in semantic.concepts),
        *(("claim", proposal) for proposal in semantic.claims),
        *(("relation", proposal) for proposal in semantic.relations),
    ]
    if not proposals:
        signals.append(_signal("empty_semantic_extraction"))
    if model_confidence < confidence_threshold:
        signals.append(
            _signal(
                "overall_model_confidence_below_threshold",
                detail=f"{model_confidence:.6g} < {confidence_threshold:.6g}",
            )
        )
    for quality_signal in semantic.source_quality_signals:
        signals.append(_signal("source_quality_signal", detail=quality_signal))

    for proposal_type, proposal in proposals:
        if proposal.model_confidence < confidence_threshold:
            signals.append(
                _signal(
                    "proposal_model_confidence_below_threshold",
                    proposal_id=proposal.proposal_id,
                    proposal_type=proposal_type,
                    detail=(
                        f"{proposal.model_confidence:.6g} "
                        f"< {confidence_threshold:.6g}"
                    ),
                )
            )
        signals.extend(
            _evidence_signals(
                source_record_id=source_record_id,
                normalized_content=normalized_content,
                proposal_id=proposal.proposal_id,
                proposal_type=proposal_type,
                evidence=proposal.evidence,
            )
        )

    for concept in semantic.concepts:
        if concept.aliases:
            signals.append(
                _signal(
                    "alias_or_identity_proposal",
                    proposal_id=concept.proposal_id,
                    proposal_type="concept",
                )
            )
    for relation in semantic.relations:
        if relation.predicate.casefold() in {"same_as", "alias_of", "equivalent_to"}:
            signals.append(
                _signal(
                    "alias_or_identity_proposal",
                    proposal_id=relation.proposal_id,
                    proposal_type="relation",
                )
            )

    unique: dict[tuple[str, str, str, str], ReviewSignal] = {}
    for signal in signals:
        key = (
            signal.code,
            signal.scope,
            signal.proposal_id or "",
            signal.detail or "",
        )
        unique[key] = signal
    return sorted(
        unique.values(),
        key=lambda signal: (
            signal.scope,
            signal.proposal_type or "",
            signal.proposal_id or "",
            signal.code,
            signal.detail or "",
        ),
    )

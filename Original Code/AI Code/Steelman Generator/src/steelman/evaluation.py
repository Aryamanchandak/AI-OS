from __future__ import annotations

import re

from pydantic import BaseModel

from steelman.models import DualAnalysis, Side


class ResolvedDispute(BaseModel):
    claim: str
    correct_side: Side


def ideological_turing_score(text: str) -> float:
    """Deterministic neutrality/proponent-voice proxy; 1 is least externally signposted."""
    markers = re.findall(r"\b(obviously|clearly|irrational|so-called|supposedly|even they|admit)\b", text, re.I)
    return max(0.0, 1.0 - 0.15 * len(markers))


def score_resolved_dispute(analysis: DualAnalysis, dispute: ResolvedDispute) -> float:
    side = analysis.claim if dispute.correct_side == Side.CLAIM else analysis.negation
    quality = analysis.rubric.score / len(analysis.rubric.checks)
    survival = sum(round.survived for round in side.hardening) / max(1, len(side.hardening))
    return round((quality + survival) / 2, 3)


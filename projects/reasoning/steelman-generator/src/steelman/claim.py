from __future__ import annotations

import re

from steelman.models import ClaimCard, ClaimComponent, ComponentType, stable_id


_NORMATIVE = re.compile(r"\b(should|must|ought|better|worse|fair|unfair|desirable)\b", re.I)
_DEFINITIONAL = re.compile(r"\b(means|defined as|is by definition|constitutes)\b", re.I)
_TESTABLE = re.compile(
    r"\b(increase|decrease|rise|fall|cause|lead|reduce|improve|worsen|will|within|by\s+20\d{2}|percent|%)\b",
    re.I,
)


def _split_claim(raw_claim: str) -> list[str]:
    normalized = " ".join(raw_claim.strip().split())
    pieces = re.split(r"\s+(?:and|but|while|because)\s+|;", normalized, flags=re.I)
    return [piece.strip(" ,.") for piece in pieces if piece.strip(" ,.")]


def _classify(text: str) -> ComponentType:
    if _DEFINITIONAL.search(text):
        return ComponentType.DEFINITIONAL
    if _NORMATIVE.search(text):
        return ComponentType.NORMATIVE
    return ComponentType.EMPIRICAL


def create_claim_card(raw_claim: str, scope: str = "unspecified", time_horizon: str = "unspecified") -> ClaimCard:
    if not raw_claim.strip():
        raise ValueError("A claim is required")
    parts = _split_claim(raw_claim)
    components = [ClaimComponent(text=part, type=_classify(part)) for part in parts]
    empirical = [item for item in components if item.type == ComponentType.EMPIRICAL]
    falsifiable = bool(empirical and (_TESTABLE.search(raw_claim) or time_horizon != "unspecified"))
    note = (
        "The claim contains an empirical commitment and a testable direction or horizon."
        if falsifiable
        else "Add a measurable outcome, comparison, threshold, or time horizon before treating this claim as falsifiable."
    )
    canonical = "; ".join(item.text for item in components)
    payload = {
        "canonical_claim": canonical.casefold(),
        "components": [item.model_dump(mode="json") for item in components],
        "scope": scope.strip() or "unspecified",
        "time_horizon": time_horizon.strip() or "unspecified",
    }
    return ClaimCard(
        canonical_claim=canonical,
        components=components,
        scope=payload["scope"],
        time_horizon=payload["time_horizon"],
        falsifiable=falsifiable,
        falsifiability_note=note,
        claim_hash=stable_id("claim", payload),
    )


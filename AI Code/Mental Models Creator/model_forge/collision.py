from __future__ import annotations

from dataclasses import asdict, dataclass

from .schema import CausalModel


@dataclass(slots=True)
class Collision:
    severity: str
    left_model_id: str
    right_model_id: str
    cause: str
    effect: str
    left_sign: str
    right_sign: str
    left_edge_id: str
    right_edge_id: str
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


def find_collisions(candidate: CausalModel, library: list[CausalModel]) -> list[Collision]:
    found: list[Collision] = []
    opposites = {("positive", "negative"), ("negative", "positive")}
    for other in library:
        if other.id == candidate.id:
            continue
        for left in candidate.edges:
            for right in other.edges:
                same = left.cause == right.cause and left.effect == right.effect
                if same and (left.sign, right.sign) in opposites:
                    found.append(Collision(
                        "critical", candidate.id, other.id, left.cause, left.effect,
                        left.sign, right.sign, left.id, right.id,
                        "Shared causal edge has opposite directional signs; belief revision required.",
                    ))
                elif left.cause == right.cause and left.effect == right.effect and left.sign != right.sign:
                    found.append(Collision(
                        "review", candidate.id, other.id, left.cause, left.effect,
                        left.sign, right.sign, left.id, right.id,
                        "Shared causal edge has incompatible or unresolved direction.",
                    ))
    severity = {"critical": 0, "review": 1}
    return sorted(found, key=lambda item: severity[item.severity])


from __future__ import annotations

import json

from ..models import CandidateSeed, CandidateSelection, DedupGroup, DiscoveryExtract
from ..providers.model import ModelClient


class NoViableCandidate(RuntimeError):
    pass


WEIGHT = {"low": 0, "medium": 1, "high": 2}


def rank_candidates(candidates: list[CandidateSeed]) -> list[CandidateSeed]:
    def score(candidate: CandidateSeed):
        grades = candidate.grades
        gating = min(WEIGHT[grades["grounded_starting_point"]], WEIGHT[grades["indian_equity_transmission"]])
        total = sum(WEIGHT[g] for g in grades.values())
        return gating, total, candidate.id
    ranked = sorted(candidates, key=score, reverse=True)[:3]
    viable = [c for c in ranked if c.grades["grounded_starting_point"] != "low" and c.grades["indian_equity_transmission"] != "low"]
    if not viable:
        raise NoViableCandidate("no supplied development has both a grounded premise and plausible Indian-equity route")
    winner_id = viable[0].id
    return [c.model_copy(update={"selected": c.id == winner_id}) for c in ranked]


def select_candidate(run_id: str, extracts: list[DiscoveryExtract], groups: list[DedupGroup], model: ModelClient) -> list[CandidateSeed]:
    payload = json.dumps({"extracts": [x.model_dump(mode="json") for x in extracts], "dedup_groups": [g.model_dump(mode="json") for g in groups]}, ensure_ascii=False)
    response = model.generate(run_id=run_id, stage="candidate_selection", prompt_name="select/candidate_selector.md", prompt_data=payload, schema=CandidateSelection)
    supplied = {x.item_id for x in extracts}
    clean = [c for c in response.candidates if c.source_item_ids and set(c.source_item_ids) <= supplied]
    return rank_candidates(clean)

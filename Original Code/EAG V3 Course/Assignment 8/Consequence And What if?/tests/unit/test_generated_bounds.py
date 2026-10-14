"""A runaway generation must be stopped by the schema, not by silent truncation."""
import pytest
from pydantic import ValidationError

from consequence_radar.config import Settings
from consequence_radar.models import (
    MAX_GENERATED_ITEMS,
    CandidateSelection,
    EvidenceClaimDrafts,
    GraphPatch,
    ResearchTaskList,
)

BOUNDED = [
    (CandidateSelection, "candidates", "candidates"),
    (ResearchTaskList, "tasks", "tasks"),
    (EvidenceClaimDrafts, "claims", "claims"),
    (GraphPatch, "operations", "operations"),
]


@pytest.mark.parametrize("model, field, key", BOUNDED)
def test_generated_lists_carry_maxitems_into_the_wire_schema(model, field, key):
    # response_json_schema is what the decoder is constrained by, so the bound
    # has to survive into model_json_schema().
    assert model.model_json_schema()["properties"][field]["maxItems"] == MAX_GENERATED_ITEMS[key]


def test_a_runaway_candidate_list_is_rejected():
    seed = {
        "id": "C1", "source_item_ids": ["I1"], "reported_premise": "p",
        "factual_status": "announcement", "possible_immediate_effect": "e",
        "possible_indian_equity_route": "r", "rationale": "why",
        "grades": dict.fromkeys(
            ["grounded_starting_point", "immediate_effect_plausibility", "knock_on_potential",
             "indian_equity_transmission", "researchability", "decision_relevance",
             "unresolved_assumptions"], "medium"),
    }
    limit = MAX_GENERATED_ITEMS["candidates"]
    CandidateSelection.model_validate({"candidates": [seed] * limit})
    with pytest.raises(ValidationError, match="at most"):
        CandidateSelection.model_validate({"candidates": [seed] * (limit + 1)})


def test_bounds_stay_clear_of_what_callers_slice_locally():
    # rank_candidates and generate_tasks let the model overshoot on purpose and
    # take the best N.  A bound near N would convert that working path into a
    # validation failure, so keep a wide margin above the slice.
    settings = Settings(_env_file=None)
    assert MAX_GENERATED_ITEMS["candidates"] >= 5 * 3
    assert MAX_GENERATED_ITEMS["tasks"] >= 5 * settings.max_research_tasks_per_cycle
    # Claim extraction runs across every source fetched in a cycle.
    assert MAX_GENERATED_ITEMS["claims"] >= 5 * settings.max_fetched_sources_per_run

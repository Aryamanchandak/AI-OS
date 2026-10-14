from tool_registry import register
from .logic import (
    study_generate_cards,
    study_get_due_cards,
    study_submit_review,
    study_start_feynman,
    study_evaluate_feynman,
    study_record_feynman_evaluation,
    study_start_challenger,
    study_grade_challenger,
    study_record_challenger_evaluation,
    study_progress,
    study_set_temporary_override,
    study_cancel_temporary_override,
)

for _fn in (
    study_generate_cards,
    study_get_due_cards,
    study_submit_review,
    study_start_feynman,
    study_evaluate_feynman,
    study_record_feynman_evaluation,
    study_start_challenger,
    study_grade_challenger,
    study_record_challenger_evaluation,
    study_progress,
    study_set_temporary_override,
    study_cancel_temporary_override,
):
    register(group="study")(_fn)

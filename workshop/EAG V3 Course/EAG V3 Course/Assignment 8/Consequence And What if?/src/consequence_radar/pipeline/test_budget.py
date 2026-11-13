"""The per-run ceilings have to leave room for a run that actually finishes."""
from consequence_radar.config import Settings
from consequence_radar.pipeline import Pipeline
from consequence_radar.storage import Repository

# Generations a worst-case run issues, by stage.
PER_CYCLE = ("gap_analysis", "claim_extraction", "graph_patch", "graph_patch_repair")
ONE_OFF = ("candidate_selection", "initial_graph", "quantification_patch",
           "whole_graph_review", "challenge", "adjudication", "case_selection", "newsletter")


def worst_case_generations(settings: Settings) -> int:
    return len(ONE_OFF) + settings.max_research_cycles * len(PER_CYCLE)


def test_default_generation_budget_covers_a_worst_case_run():
    settings = Settings(_env_file=None)
    needed = worst_case_generations(settings)
    assert settings.max_model_calls_per_run >= needed, (
        f"a full run needs {needed} generations but the budget is "
        f"{settings.max_model_calls_per_run}; it would die mid-pipeline"
    )


def test_searches_are_not_charged_against_the_generation_budget(tmp_path):
    # max_research_tasks_per_cycle searches per cycle would otherwise swallow
    # the generation budget whole before the report is ever written.
    settings = Settings(_env_file=None)
    assert settings.max_search_queries_per_run + worst_case_generations(settings) > settings.max_model_calls_per_run

    repo = Repository(f"sqlite:///{tmp_path / 'budget.db'}")
    pipeline = Pipeline(settings, repo, model=object(), search=object(), fetcher=object())
    assert pipeline.ledger.max_calls == settings.max_model_calls_per_run
    assert pipeline.ledger.max_searches == settings.max_search_queries_per_run


def test_wall_clock_allows_a_reasoning_tier_run():
    settings = Settings(_env_file=None)
    # Reasoning-tier generations dominate; anything under a few seconds each is
    # optimistic, and searching and fetching still has to fit alongside.
    assert settings.max_wall_time_seconds >= worst_case_generations(settings) * 30

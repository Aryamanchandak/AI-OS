import json
from pathlib import Path

import pytest

from generate import (
    AlreadyRunningError,
    preflight_check,
    run_generation_job,
    single_run_lock,
)
from study_system.core.baseline import StudyBaseline


def _baseline(tmp_path: Path) -> StudyBaseline:
    return StudyBaseline(
        daily_card_sets=2,
        cards_per_set=3,
        review_limit=50,
        card_gen_model="test-model",
        feynman_model="test-model",
        challenger_model="test-model",
        prompt_versions={},
        database_root=tmp_path,
        sqlite_relative_path="study_system.db",
    )


def test_single_run_lock_rejects_concurrent_holder(tmp_path: Path) -> None:
    baseline = _baseline(tmp_path)
    with single_run_lock(baseline):
        with pytest.raises(AlreadyRunningError):
            with single_run_lock(baseline):
                pass  # pragma: no cover - must not be reached


def test_single_run_lock_is_reusable_once_released(tmp_path: Path) -> None:
    baseline = _baseline(tmp_path)
    with single_run_lock(baseline):
        pass
    # Lock released on exit; a second, non-overlapping run must succeed.
    with single_run_lock(baseline):
        pass


def test_preflight_validates_isolated_database_kg_and_vector_sources(tmp_path: Path) -> None:
    kg_path = tmp_path / "kg.json"
    vector_path = tmp_path / "vector.json"
    kg_path.write_text(
        json.dumps({"concepts": [{"id": "c1", "name": "Duration"}]}),
        encoding="utf-8",
    )
    vector_path.write_text(json.dumps({"items": []}), encoding="utf-8")
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(
        json.dumps(
            {
                "daily_card_sets": 1,
                "cards_per_set": 1,
                "review_limit": 10,
                "card_gen_model": "test",
                "feynman_model": "test",
                "challenger_model": "test",
                "prompt_versions": {},
                "database_root": str(tmp_path / "database"),
                "sqlite_relative_path": "study.db",
                "kg_concepts_path": str(kg_path),
                "vector_snippets_path": str(vector_path),
                "generation_backend": "template",
            }
        ),
        encoding="utf-8",
    )

    result = preflight_check(baseline_path)

    assert result["status"] == "ok"
    assert Path(str(result["database"])).exists()

    first = run_generation_job(baseline_path=baseline_path)
    second = run_generation_job(baseline_path=baseline_path)
    assert first["cards_inserted"] == 1
    assert second["cards_inserted"] == 0

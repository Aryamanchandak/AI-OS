"""Headless automation entry point for bounded study-system card generation.

This is an adapter, not a reimplementation: all learning logic lives in the
sibling `Learning System` project's `StudyCore`
(Learning System/plans/00_RESOLVED_MVP_AND_ARCHITECTURE.md §2). This file's only
job is to construct a `StudyCore` from the versioned baseline and run one
bounded generation job under a single-run lock. See
Learning System/plans/10_AUTOMATION_ADAPTER_RELOCATION_PLAN.md for why this
adapter lives in its own project rather than inside Learning System.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _find_workspace_root() -> Path:
    """Locate the `AI Code` workspace that holds this project and Learning System."""

    env = os.environ.get("AI_CODE_ROOT")
    if env:
        return Path(env).resolve()
    here = Path(__file__).resolve()
    for parent in here.parents:
        if parent.name == "AI Code":
            return parent
    raise RuntimeError(
        "Could not locate the AI Code workspace root. Set AI_CODE_ROOT to the "
        "directory containing 'Learning System'."
    )


# The sibling `Learning System` project provides the study_system package this
# adapter calls into. It is not pip-installed here — same plain sys.path
# convention mcp_server/mcp_server.py already uses for the same package.
_STUDY_SYSTEM_SRC = _find_workspace_root() / "Learning System" / "src"
if str(_STUDY_SYSTEM_SRC) not in sys.path:
    sys.path.insert(0, str(_STUDY_SYSTEM_SRC))

import argparse  # noqa: E402
import contextlib  # noqa: E402
import errno  # noqa: E402
import fcntl  # noqa: E402
import json  # noqa: E402

from study_system.core.baseline import BASELINE_PATH, StudyBaseline, load_baseline  # noqa: E402
from study_system.core.gateway import (  # noqa: E402
    GatewayCardGenerator,
    GatewayPracticeEvaluator,
    GatewayQualityChecker,
    LLMGateway,
)
from study_system.core.study_core import (  # noqa: E402
    StructuralQualityChecker,
    StudyCore,
    TemplateCardGenerator,
)
from study_system.repositories.json_repositories import (  # noqa: E402
    JsonKGRepository,
    JsonVectorRepository,
)
from study_system.storage.mvp_store import MVPStore  # noqa: E402


class AlreadyRunningError(RuntimeError):
    """Raised when another automation run already holds the single-run lock."""


@contextlib.contextmanager
def single_run_lock(baseline: StudyBaseline):  # type: ignore[no-untyped-def]
    """Prevent overlapping automation runs (plan 02 §3/§4/§10).

    Uses an advisory `flock` on a lock file under the central Database root
    rather than either repo, so no runtime state is written inside a checkout
    and the lock is visible/cleanable outside any one repo.
    """

    lock_dir = baseline.database_root / "Locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / "study_automation.lock"
    fd = open(lock_path, "w")
    try:
        try:
            fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EAGAIN):
                raise AlreadyRunningError(
                    f"Another study automation run holds the lock at {lock_path}"
                ) from exc
            raise
        yield
    finally:
        fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
        fd.close()


def build_core(baseline_path: Path = BASELINE_PATH, *, preflight: bool = True) -> StudyCore:
    baseline = load_baseline(baseline_path)
    if baseline.kg_concepts_path is None:
        raise RuntimeError(
            "kg_concepts_path is not configured in config/baseline.json. "
            "Set it to a final KG export or wire a production KG adapter before running automation."
        )
    if baseline.vector_snippets_path is None:
        raise RuntimeError(
            "vector_snippets_path is not configured in config/baseline.json. "
            "Set it to the final vector export before running automation."
        )
    store = MVPStore(baseline.sqlite_path)
    kg = JsonKGRepository(baseline.kg_concepts_path)
    vector = JsonVectorRepository(baseline.vector_snippets_path)
    gateway = LLMGateway(baseline.llm_gateway_url, baseline.gateway_timeout_seconds)
    if baseline.generation_backend == "gateway" and preflight:
        gateway.check_available()
    generator = (
        GatewayCardGenerator(gateway)
        if baseline.generation_backend == "gateway"
        else TemplateCardGenerator()
    )
    quality = (
        GatewayQualityChecker(gateway)
        if baseline.generation_backend == "gateway" and baseline.quality_backend == "gateway"
        else StructuralQualityChecker()
    )
    return StudyCore(
        baseline=baseline,
        store=store,
        kg=kg,
        vector=vector,
        generator=generator,
        quality=quality,
        practice_evaluator=GatewayPracticeEvaluator(gateway),
    )


def preflight_check(baseline_path: Path = BASELINE_PATH) -> dict[str, object]:
    baseline = load_baseline(baseline_path)
    core = build_core(baseline_path, preflight=True)
    core.close()
    return {
        "status": "ok",
        "database": str(baseline.sqlite_path),
        "kg": str(baseline.kg_concepts_path),
        "vector": str(baseline.vector_snippets_path),
        "gateway": baseline.llm_gateway_url,
        "generation_backend": baseline.generation_backend,
    }


def run_generation_job(
    *, baseline_path: Path = BASELINE_PATH, count: int | None = None
) -> dict[str, object]:
    baseline = load_baseline(baseline_path)
    with single_run_lock(baseline):
        core = build_core(baseline_path)
        try:
            return core.generate_unseen_cards(temporary_count=count)
        finally:
            core.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run one bounded study-system card generation job.")
    parser.add_argument("--baseline", type=Path, default=BASELINE_PATH)
    parser.add_argument("--count", type=int, default=None, help="Temporary concept count for this run.")
    parser.add_argument("--check", action="store_true", help="Validate dependencies and exit.")
    args = parser.parse_args(argv)
    try:
        result = (
            preflight_check(args.baseline)
            if args.check
            else run_generation_job(baseline_path=args.baseline, count=args.count)
        )
    except Exception as exc:
        print(f"study automation failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

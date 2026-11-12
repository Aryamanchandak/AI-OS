"""Versioned baseline configuration plus audited runtime overrides.

The baseline file is code-adjacent configuration. Runtime tools do not write it;
temporary changes are stored in SQLite overrides and merged at read time.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import Any


BASELINE_PATH = Path(__file__).resolve().parents[3] / "config" / "baseline.json"

OVERRIDABLE_SETTINGS = {
    "daily_card_sets": int,
    "cards_per_set": int,
    "review_limit": int,
}


# Fallback ceilings used when config/baseline.json does not set
# `override_max_values` for a given setting. Plan 02 §7 requires override
# values to be bounded; these defaults ensure that holds even for an
# unconfigured baseline file.
DEFAULT_OVERRIDE_MAX_VALUES: dict[str, int] = {
    "daily_card_sets": 20,
    "cards_per_set": 20,
    "review_limit": 200,
}


@dataclass(frozen=True)
class StudyBaseline:
    daily_card_sets: int
    cards_per_set: int
    review_limit: int
    card_gen_model: str
    feynman_model: str
    challenger_model: str
    prompt_versions: dict[str, str]
    database_root: Path
    sqlite_relative_path: str
    kg_concepts_path: Path | None = None
    vector_snippets_path: Path | None = None
    override_max_values: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_OVERRIDE_MAX_VALUES))
    llm_gateway_url: str = "http://127.0.0.1:8107"
    generation_backend: str = "gateway"
    quality_min_front_chars: int = 1
    quality_min_back_chars: int = 1
    gateway_timeout_seconds: float = 120.0
    quality_backend: str = "structural"
    quality_model: str = "gpt-4o-mini"
    rubric_fail_threshold: float = 2.5
    grounding_min_confidence: float = 0.5
    fsrs_weights: tuple[float, ...] = ()

    @property
    def sqlite_path(self) -> Path:
        return self.database_root / self.sqlite_relative_path

    def to_jsonable(self) -> dict[str, Any]:
        data = asdict(self)
        data["database_root"] = str(self.database_root)
        data["sqlite_path"] = str(self.sqlite_path)
        data["kg_concepts_path"] = str(self.kg_concepts_path) if self.kg_concepts_path else None
        data["vector_snippets_path"] = str(self.vector_snippets_path) if self.vector_snippets_path else None
        return data


def default_database_root(start: Path | None = None) -> Path:
    """Resolve the central Database root.

    Priority:
    1. STUDY_SYSTEM_DATABASE_ROOT, if set.
    2. A sibling `Database/` under the nearest ancestor named `AI Code`.
    3. A workspace-local `Database/` fallback.
    """

    override = os.environ.get("STUDY_SYSTEM_DATABASE_ROOT")
    if override:
        return Path(override).expanduser().resolve()

    cursor = (start or Path.cwd()).resolve()
    for parent in (cursor, *cursor.parents):
        if parent.name == "AI Code":
            return parent / "Database"
    return cursor / "Database"


def _optional_path(value: Any, base_dir: Path) -> Path | None:
    if value in (None, ""):
        return None
    path = Path(str(value)).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def load_baseline(path: Path = BASELINE_PATH) -> StudyBaseline:
    raw = json.loads(path.read_text(encoding="utf-8"))
    database_root_raw = raw.get("database_root")
    database_root = (
        Path(database_root_raw).expanduser().resolve()
        if database_root_raw
        else default_database_root(path.parent)
    )
    baseline = StudyBaseline(
        daily_card_sets=int(raw["daily_card_sets"]),
        cards_per_set=int(raw["cards_per_set"]),
        review_limit=int(raw["review_limit"]),
        card_gen_model=str(raw["card_gen_model"]),
        feynman_model=str(raw["feynman_model"]),
        challenger_model=str(raw["challenger_model"]),
        prompt_versions=dict(raw.get("prompt_versions", {})),
        database_root=database_root,
        sqlite_relative_path=str(raw["sqlite_relative_path"]),
        kg_concepts_path=_optional_path(raw.get("kg_concepts_path"), path.parent),
        vector_snippets_path=_optional_path(raw.get("vector_snippets_path"), path.parent),
        override_max_values={**DEFAULT_OVERRIDE_MAX_VALUES, **dict(raw.get("override_max_values", {}))},
        llm_gateway_url=str(raw.get("llm_gateway_url", "http://127.0.0.1:8107")).rstrip("/"),
        generation_backend=str(raw.get("generation_backend", "gateway")),
        quality_min_front_chars=int(raw.get("quality_min_front_chars", 8)),
        quality_min_back_chars=int(raw.get("quality_min_back_chars", 8)),
        gateway_timeout_seconds=float(raw.get("gateway_timeout_seconds", 120.0)),
        quality_backend=str(raw.get("quality_backend", "gateway")),
        quality_model=str(raw.get("quality_model", raw["card_gen_model"])),
        rubric_fail_threshold=float(raw.get("rubric_fail_threshold", 2.5)),
        grounding_min_confidence=float(raw.get("grounding_min_confidence", 0.5)),
        fsrs_weights=tuple(float(value) for value in raw.get("fsrs_weights", [])),
    )
    if baseline.daily_card_sets < 1 or baseline.cards_per_set < 1 or baseline.review_limit < 1:
        raise ValueError("daily_card_sets, cards_per_set, and review_limit must all be >= 1")
    if baseline.generation_backend not in {"gateway", "template"}:
        raise ValueError("generation_backend must be 'gateway' or 'template'")
    if baseline.quality_backend not in {"gateway", "structural"}:
        raise ValueError("quality_backend must be 'gateway' or 'structural'")
    if not baseline.llm_gateway_url.startswith(("http://", "https://")):
        raise ValueError("llm_gateway_url must be an http(s) URL")
    if baseline.quality_min_front_chars < 1 or baseline.quality_min_back_chars < 1:
        raise ValueError("quality minimum lengths must be >= 1")
    if not 1.0 <= baseline.rubric_fail_threshold <= 5.0:
        raise ValueError("rubric_fail_threshold must be between 1 and 5")
    if not 0.0 <= baseline.grounding_min_confidence <= 1.0:
        raise ValueError("grounding_min_confidence must be between 0 and 1")
    if baseline.fsrs_weights and len(baseline.fsrs_weights) != 19:
        raise ValueError("fsrs_weights must contain exactly 19 FSRS-4.5 values")
    return baseline


def validate_override(setting: str, value: Any, max_values: dict[str, int] | None = None) -> Any:
    if setting not in OVERRIDABLE_SETTINGS:
        allowed = ", ".join(sorted(OVERRIDABLE_SETTINGS))
        raise ValueError(f"Setting {setting!r} cannot be overridden. Allowed: {allowed}")
    if isinstance(value, bool):
        raise ValueError(f"Override {setting!r} must be an integer")
    if isinstance(value, float) and not value.is_integer():
        raise ValueError(f"Override {setting!r} must be an integer")
    try:
        value = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Override {setting!r} must be an integer") from exc
    if value < 1:
        raise ValueError(f"Override {setting!r} must be >= 1")
    ceiling = (max_values or DEFAULT_OVERRIDE_MAX_VALUES).get(setting)
    if ceiling is not None and value > ceiling:
        raise ValueError(f"Override {setting!r} must be <= {ceiling}")
    return value


def merge_overrides(
    baseline: StudyBaseline,
    active_overrides: dict[str, Any],
    *,
    today: date | None = None,
) -> StudyBaseline:
    """Return a new effective config after validating active overrides."""

    del today  # retained for call-site readability and future date-sensitive rules.
    effective = baseline
    for setting, value in active_overrides.items():
        validated = validate_override(setting, value, baseline.override_max_values)
        effective = replace(effective, **{setting: validated})
    return effective


def effective_config_json(config: StudyBaseline) -> str:
    return json.dumps(config.to_jsonable(), sort_keys=True)

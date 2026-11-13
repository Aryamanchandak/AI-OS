"""Known answers for the runner's constraints and the key-free browser run."""
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dry_run_shoes import evaluate, load_profile, run_dry_run


def product():
    return dict(model="Sample road shoe", retailer="Fictional shop",
                price=150, currency="USD", size=11, size_system="UK",
                category="men", in_stock=True, delivery=True,
                surface="road")


def test_confirmed_profile():
    profile = load_profile()
    assert profile["budget"] == {"amount": 200, "currency": "USD"}
    assert profile["size"] == {"value": 11, "system": "UK"}
    assert profile["category"] == "men"
    assert profile["delivery"] == {"city": "Mumbai", "postcode": "400054"}
    assert profile["current_surface"] == "treadmill"
    assert profile["intended_surface"] == "road"


@pytest.mark.parametrize("changes,status", [
    ({}, "eligible"),
    ({"price": 200}, "eligible"),
    ({"price": 201}, "excluded"),
    ({"size": 10}, "excluded"),
    ({"size_system": "US"}, "excluded"),
    ({"in_stock": False}, "excluded"),
    ({"delivery": False}, "excluded"),
    ({"in_stock": None}, "unverified"),
    ({"delivery": None}, "unverified"),
    ({"currency": "INR", "price": 10000}, "unverified"),
])
def test_no_relaxing_constraints(changes, status):
    row = product()
    row.update(changes)
    assert evaluate(row, load_profile())[0] == status


async def test_real_browser_dry_run_creates_trace_and_report(tmp_path):
    result = await run_dry_run(tmp_path, session_id="test-shoes-dry-run")
    assert len(result["rows"]) == 3
    assert len(result["excluded"]) == 3
    assert result["interactive_actions"] >= 3
    assert result["paid_calls"] == 0
    assert result["all_nodes_complete"]
    assert result["critic_verdict"] == "pass"
    report = Path(result["report"]).read_text()
    assert "DRY RUN" in report and "FICTIONAL" in report
    for section in ("goal", "dag", "path", "actions", "shots", "extracted", "final", "cost"):
        assert f'<section id="{section}">' in report
    assert "data:image/png;base64," in report
    assert len(list(tmp_path.rglob("turn_*_state.txt"))) >= 3
    assert (tmp_path / "test-shoes-dry-run" / "graph.json").is_file()
    assert (tmp_path / "test-shoes-dry-run" / "comparison.md").is_file()

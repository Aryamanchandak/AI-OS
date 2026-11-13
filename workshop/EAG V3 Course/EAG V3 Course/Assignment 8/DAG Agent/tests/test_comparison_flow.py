import json

from agent.comparison_service import run_comparison
from tests.test_comparison import comparison_request


def test_supplied_evidence_reaches_sourced_answer(comparison_request, tmp_path):
    result, log = run_comparison(comparison_request, tmp_path)
    assert log.status == "completed"
    assert len(log.layers[0]) == 3
    assert "1,200" in log.answer
    assert "Missing" in log.answer
    assert "[sa]" in log.answer
    assert result["cells"]["a"]["cost"]["value"] == 1200
    assert (tmp_path / "state.json").exists()
    assert (tmp_path / "comparison.json").exists()


def test_follow_up_reuses_evidence_but_recalculates(comparison_request, tmp_path):
    run_comparison(comparison_request, tmp_path / "first")
    comparison_request["criteria"][0]["weight"] = 1
    result, log = run_comparison(comparison_request, tmp_path / "second", reuse=tmp_path / "first")
    assert result["ranking"][0]["option"] == "c"
    assert len(log.reused_nodes) == 3
    assert "Weighted" in log.answer


def test_changed_source_is_never_reused(comparison_request, tmp_path):
    run_comparison(comparison_request, tmp_path / "first")
    option = comparison_request["options"][0]
    option["sources"][0]["text"] = "Costs INR 200 per month. Email support."
    option["evidence"]["cost"]["value"] = 200
    option["evidence"]["cost"]["quote"] = "Costs INR 200 per month."
    result, log = run_comparison(comparison_request, tmp_path / "second", reuse=tmp_path / "first")
    assert result["cells"]["a"]["cost"]["value"] == 2400
    assert "read_a" not in log.reused_nodes


def test_resume_rechecks_unverified_producers(comparison_request, tmp_path):
    _, paused = run_comparison(comparison_request, tmp_path, stop_after=1)
    assert paused.status == "paused"
    result, resumed = run_comparison(None, tmp_path)
    assert resumed.status == "completed"
    assert result["cells"]["c"]["cost"]["value"] == 900


def test_numerical_chart_is_created_from_verified_values(comparison_request, tmp_path):
    comparison_request["chart"] = "cost"
    _, log = run_comparison(comparison_request, tmp_path)
    assert log.status == "completed"
    assert (tmp_path / "artifacts/cost.png").read_bytes().startswith(b"\x89PNG")
    assert "Chart:" in log.answer


def test_extractor_reply_wrapped_in_a_code_fence_is_still_read(comparison_request):
    from agent.comparison_tools import align
    context = {"read_" + o["id"]: json.dumps({"kind": "sources", "option": o})
               for o in comparison_request["options"]}
    first = comparison_request["options"][0]
    context["extract_" + first["id"]] = ("Here is the evidence:\n```json\n" + json.dumps(
        {"option": first["id"], "evidence": first["evidence"]}) + "\n```")
    result = json.loads(align(json.dumps(comparison_request), context))
    assert result["cells"][first["id"]]["cost"]["value"] == 1200


def test_extractor_reply_with_no_json_still_stops_the_run(comparison_request):
    import pytest
    from agent.comparison_tools import align
    context = {"read_" + o["id"]: json.dumps({"kind": "sources", "option": o})
               for o in comparison_request["options"]}
    context["extract_a"] = "I could not find anything."
    with pytest.raises(ValueError):
        align(json.dumps(comparison_request), context)

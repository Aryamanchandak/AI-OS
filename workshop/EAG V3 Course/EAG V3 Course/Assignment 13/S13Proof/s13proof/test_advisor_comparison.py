"""Paired comparisons must retain failures, overhead, and human-review boundaries."""
from __future__ import annotations

import csv
import json
import socket
from unittest.mock import patch

import pytest
import httpx

import s13proof.advisor_comparison as comparison
from s13code.gateway import GatewayClient
from s13proof.advisor_comparison import compare, load_config, run, write_review_sheet


@pytest.mark.asyncio
async def test_dry_run_is_network_free_and_never_claims_live_improvement(tmp_path):
    with patch.object(socket.socket, "connect", side_effect=AssertionError("Unexpected network")):
        report = await run(mode="dry-run")
    assert report["mode"] == "dry-run"
    assert report["judgment_quality_verified"] is False
    assert report["case_labels"] == "draft-needs-human-review"
    assert len(report["cases"]) >= 13
    assert report["summary"]["completed_pairs"] == len(report["cases"])
    assert all(case["with_advice"]["metrics"]["model_calls"] >= 2 for case in report["cases"])
    assert all(case["without_advice"]["metrics"]["model_calls"] == 1 for case in report["cases"])
    assert all(case["with_advice"]["metrics"]["cost"] is None for case in report["cases"])
    sheet = tmp_path / "reviews.csv"
    write_review_sheet(report, sheet)
    with sheet.open() as file:
        rows = list(csv.DictReader(file))
    assert len(rows) == len(report["cases"]) * 2
    assert all(row["unsupported_claim_count"] == "" and row["citations_accurate"] == "" for row in rows)
    assert {row["arm"] for row in rows} == {"without_advice", "with_advice"}


@pytest.mark.asyncio
async def test_same_initial_draft_is_shared_and_bad_advice_is_counted_as_regression():
    calls = []
    case = {"id": "preserve", "question": "What uses attention?", "claim": "The Transformer uses attention.",
            "expected_verdict": "supported", "source": "attention.txt", "quote": "based solely on attention mechanisms"}

    async def mistaken_advisor(role, case_id, prompt, system):
        assert "expected_verdict" not in prompt
        assert "draft-needs-human-review" not in prompt
        payload = json.loads(prompt)
        calls.append(role)
        record = next(card for card in payload["evidence"] if "based solely on attention mechanisms" in card["text"])
        verdict = "supported" if role == "worker" else "contradicted"
        return {"text": json.dumps({"summary": "A fixture conclusion.", "followup_query": None,
            "assessments": [{"claim": case["claim"], "verdict": verdict, "reason": "Fixture judgment.",
                "citations": [{"record_id": record["record_id"], "quote": "based solely on attention mechanisms"}]}]}),
                "provider": role, "model": "fixture", "input_tokens": 10, "output_tokens": 5}

    report = await compare([case], mistaken_advisor, mode="test")
    assert calls == ["worker", "advisor", "revision"]
    assert report["summary"]["label_regressions"] == 1
    row = report["cases"][0]
    assert row["without_advice"]["metrics"]["input_tokens"] == 10
    assert row["with_advice"]["metrics"]["input_tokens"] == 30
    assert row["with_advice"]["initial_draft"] == row["without_advice"]["result"]


@pytest.mark.asyncio
async def test_provider_failure_is_retained_without_leaking_error_body():
    async def fail(*_args):
        raise RuntimeError("private provider body")

    case = {"id": "failure", "question": "What uses attention?", "claim": "The Transformer uses attention.",
            "expected_verdict": "supported", "source": "attention.txt", "quote": "attention mechanisms"}
    report = await compare([case], fail, mode="test")
    assert len(report["cases"]) == 1
    assert report["summary"]["completed_pairs"] == 0
    assert report["status"] == "incomplete"
    assert "private provider body" not in json.dumps(report)
    assert report["cases"][0]["without_advice"]["metrics"]["input_tokens"] is None


def test_comparison_loads_dotenv_before_resolving_every_setting(tmp_path, monkeypatch):
    names = ["GLC_BASE_URL", "S13_GATEWAY_PROVIDER", "S13_COMPARISON_WORKER_PROVIDER",
             "S13_COMPARISON_ADVISOR_PROVIDER"]
    for name in names:
        monkeypatch.delenv(name, raising=False)
    file = tmp_path / ".env"
    file.write_text("GLC_BASE_URL=http://fixture.test\nS13_GATEWAY_PROVIDER=default\n"
                    "S13_COMPARISON_WORKER_PROVIDER=worker\nS13_COMPARISON_ADVISOR_PROVIDER=advisor\n")
    assert load_config(file) == {"base_url": "http://fixture.test", "worker_provider": "worker",
                                 "advisor_provider": "advisor"}
    monkeypatch.delenv("S13_COMPARISON_WORKER_PROVIDER")
    monkeypatch.delenv("S13_COMPARISON_ADVISOR_PROVIDER")
    assert load_config(tmp_path / "absent") == {"base_url": "http://fixture.test",
                                                "worker_provider": "default", "advisor_provider": "default"}


@pytest.mark.asyncio
async def test_live_wiring_uses_gateway_roles_with_no_label_leakage(monkeypatch):
    captured = []

    async def handler(request):
        if request.method == "GET":
            assert request.url.path == "/healthz"
            return httpx.Response(200, json={"ok": True})
        body = json.loads(request.content)
        prompt = body["messages"][0]["content"]
        assert "expected_verdict" not in prompt
        payload = json.loads(prompt)
        captured.append(body)
        card = payload["evidence"][0]
        verdict = "supported" if body["provider"] == "worker-slot" else "contradicted"
        text = json.dumps({"summary": "Mocked live response.", "followup_query": None, "assessments": [{
            "claim": payload["claims"][0], "verdict": verdict, "reason": "Fixture response.",
            "citations": [{"record_id": card["record_id"], "quote": card["text"][:60]}]}]})
        return httpx.Response(200, json={"text": text, "provider": body["provider"], "model": "mock",
                                        "input_tokens": 20, "output_tokens": 10})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        monkeypatch.setattr(comparison, "GatewayClient", lambda base_url: GatewayClient(base_url, client=http))
        report = await run(mode="live", config={"base_url": "http://gateway.test",
                                                "worker_provider": "worker-slot", "advisor_provider": "advisor-slot"})
    assert report["status"] == "completed"
    assert report["judgment_quality_verified"] is False
    assert [body["provider"] for body in captured[:3]] == ["worker-slot", "advisor-slot", "worker-slot"]
    assert all(body["session"].startswith(report["run_id"] + ":") for body in captured)


@pytest.mark.asyncio
async def test_invalid_reference_and_empty_cases_fail_before_spending_calls():
    async def forbidden(*_args):
        pytest.fail("Invalid references must not spend a call")

    with pytest.raises(ValueError, match="nonempty"):
        await compare([], forbidden, mode="test")
    with pytest.raises(ValueError, match="reference label"):
        await compare([{"id": "valid", "source": "attention.txt", "quote": "attention mechanisms",
                        "expected_verdict": "supported"},
                       {"id": "invalid", "source": "attention.txt", "quote": "invented reference",
                        "expected_verdict": "supported"}], forbidden, mode="test")


def test_review_csv_cannot_execute_a_formula_from_model_output(tmp_path):
    result = {"summary": '=HYPERLINK("https://fixture.invalid")',
              "assessments": [{"verdict": "unclear", "citations": []}]}
    report = {"run_id": "test", "cases": [{"id": "csv", "question": "Question", "claim": "Claim",
        "reference": {"expected_verdict": "unclear"}, "without_advice": {"result": result},
        "with_advice": {"result": result}}]}
    output = tmp_path / "review.csv"
    write_review_sheet(report, output)
    with output.open() as file:
        rows = list(csv.DictReader(file))
    assert all(row["answer"].startswith("'=") for row in rows)


def test_incomplete_cli_preserves_report_and_exits_nonzero(tmp_path, monkeypatch):
    async def failed_run(**_kwargs):
        return {"run_id": "test", "mode": "dry-run", "status": "incomplete", "summary": {}, "cases": []}

    output = tmp_path / "comparison.json"
    monkeypatch.setattr(comparison, "run", failed_run)
    monkeypatch.setattr("sys.argv", ["comparison", "--output", str(output), "--env-file", str(tmp_path / "absent")])
    with pytest.raises(SystemExit) as result:
        comparison.main()
    assert result.value.code == 1
    assert json.loads(output.read_text())["status"] == "incomplete"

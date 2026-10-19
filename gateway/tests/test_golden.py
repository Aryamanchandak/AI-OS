"""Golden set: real requests through the real app, using keys from gateway/.env.

Skipped in the normal run; costs money. Run with `.venv/bin/pytest -m golden -v`.
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest
import yaml

from conftest import REAL_ENV_FILE
import gateway.env
from gateway.llm.models import ChatResponse, EmbedResponse
from main import create_app


CASES = yaml.safe_load((Path(__file__).parent / "golden" / "cases.yaml").read_text(encoding="utf-8"))
AUTH = {"Authorization": "Bearer golden-token"}


@pytest.mark.golden
@pytest.mark.parametrize("case", CASES, ids=[case["name"] for case in CASES])
def test_golden_case(case, tmp_path, monkeypatch) -> None:
    # A private ledger, so row counts are exact and the $0 budget never reaches the real database.
    monkeypatch.setenv("GLC_GATEWAY_DB", str(tmp_path / "gateway.sqlite"))
    monkeypatch.setattr(gateway.env, "ENV_FILE", REAL_ENV_FILE)
    expect = case["expect"]
    with TestClient(create_app(token="golden-token")) as client:
        if budget := case.get("budget"):
            client.post("/api/llm/budget", headers=AUTH, json=budget).raise_for_status()
        response = client.post(f"/api/llm/{case['call']}", headers=AUTH, json=case["request"])
        rows = client.get("/api/llm/calls", headers=AUTH).json()

    assert response.status_code == expect.get("status", 200), response.text
    assert len(rows) == expect["ledger_rows"]
    if response.status_code != 200:
        return
    if case["call"] == "embed":
        reply = EmbedResponse.model_validate(response.json())
        assert reply.dim == len(reply.embedding) == expect["dim"]
        return
    reply = ChatResponse.model_validate(response.json())
    if "text" in expect:
        assert reply.text.strip() == expect["text"]
    if expect.get("cost_above_zero"):
        assert reply.input_tokens > 0 and reply.output_tokens > 0
        assert rows[0]["usd"] > 0
    if names := expect.get("parsed_names_include"):
        assert reply.parsed is not None
        assert set(names) <= {entity["name"] for entity in reply.parsed["entities"]}

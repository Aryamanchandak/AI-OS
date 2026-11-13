"""End-to-end evidence for the assignment's Critic, Coder, and new skill."""

import json
import pathlib
import urllib.error

from agent import tools
from agent.executor import Executor
from agent.mock_llm import MockLLM
from agent.planner import Planner
from agent.skills import load_config, load_skills


class CapturingExecutor(Executor):
    """Keep node results visible to assertions without changing RunLog."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.captured = {}

    def _run_node(self, node, upstream):
        result = super()._run_node(node, upstream)
        self.captured[node.id] = result
        return result


def _agent(tmp_path, monkeypatch):
    def offline(*_args, **_kwargs):
        raise urllib.error.URLError("offline test")

    monkeypatch.setattr(tools, "_from_stooq", offline)
    config = load_config()
    skills = load_skills(config)
    llm = MockLLM()
    planner = Planner(skills, llm)
    executor = CapturingExecutor(
        skills, llm, pathlib.Path(tmp_path), replan=planner.replan
    )
    return planner, executor


def test_critic_checks_every_declared_field():
    llm = MockLLM()
    good = {
        "_conventions": {"trading_days_per_year": 252},
        "AMD": {"points": 252, "cagr_pct": 12.5},
        "NVDA": {"points": 252, "cagr_pct": -3.0},
    }
    verdict = json.loads(llm._critic("PRODUCER OUTPUT:\n" + json.dumps(good)))
    assert verdict == {"verdict": "pass", "reason": ""}

    missing_cagr = {"AMD": {"points": 252}}
    verdict = json.loads(
        llm._critic("PRODUCER OUTPUT:\n" + json.dumps(missing_cagr))
    )
    assert verdict["verdict"] == "fail"
    assert "AMD" in verdict["reason"] and "cagr_pct" in verdict["reason"]


def test_critic_fail_splices_complete_corrected_answer(tmp_path, monkeypatch):
    planner, executor = _agent(tmp_path, monkeypatch)
    tools.DEGRADED_TICKERS.add("AMD")
    try:
        graph = planner.plan("compare NVDA, AMD and INTC")
        log = executor.run(graph, "compare NVDA, AMD and INTC")
    finally:
        tools.DEGRADED_TICKERS.discard("AMD")

    assert log.iterations == 2
    assert log.critic_verdicts[0]["verdict"] == "fail"
    assert "AMD" in log.critic_verdicts[0]["reason"]
    assert log.recoveries[0]["strategy"] == "refetch_upstream"

    recovery_id = log.recoveries[0]["spliced"][-1]
    recovered = json.loads(executor.captured[recovery_id].output)
    assert {"AMD", "INTC", "NVDA"} <= recovered.keys()
    assert all(recovered[ticker]["points"] >= 200
               for ticker in ("AMD", "INTC", "NVDA"))

    # The user-facing answer, not merely an internal node, contains all three
    # corrected computed rows.
    assert all(f"| {ticker} | 252 |" in log.answer
               for ticker in ("AMD", "INTC", "NVDA"))
    assert "degraded-stub" not in log.answer


def test_coder_computation_reaches_final_answer(tmp_path, monkeypatch):
    planner, executor = _agent(tmp_path, monkeypatch)
    graph = planner.plan("compare NVDA, AMD and INTC")
    log = executor.run(graph, "compare NVDA, AMD and INTC")

    metrics = json.loads(executor.captured["metrics"].output)
    for ticker in ("AMD", "INTC", "NVDA"):
        assert isinstance(metrics[ticker]["cagr_pct"], (int, float))
        assert isinstance(metrics[ticker]["vol_pct"], (int, float))
        assert f"| {ticker} | 252 |" in log.answer
    assert log.critic_verdicts == [
        {"node": "metrics", "verdict": "pass", "reason": ""}
    ]


def test_charter_creates_and_reports_png(tmp_path, monkeypatch):
    planner, executor = _agent(tmp_path, monkeypatch)
    query = "compare NVDA, AMD and INTC with a chart"
    graph = planner.plan(query)
    log = executor.run(graph, query)

    chart = json.loads(executor.captured["chart"].output)
    artifact = pathlib.Path(chart["chart"])
    assert artifact.exists()
    assert artifact.suffix == ".png"
    assert str(artifact) in executor.captured["chart"].artifacts
    assert f"Chart artifact: {artifact}" in log.answer

"""Unit tests for the recovery classifier.

Per the architectural rules, these must keep passing after any change to the
agent. Run: python -m pytest tests/ -q
"""

import pytest

from agent.recovery import Recovery, Strategy, classify, recovery_instruction


class TestClassify:
    @pytest.mark.parametrize("reason", [
        "AMD series has only 5 close prices — incomplete series",
        "the NVDA quote is stale",
        "missing data for INTC",
        "no data returned for the requested window",
        "insufficient history to compute a one-year CAGR",
        "fewer than 200 close prices were returned",
    ])
    def test_data_problems_refetch(self, reason):
        assert classify("fail", reason).strategy is Strategy.REFETCH_UPSTREAM

    @pytest.mark.parametrize("reason", [
        "the weights do not sum to 1.0 (got 0.94)",
        "arithmetic error: CAGR reported as 41% but computes to 38%",
        "the allocation sums to 103%",
        "volatility is off by a factor of sqrt(252)",
        "miscalculated Sharpe ratio",
    ])
    def test_number_problems_recompute(self, reason):
        assert classify("fail", reason).strategy is Strategy.RECOMPUTE

    @pytest.mark.parametrize("reason", [
        "the claimed dividend yield is unsupported by the retrieved data",
        "the 2019 figure is not present in the upstream output",
        "fabricated a P/E ratio that never appears in the source",
        "the revenue claim cannot be traced to any node output",
    ])
    def test_ungrounded_claims_reground(self, reason):
        assert classify("fail", reason).strategy is Strategy.REGROUND

    @pytest.mark.parametrize("reason", [
        "the producer timed out",
        "output was truncated mid-object",
        "empty output from the coder node",
        "malformed JSON in the producer output",
    ])
    def test_transient_problems_retry(self, reason):
        assert classify("fail", reason).strategy is Strategy.RETRY_PRODUCER

    def test_unrecognised_reason_escalates(self):
        rec = classify("fail", "the vibes are off")
        assert rec.strategy is Strategy.ESCALATE
        assert rec.reason == "the vibes are off"

    @pytest.mark.parametrize("reason", ["", "   ", None])
    def test_empty_reason_escalates(self, reason):
        assert classify("fail", reason).strategy is Strategy.ESCALATE

    def test_passing_verdict_is_a_programming_error(self):
        with pytest.raises(ValueError):
            classify("pass", "everything checks out")

    def test_verdict_is_case_and_space_insensitive(self):
        with pytest.raises(ValueError):
            classify("  PASS  ", "fine")

    def test_specificity_order_data_beats_arithmetic(self):
        # Mentions both a data problem and a sum; refetching is the right fix,
        # because recomputing on missing data reproduces the failure.
        rec = classify("fail", "missing data for AMD, so the weights do not sum to 1")
        assert rec.strategy is Strategy.REFETCH_UPSTREAM

    def test_reason_is_preserved_verbatim(self):
        reason = "AMD series has only 5 close prices — incomplete series"
        assert classify("fail", reason).reason == reason


class TestRecoveryInstruction:
    def test_includes_reason_and_original_task(self):
        rec = Recovery(Strategy.REFETCH_UPSTREAM, "incomplete series for AMD")
        text = recovery_instruction(rec, "Compute CAGR for NVDA, AMD, INTC")
        assert "incomplete series for AMD" in text
        assert "Compute CAGR for NVDA, AMD, INTC" in text
        assert "Re-fetch" in text

    @pytest.mark.parametrize("strategy", list(Strategy))
    def test_every_strategy_has_guidance(self, strategy):
        text = recovery_instruction(Recovery(strategy, "because"), "task")
        assert len(text.splitlines()[0]) > 20

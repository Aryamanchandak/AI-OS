"""Scripted stand-in for Claude.

Exists so the *architecture* claims — parallel wall-clock, the Critic gate,
recovery splicing, sandbox execution — can be demonstrated and regression
tested without an API key. It is not a model: it pattern-matches the system
prompt to decide which role it is playing.

Real runs use agent.llm.ClaudeLLM. Never present mock output as model output.
"""

from __future__ import annotations

import json
import re


class MockLLM:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))

        if "You are the Planner" in system:
            return self._plan(user)
        if "You are the Critic" in system:
            return self._critic(user)
        if "You are the Coder" in system:
            return _CODER_SCRIPT
        if "You are the Charter" in system:
            return _CHARTER_SCRIPT
        if "You are the Formatter" in system:
            return self._format(user)
        return "mock: unrecognised role"

    # ---------- planner ----------

    def _plan(self, user: str) -> str:
        if "RECOVERY SUBGRAPH" in user:
            original_deps = re.findall(r'"(fetch_[A-Z]{1,5})"', user)
            original_tickers = [dep.removeprefix("fetch_") for dep in original_deps]

            # The Critic names the offending ticker in its reason. Limit the
            # match to tickers that were actually in the failed node so prompt
            # labels such as JSON/RECOVERY can never become retrieval work.
            offenders = [t for t in _tickers(user) if t in original_tickers]

            if "Re-fetch" not in user:
                # Arithmetic/grounding recovery: rerun the producer over all of
                # its original inputs. A replacement must restore the complete
                # result, not just the field that caused the failure.
                return json.dumps({"nodes": [{
                    "id": "recompute",
                    "skill": "coder",
                    "input": "Recompute every requested metric for every ticker.",
                    "depends_on": original_deps,
                }]})

            if not offenders:
                offenders = original_tickers[:1]

            nodes = [
                {"id": f"refetch_{ticker}", "skill": "retriever",
                 "input": f"Fetch one year of daily closes for {ticker}.",
                 "depends_on": []}
                for ticker in offenders
            ]
            replacements = {
                f"fetch_{ticker}": f"refetch_{ticker}" for ticker in offenders
            }
            complete_inputs = [replacements.get(dep, dep) for dep in original_deps]
            nodes.append({
                "id": "recompute",
                "skill": "coder",
                "input": "Recompute CAGR, annualised volatility, Sharpe ratio and "
                         "max drawdown for every ticker using the repaired inputs.",
                "depends_on": complete_inputs,
            })
            return json.dumps({"nodes": nodes})

        tickers = _tickers(user) or ["NVDA", "AMD", "INTC"]
        nodes = [
            {"id": f"fetch_{t}", "skill": "retriever",
             "input": f"Fetch one year of daily closes for {t}.",
             "depends_on": [], "critic": False}
            for t in tickers
        ]
        fan_in = [n["id"] for n in nodes]

        nodes.append({
            "id": "metrics",
            "skill": "coder",
            "input": "Compute CAGR, annualised volatility, Sharpe ratio and max "
                     "drawdown for each ticker over the retrieved window.",
            "depends_on": fan_in,
            "critic": True,
            "critic_property":
                "Every top-level ticker object in the producer output (excluding "
                "underscore-prefixed metadata) has an integer points value of at "
                "least 200 and a numeric cagr_pct value.",
        })

        if "chart" in user.lower() or "plot" in user.lower():
            nodes.append({
                "id": "chart", "skill": "charter",
                "input": "Plot the rebased price series for all tickers.",
                "depends_on": fan_in,
            })

        answer_inputs = ["metrics"]
        if any(n["id"] == "chart" for n in nodes):
            answer_inputs.append("chart")
        nodes.append({
            "id": "answer", "skill": "formatter",
            "input": "Write the comparison for the user.",
            "depends_on": answer_inputs,
        })
        return json.dumps({"nodes": nodes})

    # ---------- critic ----------

    def _critic(self, user: str) -> str:
        raw = user.split("PRODUCER OUTPUT:\n", 1)[-1].strip()
        try:
            output = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return json.dumps({
                "verdict": "fail",
                "reason": "malformed producer output: expected one JSON object",
            })

        tickers = {
            key: value for key, value in output.items()
            if not key.startswith("_")
        } if isinstance(output, dict) else {}
        if not tickers:
            return json.dumps({
                "verdict": "fail",
                "reason": "missing data: producer output contains no ticker objects",
            })

        for ticker, metrics in tickers.items():
            if not isinstance(metrics, dict):
                return json.dumps({
                    "verdict": "fail",
                    "reason": f"malformed output: {ticker} is not a metric object",
                })
            points = metrics.get("points")
            if not isinstance(points, int) or isinstance(points, bool):
                return json.dumps({
                    "verdict": "fail",
                    "reason": f"missing data: {ticker} has no integer points value",
                })
            if points < 200:
                return json.dumps({
                    "verdict": "fail",
                    "reason": f"{ticker} has fewer than 200 close prices ({points})",
                })
            cagr = metrics.get("cagr_pct")
            if not isinstance(cagr, (int, float)) or isinstance(cagr, bool):
                return json.dumps({
                    "verdict": "fail",
                    "reason": f"miscalculated output: {ticker} cagr_pct is not numeric",
                })
        return json.dumps({"verdict": "pass", "reason": ""})

    # ---------- formatter ----------

    def _format(self, user: str) -> str:
        marker = "UPSTREAM NODE OUTPUTS (JSON keys are node ids):"
        if marker not in user:
            return "[mock formatter] No upstream outputs were supplied."
        try:
            context = json.loads(user.split(marker, 1)[1].strip())
        except json.JSONDecodeError:
            return "[mock formatter] Upstream outputs were not valid JSON."

        decoded = {}
        for node_id, raw in context.items():
            try:
                decoded[node_id] = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                decoded[node_id] = raw

        metrics = next(
            (value for value in decoded.values()
             if isinstance(value, dict) and "_conventions" in value),
            None,
        )
        chart = next(
            (value for value in decoded.values()
             if isinstance(value, dict) and "chart" in value),
            None,
        )
        if metrics is None:
            return "[mock formatter] Computed metrics were not available."

        rows = []
        for ticker, values in sorted(metrics.items()):
            if ticker.startswith("_") or not isinstance(values, dict):
                continue
            rows.append(
                f"| {ticker} | {values.get('points')} | {values.get('cagr_pct')} | "
                f"{values.get('vol_pct')} | {values.get('sharpe')} | "
                f"{values.get('max_drawdown_pct')} |"
            )
        lines = [
            "[mock formatter] Computed comparison",
            "",
            "| Ticker | Points | CAGR % | Volatility % | Sharpe | Max drawdown % |",
            "|---|---:|---:|---:|---:|---:|",
            *rows,
        ]
        sources = metrics.get("_sources", {})
        if sources:
            source_text = ", ".join(
                f"{ticker}: {source}" for ticker, source in sorted(sources.items())
            )
            lines.extend(["", f"Sources: {source_text}"])
        if chart:
            lines.extend(["", f"Chart artifact: {chart['chart']}"])
        return "\n".join(lines)


def _tickers(text: str) -> list[str]:
    found = re.findall(r"\b[A-Z]{2,5}\b", text)
    stop = {"USER", "QUERY", "TASK", "JSON", "CAGR", "NODE", "AND", "THE",
            "RECOVERY", "SUBGRAPH", "OUTPUTS", "UPSTREAM", "PROPERTY"}
    out = []
    for t in found:
        if t not in stop and t not in out:
            out.append(t)
    return out[:5]


_CODER_SCRIPT = '''```python
import json, math, sys

with open(sys.argv[1]) as fh:
    upstream = json.load(fh)

series = {}
sources = {}
for raw in upstream.values():
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        continue
    if isinstance(payload, dict) and "closes" in payload:
        series[payload["ticker"]] = payload["closes"]
        sources[payload["ticker"]] = payload.get("source", "unknown")

if not series:
    print(json.dumps({"error": "no price series found in upstream outputs"}))
    sys.exit(1)

TRADING_DAYS = 252
results = {
    "_conventions": {"trading_days_per_year": TRADING_DAYS, "risk_free_rate": 0.0},
    "_sources": sources,
}

for ticker, closes in series.items():
    n = len(closes)
    if n < 2 or closes[0] <= 0:
        results[ticker] = {"error": "only %d usable points" % n}
        continue

    years = (n - 1) / TRADING_DAYS
    cagr = (closes[-1] / closes[0]) ** (1 / years) - 1

    rets = [closes[i] / closes[i - 1] - 1 for i in range(1, n)]
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1) if len(rets) > 1 else 0.0
    vol = math.sqrt(var) * math.sqrt(TRADING_DAYS)

    peak, mdd = closes[0], 0.0
    for c in closes:
        peak = max(peak, c)
        mdd = min(mdd, c / peak - 1)

    results[ticker] = {
        "points": n,
        "cagr_pct": round(cagr * 100, 2),
        "vol_pct": round(vol * 100, 2),
        "sharpe": round(cagr / vol, 2) if vol > 0 else None,
        "max_drawdown_pct": round(mdd * 100, 2),
    }

print(json.dumps(results, indent=2))
```'''


_CHARTER_SCRIPT = '''```python
import json, os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

with open(sys.argv[1]) as fh:
    upstream = json.load(fh)
artifacts = sys.argv[2]

series = {}
for raw in upstream.values():
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        continue
    if isinstance(payload, dict) and "closes" in payload:
        series[payload["ticker"]] = payload["closes"]

if not series:
    print(json.dumps({"error": "no plottable series in upstream outputs"}))
    sys.exit(1)

fig, ax = plt.subplots(figsize=(10, 6), dpi=150)
for ticker in sorted(series):
    closes = series[ticker]
    base = closes[0]
    ax.plot([c / base * 100 for c in closes], label=ticker, alpha=0.85)

ax.set_title("Relative price performance")
ax.set_xlabel("Trading days")
ax.set_ylabel("Price, rebased to 100 at period start")
ax.legend()
ax.grid(alpha=0.3)
plt.tight_layout()

path = os.path.join(artifacts, "comparison.png")
plt.savefig(path)
plt.close()

print(json.dumps({"chart": path, "series": sorted(series),
                  "points": len(next(iter(series.values())))}))
```'''

"""Real Chromium + course runtime, fictional shops + scripted cognition. No keys.

    uv run python dry_run_shoes.py

This is integration evidence only, never live shopping/submission evidence.
"""
from __future__ import annotations

import argparse
import asyncio
from contextlib import ExitStack, redirect_stdout
from decimal import Decimal, InvalidOperation
import io
import json
from pathlib import Path
import re
from unittest.mock import AsyncMock, patch
import uuid

import yaml

ROOT = Path(__file__).resolve().parent
EXAMPLES = ROOT / "examples"
COLUMNS = ["model", "retailer", "price", "size", "stock", "delivery", "intended use", "source_url"]


def load_profile() -> dict:
    return yaml.safe_load((EXAMPLES / "beginner_runner.yaml").read_text())


def evaluate(product: dict, profile: dict) -> tuple[str, str]:
    """Conservative fixture eligibility; unknown facts never become matches."""
    required = ("price", "currency", "size", "size_system", "category", "in_stock", "delivery", "surface")
    if any(product.get(key) is None for key in required):
        return "unverified", "missing price, variant, stock, delivery or surface evidence"
    for key, expected in (("size", profile["size"]["value"]),
                          ("size_system", profile["size"]["system"]),
                          ("category", profile["category"]),
                          ("surface", profile["intended_surface"])):
        if product[key] != expected:
            return "excluded", f"{key} does not meet the confirmed condition"
    if product["in_stock"] is not True or product["delivery"] is not True:
        return "excluded", "out of stock or delivery unavailable"
    if product["currency"] != profile["budget"]["currency"]:
        return "unverified", "currency conversion requires a dated rate and source"
    try:
        price = Decimal(str(product["price"]))
        budget = Decimal(str(profile["budget"]["amount"]))
        if not price.is_finite() or price < 0:
            return "unverified", "invalid displayed price"
        if price > budget:
            return "excluded", "displayed item price exceeds budget"
    except InvalidOperation:
        return "unverified", "invalid displayed price"
    return "eligible", "confirmed fixture constraints met; fit is not established"


def _inputs(prompt: str) -> list[dict]:
    return json.loads(prompt.split("\nINPUTS:\n", 1)[1])


def _products(inputs: list[dict]) -> list[dict]:
    observed = {}
    for item in inputs:
        content = item.get("output", {}).get("content", "") or ""
        for line in content.splitlines():
            if line.startswith("OBSERVED_PRODUCT "):
                row = json.loads(line.removeprefix("OBSERVED_PRODUCT "))
                observed[row["source_url"]] = row
    return list(observed.values())


def _comparison(inputs: list[dict], profile: dict) -> dict:
    rows, excluded = [], []
    for p in _products(inputs):
        status, reason = evaluate(p, profile)
        if status != "eligible":
            excluded.append({"model": p["model"], "status": status, "reason": reason})
            continue
        rows.append({"model": p["model"], "retailer": p["retailer"],
                     "price": f'{p["currency"]} {p["price"]:.2f}',
                     "size": f'{p["size_system"]} {p["size"]}',
                     "stock": "in stock (fixture)", "delivery": "available (fixture)",
                     "intended use": "road (fixture claim; treadmill fit untested)",
                     "source_url": p["source_url"]})
    shortfall = max(0, profile["requested_count"] - len(rows))
    return {"columns": COLUMNS, "rows": rows, "excluded": excluded,
            "rationale": f"DRY RUN — FICTIONAL data. Shortfall: {shortfall}. "
                         "Budget checks displayed item prices; delivery fees and personal fit are not verified."}


def _table(output: dict) -> str:
    columns = output["columns"]
    def escape(value):
        return str(value).replace("|", "\\|").replace("\n", " ")
    lines = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    lines.extend("| " + " | ".join(escape(row[c]) for c in columns) + " |"
                 for row in output["rows"])
    exclusions = "; ".join(f'{p["model"]}: {p["reason"]}' for p in output["excluded"])
    return "\n".join(lines) + "\n\n" + output["rationale"] + "\n\nExcluded: " + exclusions


class ScriptedBrowserClient:
    """Scripted decisions based on actual DOM observations; never calls an API."""
    def __init__(self, profile):
        self.profile = profile

    async def chat(self, prompt, **kwargs):
        from browser.client import GatewayResult
        elements = dict((name, int(mark)) for mark, name in re.findall(
            r'^\[(\d+)\]<[^>]+>(.*?)</[^>]+>$', prompt, re.M))
        if "FILTER: men / road" not in prompt:
            label = "Filter men's road shoes"
        elif "SIZE: UK 11" not in prompt:
            label = "Select UK 11"
        elif "DETAIL: none" in prompt:
            label = next(name for name in elements if name.startswith("Open "))
        elif "DELIVERY: unchecked" in prompt:
            if "POSTCODE: empty" in prompt:
                action = {"type": "type", "mark": elements["Delivery postcode"],
                          "value": self.profile["delivery"]["postcode"]}
                return GatewayResult({"actions": [action]}, "", "scripted", "dry-run", 0, 0, 0)
            label = "Check delivery"
        elif "Next product" in elements:
            label = "Next product"
        else:
            return GatewayResult({"actions": [{"type": "done", "success": True}]},
                                 "", "scripted", "dry-run", 0, 0, 0)
        return GatewayResult({"actions": [{"type": "click", "mark": elements[label]}]},
                             "", "scripted", "dry-run", 0, 0, 0)

    async def vision(self, *args, **kwargs):
        raise RuntimeError("Dry run unexpectedly escalated beyond the scripted a11y path")


class ScriptedLLM:
    def __init__(self, profile, shops):
        self.profile, self.shops = profile, shops

    def chat(self, *, agent, prompt, **kwargs):
        if agent == "planner":
            if "\nFAILURE:\n" in prompt:
                return {"text": json.dumps({"nodes": [{"skill": "formatter",
                        "inputs": ["USER_QUERY"], "metadata": {"label": "failure"}}]}),
                        "provider": "scripted"}
            nodes = []
            for i, shop in enumerate(self.shops):
                nodes.append({"skill": "browser", "inputs": [] if i == 0 else [f"n:shop{i-1}"],
                              "metadata": {"label": f"shop{i}", "url": shop.as_uri(),
                                           "goal": "Filter men's road shoes, select UK 11, open both products and check delivery using the configured postcode."}})
            nodes.extend([
                {"skill": "distiller", "inputs": [f"n:shop{i}" for i in range(len(self.shops))],
                 "metadata": {"label": "table"}},
                {"skill": "formatter", "inputs": ["USER_QUERY", "n:table"], "metadata": {"label": "answer"}},
            ])
            output = {"nodes": nodes, "rationale": "DRY RUN: scripted plan on local fictional shops."}
        elif agent == "distiller":
            output = _comparison(_inputs(prompt), self.profile)
        elif agent == "critic":
            inputs = _inputs(prompt)
            proposed = next(i["output"] for i in inputs if i.get("skill") == "distiller")
            expected = _comparison(inputs, self.profile)
            passed = bool(expected["rows"]) and proposed == expected
            output = {"verdict": "pass" if passed else "fail",
                      "rationale": "Scripted comparison against the original browser evidence."}
        elif agent == "formatter":
            table = next((i["output"] for i in _inputs(prompt) if i.get("skill") == "distiller"), None)
            output = {"final_answer": _table(table) if table else
                      "DRY RUN FAILED: a source step did not complete; no comparison is verified."}
        else:
            raise RuntimeError(f"Unexpected dry-run skill {agent}")
        return {"text": json.dumps(output), "provider": "scripted"}


async def run_dry_run(sessions_root: Path | None = None, *, session_id: str | None = None) -> dict:
    import flow
    import persistence
    import report
    from browser.skill import BrowserSkill

    profile = load_profile()
    root = (sessions_root or persistence.SESSIONS_ROOT).resolve()
    sid = session_id or f"s9-shoes-dry-{uuid.uuid4().hex[:8]}"
    session = root / sid
    if session.exists():
        raise FileExistsError(f"Refusing to overwrite existing session: {session}")
    shops_dir = session / "shops"
    shops_dir.mkdir(parents=True)
    fixture = yaml.safe_load((EXAMPLES / "shoes_dry_run.yaml").read_text())["products"]
    template = (EXAMPLES / "shoe_shop.html").read_text()
    shops = []
    for retailer in dict.fromkeys(p["retailer"] for p in fixture):
        shop = shops_dir / f"shop-{len(shops)+1}.html"
        products = [p for p in fixture if p["retailer"] == retailer]
        shop.write_text(template.replace("__PRODUCTS__", json.dumps(products))
                        .replace("__PROFILE__", json.dumps(profile)))
        shops.append(shop)

    def browser_factory(**kwargs):
        kwargs["artifacts_root"] = str(session / "browser")
        return BrowserSkill(**kwargs)

    query = ("DRY RUN — FICTIONAL PRODUCTS / SCRIPTED MODEL RESPONSES. Compare three "
             "men's UK 11 shoes within USD 200 for a beginner who runs on a treadmill "
             "and wants to run on roads; delivery to Mumbai using the configured postcode. "
             "No external model calls, no real stock/price claims, no medical fit claims.")
    # All replacement clients are scoped to this harness. flow.py is unchanged.
    with ExitStack() as stack:
        for target, value in [
            ("flow.ensure_gateway", lambda: None),
            ("flow.memory_svc.read", lambda *a, **k: []),
            ("flow.memory_svc.remember", lambda *a, **k: None),
            ("persistence.SESSIONS_ROOT", root), ("report.SESSIONS_ROOT", root),
            ("skills.LLM", lambda: ScriptedLLM(profile, shops)),
            ("browser.skill.BrowserSkill", browser_factory),
            ("browser.skill.V9Client", lambda **kw: ScriptedBrowserClient(profile)),
            ("browser.skill._fetch_html", AsyncMock(return_value=("", ""))),
            ("report.fetch_cost", lambda *a, **k: ({"dry_run": [{"provider": "scripted", "calls": 0, "dollars": 0}]}, None)),
        ]:
            stack.enter_context(patch(target, value))
        # The course executor prints full queries. Keep personal details out of stdout.
        with redirect_stdout(io.StringIO()):
            answer = await flow.Executor().run(query, session_id=sid)
        states = persistence.SessionStore(sid).read_all_nodes()
        failures = [s for s in states if s.status == "failed"]
        if failures:
            report_path = session / "shoes_report.html"
            report_path.write_text(report.build_report(sid, use_gateway=False))
            first = failures[0]
            raise RuntimeError(f"Dry run failed at {first.node_id} ({first.skill}): "
                               f"{(first.result.error or '')[:160]}. Report: {report_path}")
        table = next(s.result.output for s in states if s.skill == "distiller")
        critic = next(s.result.output["verdict"] for s in states if s.skill == "critic")
        actions = [a for s in states if s.skill == "browser" for turn in s.result.output["actions"]
                   for a in turn["actions"] if a["type"] not in ("done", "wait")]
        report_path = session / "shoes_report.html"
        report_path.write_text(report.build_report(sid, use_gateway=False))
        (session / "comparison.md").write_text(answer)
        summary = {"session": sid, "mode": "DRY RUN — FICTIONAL PRODUCTS", **table,
                   "interactive_actions": len(actions), "paid_calls": 0,
                   "all_nodes_complete": all(s.status == "complete" for s in states),
                   "critic_verdict": critic, "report": str(report_path)}
        (session / "dry_run_summary.json").write_text(json.dumps(summary, indent=2))
    if not summary["all_nodes_complete"] or critic != "pass" or len(actions) < 3:
        raise RuntimeError("Dry-run integration checks failed; inspect the saved session")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, help="session output directory")
    args = parser.parse_args()
    result = asyncio.run(run_dry_run(args.output_root))
    print(f'{result["mode"]}\nSession: {result["session"]}\n'
          f'Qualifying: {len(result["rows"])}; excluded: {len(result["excluded"])}; '
          f'interactive actions: {result["interactive_actions"]}; model API calls: 0\n'
          f'Critic: {result["critic_verdict"]}\nReport: {result["report"]}')


if __name__ == "__main__":
    main()

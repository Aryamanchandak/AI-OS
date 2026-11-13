"""Evaluate the actual research service; offline smoke checks never claim answer quality."""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from s15code.core.live_graph import GraphStore  # noqa: E402
from s15code.economics import EconomicsConfig  # noqa: E402
from s15code.evals import EvalsConfig, RubricJudge, load_tasks  # noqa: E402
from s15code.gateway import GatewayClient  # noqa: E402
from s15code.research.evaluation import compare  # noqa: E402
from s15code.research.models import Document, ResearchRequest  # noqa: E402
from s15code.research.service import ResearchAssistant  # noqa: E402


class CapturedTransport:
    def __init__(self, gateway, offline):
        self.gateway, self.offline, self.last_request = gateway, offline, None

    async def chat(self, *, prompt, system, request=None):
        self.last_request = {"prompt": prompt, "system": system, "request": request}
        if not self.offline:
            return await self.gateway.chat(prompt=prompt, system=system, request=request)
        source = json.loads(prompt)["evidence"][0]
        quote = source["text"].strip()[:120]
        claim = {"text": "Offline fixture quotes a source; this is not a researched conclusion.",
                 "citations": [{"evidence_id": source["id"], "quote": quote}]}
        text = json.dumps({"title": "Offline contract check", "conclusions": [claim], "alternatives": [claim],
                           "uncertainties": ["No model was called. Answer quality and savings are unmeasured."]})
        return {"text": text, "provider": "simulated", "model": request["model"],
                "input_tokens": len(prompt) // 4, "output_tokens": len(text) // 4}


async def run(args):
    config = EconomicsConfig.load()
    gateway = GatewayClient(args.base_url)
    store = None
    try:
        if not args.offline:
            await gateway.health()  # No implicit offline fallback or paid calls before this succeeds.
        tasks = load_tasks(args.tasks)
        if len(tasks) < 15:
            raise ValueError("the workload needs at least 15 source-based research tasks")
        documents = [Document(name=p.name, text=p.read_text(encoding="utf-8")) for p in
                     [ROOT.parent / "Assignment.md", ROOT / "README.md", ROOT.parent / "Lecture.md"]]
        args.output.mkdir(parents=True, exist_ok=True)
        # Separate database per invocation: prior experiments never alter this report.
        import uuid
        store = GraphStore(args.output / f"research-{uuid.uuid4().hex}.sqlite")
        assistant = ResearchAssistant(store, config)
        transport = CapturedTransport(gateway, args.offline)
        judge = RubricJudge(gateway, EvalsConfig.load().rubric, pricing=config.pricing)
        rows, captures = [], []
        for task in tasks:
            for strategy in ("routed", "frontier"):
                result = await assistant.research(ResearchRequest(question=task.task, documents=documents,
                    budget=args.budget, strategy=strategy), transport)
                charges = result["budget"]["charges"]
                model = charges[-1] if charges else {}
                verdict = None if args.offline else await judge.judge(task=task.task, task_id=task.id,
                    answer=json.dumps(result["output"]) if result["output"] else None,
                    expectation=task.expectation,
                    answer_provider=model.get("provider"), answer_model=model.get("model"), error=result["error"])
                row = {"task_id": task.id, "strategy": strategy, "question": task.task,
                       "expectation": task.expectation, "run_id": result["run_id"],
                       "spent": result["budget"]["spent"], "calls": len(charges),
                       "resolved": verdict.resolved if verdict else None, "status": result["status"],
                       "baseline_valid": strategy != "frontier" or (bool(charges) and all(
                           c["tier"] == config.ladder.most_capable.name for c in charges)),
                       "quality": verdict.overall if verdict else None,
                       "judge_cost": verdict.judge_cost if verdict else 0,
                       "self_judged": verdict.self_judged if verdict else False,
                       "verdict": verdict.as_dict() if verdict else None}
                rows.append(row)
                if len(captures) < 4:
                    captures.append({"question": task.task, "strategy": strategy,
                                     "exact_model_request": transport.last_request, "result": result})
                report = {"simulated": args.offline, "workload": str(args.tasks), "config": config.describe(),
                          "summary": compare(rows), "rows": rows, "four_captured_runs": captures,
                          "complete": len(rows) == 2 * len(tasks),
                          "limitations": ["Quote matching checks provenance, not whether a claim follows from a quote.",
                                           "Lexical retrieval can omit relevant passages.",
                                           "Judge spend is reported separately and is not inside each answer budget.",
                                           "Offline costs are simulated; quality, savings and bad routing are unmeasured."]}
                (args.output / "research-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
                print(f"{task.id} {strategy}: {result['status']}; resolved={row['resolved']}; cost={row['spent']:.6f}",
                      flush=True)
        print(json.dumps(report["summary"], indent=2))
        if args.offline:
            return 0 if all(r["status"] == "completed" for r in rows) else 1
        summaries = report["summary"]["strategies"]
        return 0 if all(s["valid_quality"] for s in summaries.values()) and summaries["frontier"]["resolved"] else 1
    finally:
        if store is not None:
            store.close()
        await gateway.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--tasks", type=Path, default=ROOT / "proofs/tasks/research.yaml")
    parser.add_argument("--budget", type=float, default=0.10, help="answer budget per task and strategy; judge cost extra")
    parser.add_argument("--output", type=Path, default=ROOT / "proofs/out/research")
    parser.add_argument("--offline", action="store_true", help="contract smoke check; no judge or quality claims")
    args = parser.parse_args()
    try:
        return asyncio.run(run(args))
    except (RuntimeError, ValueError, OSError, httpx.HTTPError) as exc:
        print(f"Research evaluation could not complete: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

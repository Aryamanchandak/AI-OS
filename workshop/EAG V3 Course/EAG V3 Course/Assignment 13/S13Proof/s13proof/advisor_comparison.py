"""Compare one shared worker draft with and without a bounded advisor consultation."""
from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import json
import os
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

from dotenv import load_dotenv

from s13code.advisor import ResearchAdvisor, Review
from s13code.core.live_graph import GraphStore
from s13code.core.memory import MemoryScope, MemoryStore
from s13code.core.memory.chunking import prepare_markdown, semantic_chunks
from s13code.core.memory.embeddings import DeterministicEmbedder
from s13code.gateway import GatewayClient
from s13proof.advisor_evaluation import COURSE

SCOPE = MemoryScope("synthetic-comparison", "papers", "student")
USAGE = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens", "latency_ms")


def load_config(env_file):
    load_dotenv(env_file)
    default = os.getenv("S13_GATEWAY_PROVIDER")
    return {"base_url": os.getenv("GLC_BASE_URL", "http://127.0.0.1:8111"),
            "worker_provider": os.getenv("S13_COMPARISON_WORKER_PROVIDER") or default,
            "advisor_provider": os.getenv("S13_COMPARISON_ADVISOR_PROVIDER") or default}


def metrics(calls, elapsed):
    totals = {field: sum(call[field] for call in calls) if calls and
              all(isinstance(call.get(field), (int, float)) for call in calls) else None for field in USAGE}
    return {**totals, "model_calls": len(calls), "elapsed_seconds": round(elapsed, 6), "cost": None,
            "cost_note": "Gateway chat responses do not supply priced cost; missing values are not zero.",
            "usage_note": "Counts logical calls and reported usage; internal gateway attempts may cost extra."}


async def compare(cases, call, *, mode, run_id=None):
    run_id = run_id or "comparison-" + uuid4().hex[:12]
    if not cases or len({case["id"] for case in cases}) != len(cases):
        raise ValueError("comparison requires nonempty cases with unique IDs")
    rows, hashes = [], {}
    worker_system = (COURSE / "advisor_worker.md").read_text()
    with TemporaryDirectory(prefix="s13-comparison-") as temporary:
        memory = MemoryStore(Path(temporary) / "memory.sqlite", embedder=DeterministicEmbedder(256))
        graph = GraphStore(Path(temporary) / "graph.sqlite")
        advisor = ResearchAdvisor(memory, graph)
        prepared_sources = {}
        try:
            for source in [*sorted((COURSE / "papers").glob("*.txt")), COURSE / "advisor_hostile.md"]:
                raw = source.read_text()
                hashes[source.name] = hashlib.sha256(raw.encode()).hexdigest()
                prepared, preprocessing = prepare_markdown(raw)
                prepared_sources[source.name] = prepared
                memory.ingest_document(source_text=raw, prepared_text=prepared,
                    chunks=semantic_chunks(prepared, memory.embedder, preprocess=False),
                    source_uri=f"fixture://papers/{source.name}", scope=SCOPE,
                    source_author="synthetic-indexer", preprocessing=preprocessing)
            for case in cases:
                if (case["expected_verdict"] not in {"supported", "contradicted", "unclear"} or
                        case["quote"] not in prepared_sources.get(case["source"], "")):
                    raise ValueError("reference label is invalid or its quote is absent from its source")
            for case in cases:
                calls = []
                started = time.perf_counter()

                async def ask(role, prompt, system):
                    before = time.perf_counter()
                    entry = {"role": role, "provider": None, "model": None,
                             **dict.fromkeys(USAGE), "error": None}
                    try:
                        response = await call(role, case["id"], prompt, system)
                        entry.update({field: response.get(field) for field in (*USAGE, "provider", "model")})
                        return response
                    except Exception:
                        entry["error"] = "Provider call failed."
                        raise RuntimeError("Provider call failed.") from None
                    finally:
                        entry["elapsed_seconds"] = round(time.perf_counter() - before, 6)
                        calls.append(entry)

                baseline = None
                consultation = None
                final = None
                initial_cards = advisor._retrieve([case["question"]], SCOPE)
                payload = {"stage": "worker", "question": case["question"], "claims": [case["claim"]],
                           "evidence": initial_cards, "response_schema": Review.model_json_schema()}
                try:
                    response = await ask("worker", json.dumps(payload), worker_system)
                    baseline = advisor._validate(Review.model_validate_json(response["text"]),
                                                 [case["claim"]], initial_cards, SCOPE)
                    baseline_error = None
                except Exception:
                    baseline_error = "Worker response could not be validated or provider call failed."
                baseline_calls = list(calls)
                baseline_elapsed = time.perf_counter() - started
                final_error = "No valid initial draft was available." if baseline_error else None
                if baseline is not None:
                    try:
                        consultation = await advisor.consult(question=case["question"], draft=json.dumps(baseline),
                            claims=[case["claim"]], scope=SCOPE,
                            llm=lambda prompt, system: ask("advisor", prompt, system))
                        if consultation["status"] != "completed":
                            raise ValueError("advisor failed")
                        if (consultation["recommendation"] == "accept" and baseline["assessments"][0]["verdict"] ==
                                consultation["assessments"][0]["verdict"]):
                            final = baseline
                        else:
                            cards = {card["record_id"]: card for card in initial_cards}
                            for node in consultation["graph"]["nodes"].values():
                                for card in (node.get("result") or {}).get("evidence", []):
                                    cards[card["record_id"]] = card
                            revision = {**payload, "stage": "revision", "initial_draft": baseline,
                                "advice": {key: consultation[key] for key in ("recommendation", "summary", "assessments")},
                                "evidence": list(cards.values())}
                            response = await ask("revision", json.dumps(revision), worker_system)
                            final = advisor._validate(Review.model_validate_json(response["text"]),
                                                      [case["claim"]], revision["evidence"], SCOPE)
                        final_error = None
                    except Exception:
                        final_error = "Advised response could not be validated or consultation failed."
                rows.append({"id": case["id"], "question": case["question"], "claim": case["claim"],
                    "reference": {key: case[key] for key in ("expected_verdict", "source", "quote")},
                    "without_advice": {"status": "failed" if baseline_error else "completed", "result": baseline,
                        "error": baseline_error, "metrics": metrics(baseline_calls, baseline_elapsed)},
                    "with_advice": {"status": "failed" if final_error else "completed", "result": final,
                        "initial_draft": baseline, "consultation": consultation, "error": final_error,
                        "metrics": metrics(calls, time.perf_counter() - started)}, "calls": calls})
        finally:
            memory.close()
            graph.close()
    summary = {"requested_cases": len(rows), "completed_pairs": 0, "label_corrections": 0,
               "label_regressions": 0, "label_matches_preserved": 0,
               "without_advice_label_matches": 0, "with_advice_label_matches": 0}
    for row in rows:
        matched = {}
        for arm in ("without_advice", "with_advice"):
            result = row[arm]["result"]
            matched[arm] = bool(result and result["assessments"][0]["verdict"] == row["reference"]["expected_verdict"])
            summary[arm + "_label_matches"] += int(matched[arm])
        if all(row[arm]["status"] == "completed" for arm in matched):
            summary["completed_pairs"] += 1
            before, after = matched.values()
            summary["label_corrections"] += int(not before and after)
            summary["label_regressions"] += int(before and not after)
            summary["label_matches_preserved"] += int(before and after)
    return {"run_id": run_id, "mode": mode, "status": "completed" if summary["completed_pairs"] == len(rows) else "incomplete",
            "case_labels": "draft-needs-human-review", "judgment_quality_verified": False,
            "retrieval": "fixed heading segmentation and deterministic embeddings in both arms",
            "corpus_sha256": hashes, "worker_prompt_sha256": hashlib.sha256(worker_system.encode()).hexdigest(),
            "cases_sha256": hashlib.sha256(json.dumps(cases, sort_keys=True).encode()).hexdigest(),
            "summary": summary, "cases": rows,
            "limitation": "Label agreement is not prose accuracy. Human reviewers must assess unsupported claims, "
                          "preservation, and citations. Live models still use fixed offline retrieval here. "
                          "The advisor arm may consume more evidence and calls; this is not an equal-compute comparison."}


def write_review_sheet(report, path):
    fields = ["run_id", "case_id", "arm", "question", "claim", "expected_verdict", "actual_verdict", "answer", "citations",
              "unsupported_claim_count", "correct_claims_preserved", "citations_accurate", "reviewer_notes"]
    with path.open("w", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        for case in report["cases"]:
            for arm in ("without_advice", "with_advice"):
                result = case[arm]["result"] or {}
                assessment = (result.get("assessments") or [{}])[0]
                row = {"run_id": report["run_id"], "case_id": case["id"], "arm": arm, "question": case["question"],
                    "claim": case["claim"], "expected_verdict": case["reference"]["expected_verdict"],
                    "actual_verdict": assessment.get("verdict", ""), "answer": result.get("summary", ""),
                    "citations": json.dumps(assessment.get("citations", []))}
                # Model/source text must remain text when the CSV is opened in a spreadsheet.
                writer.writerow({key: "'" + value if str(value).lstrip().startswith(("=", "+", "-", "@")) else value
                                 for key, value in row.items()})


def scripted_call(cases):
    labels = {case["id"]: case for case in cases}

    async def respond(role, case_id, prompt, _system):
        case, payload = labels[case_id], json.loads(prompt)
        card = next((card for card in payload["evidence"] if case["quote"] in card["text"]), payload["evidence"][0])
        quote = case["quote"] if case["quote"] in card["text"] else card["text"][:80]
        verdict = "supported" if role == "worker" else case["expected_verdict"]
        followup = case["question"] if role == "advisor" and verdict == "unclear" and payload["round"] == 1 else None
        review = {"summary": f"Scripted fixture assessment: {verdict}.", "followup_query": followup,
            "assessments": [{"claim": case["claim"], "verdict": verdict, "reason": "Scripted fixture judgment.",
                "citations": [{"record_id": card["record_id"], "quote": quote}]}]}
        return {"text": json.dumps(review), "provider": f"scripted-{role}", "model": "fixture-v1",
                "input_tokens": 100, "output_tokens": 50, "latency_ms": 0}
    return respond


async def run(*, mode="dry-run", config=None):
    with (COURSE / "advisor_judgment_cases.csv").open() as file:
        cases = list(csv.DictReader(file))
    if mode == "dry-run":
        return await compare(cases, scripted_call(cases), mode=mode)
    if mode != "live":
        raise ValueError("mode must be dry-run or live")
    config = config or load_config(COURSE.parent / ".env")
    gateway = GatewayClient(config["base_url"])
    run_id = "comparison-" + uuid4().hex[:12]
    try:
        await gateway.health()

        async def live_call(role, case_id, prompt, system):
            provider = config["advisor_provider" if role == "advisor" else "worker_provider"]
            return await gateway.complete(prompt, system, provider=provider, session=f"{run_id}:{case_id}")
        return await compare(cases, live_call, mode=mode, run_id=run_id)
    finally:
        await gateway.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("dry-run", "live"), default="dry-run")
    parser.add_argument("--env-file", type=Path, default=COURSE.parent / ".env")
    parser.add_argument("--output", type=Path, default=Path("advisor-comparison.json"))
    args = parser.parse_args()
    config = load_config(args.env_file)
    try:
        report = asyncio.run(run(mode=args.mode, config=config))
    except Exception:
        parser.exit(1, "Comparison could not start; check the gateway configuration and fixture files.\n")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    write_review_sheet(report, args.output.with_suffix(".reviews.csv"))
    print(json.dumps({"mode": report["mode"], "status": report["status"], "summary": report["summary"],
                      "judgment_quality_verified": False, "output": str(args.output)}, indent=2))
    if report["status"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

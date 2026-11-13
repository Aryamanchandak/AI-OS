"""Replay a worker consultation through HTTP with explicitly scripted model replies."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import httpx

from s13code.core.memory import MemoryScope
from s13code.core.memory.embeddings import DeterministicEmbedder
from s13proof.advisor_evaluation import COURSE, evaluate

SCOPE = {"tenant_id": "synthetic-proof", "project_id": "research", "user_id": "student"}
CLAIMS = ["ReAct interleaves reasoning and actions.",
          "ReAct always outperforms chain-of-thought on every task."]
QUOTE = "generate both reasoning traces and task-specific actions in an interleaved manner"
def revise(consultation):
    """A scripted worker consumes advice; this does not simulate model reasoning."""
    if consultation["status"] != "completed":
        return "The worker cannot finalize this draft because its consultation failed."
    supported = [item["claim"] for item in consultation["assessments"] if item["verdict"] == "supported"]
    if consultation["recommendation"] == "accept":
        return " ".join(supported)
    return (" ".join(supported) + " The supplied abstracts do not establish universal superiority over "
            "chain-of-thought. [source: fixture://papers/react.txt]")


async def run():
    request = {**SCOPE, "question": "What do these abstracts establish about ReAct versus chain-of-thought?",
               "draft": " ".join(CLAIMS), "claims": CLAIMS}
    with TemporaryDirectory(prefix="s13-advisor-") as temporary, patch.dict("os.environ", {
        "S13_DATA_DIR": temporary, "S13_SANDBOX_ROOT": temporary, "S13_A2A_GRPC_ENABLED": "0",
        "S13_PLANNER_LLM": "0", "S13_LIVE_SEMANTIC_CHUNKING": "0",
    }):
        # Load configuration only after the isolated environment is in place.
        from s13code.main import app
        import s13code.routes as routes
        import s13code.runtime as runtime_module

        stale_attack = False

        async def gateway(_app, prompt, system):
            nonlocal stale_attack
            if "response_schema" in prompt:
                payload = json.loads(prompt)
                card = next(card for card in payload["evidence"] if QUOTE in card["text"])
                citations = [{"record_id": card["record_id"], "quote": QUOTE}]
                review = {"summary": "Keep the interleaving claim; remove universal superiority.",
                    "assessments": [
                        {"claim": CLAIMS[0], "verdict": "supported", "reason": "The abstract states interleaving.",
                         "citations": citations},
                        {"claim": CLAIMS[1], "verdict": "unclear", "reason": "Named evaluations do not establish every task.",
                         "citations": citations},
                    ], "followup_query": "ReAct chain-of-thought direct comparison evaluated tasks"}
                if stale_attack:
                    app.state.s13_runtime.index_document(
                        text="# Withdrawn\nThe earlier evaluation has been withdrawn.",
                        source_uri="fixture://papers/react.txt", scope=MemoryScope(**SCOPE),
                        source_author="synthetic-indexer")
                    stale_attack = False
                return {"text": json.dumps(review), "provider": "scripted-advisor", "model": "fixture-v1"}
            if "What is the synthetic budget?" in prompt:
                assert "Budget is ₹75,000." in prompt
                text = "The synthetic budget is ₹75,000. [source: fixture://budget]"
            elif "How does ReAct gather additional information" in prompt:
                assert "external sources" in prompt
                text = "ReAct uses actions to gather information from external sources. [source: fixture://papers/react.txt]"
            else:
                text = "The fixture sources recommend awaiting I/O and bounding concurrency."
            return {"text": text, "provider": "scripted-worker", "model": "fixture-v1"}

        async def search(query, max_results=3):
            return {"query": query, "hits": [{"title": f"Fixture {i}", "url": f"https://fixture.invalid/{i}",
                "snippet": "Await I/O and bound concurrency."} for i in range(max_results)]}

        async def fetch(url):
            return {"url": url, "status": 200, "text": "Await I/O and bound concurrency."}

        async def post(client, path, body):
            response = await client.post(path, json=body)
            response.raise_for_status()
            return response.json()

        with patch.object(routes, "gateway_text_llm", gateway), patch.object(runtime_module, "web_search", search), \
                patch.object(runtime_module, "fetch_url", fetch):
            async with app.router.lifespan_context(app):
                app.state.s13_runtime.memory.embedder = DeterministicEmbedder(256)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proof") as client:
                    indexed = []
                    for source in sorted((COURSE / "papers").glob("*.txt")):
                        indexed.append(await post(client, "/v1/agent/documents", {
                            **SCOPE, "text": source.read_text(), "source_uri": f"fixture://papers/{source.name}",
                            "source_author": "synthetic-indexer"}))
                    live = await post(client, "/v1/agent/runs", {**SCOPE,
                        "prompt": "Search for 'fixture asyncio advice', read the top 3 results, and summarize."})
                    await post(client, "/v1/agent/facts", {**SCOPE, "text": "Budget is ₹75,000.",
                                                        "source_uri": "fixture://budget"})
                    semantic = await post(client, "/v1/agent/runs", {**SCOPE,
                        "prompt": "Across the papers I have indexed, How does ReAct gather additional information?"})
            # A fresh service lifetime reads the same persisted state.
            async with app.router.lifespan_context(app):
                app.state.s13_runtime.memory.embedder = DeterministicEmbedder(256)
                async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proof") as client:
                    durable = await post(client, "/v1/agent/runs", {**SCOPE, "prompt": "What is the synthetic budget?"})
                    consultation = await post(client, "/v1/agent/advisor", request)
                    cross_scope = await post(client, "/v1/agent/advisor", {**request, "tenant_id": "synthetic-other"})
                    stale_attack = True
                    attack = await post(client, "/v1/agent/advisor", request)
        return {"mode": "scripted-models-real-http-and-stores", "request": request,
                "consultation": consultation, "worker_revision": revise(consultation),
                "worker_revision_mode": "scripted response to the consultation, not measured model improvement",
                "cross_scope": cross_scope, "stale_attack": attack, "indexed": indexed,
                "floor": {"live_expansion": live, "durable_memory": durable, "semantic_query": semantic},
                "retrieval_evaluation": evaluate(),
                "limitation": "Citation integrity is enforced in code; semantic support is a model judgment. "
                              "No live provider or Nomic/Phi-4 evaluation has been run."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("advisor-proof.json"))
    args = parser.parse_args()
    result = asyncio.run(run())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(json.dumps({"mode": result["mode"], "recommendation": result["consultation"]["recommendation"],
        "followups_used": result["consultation"]["followups_used"], "worker_revision": result["worker_revision"],
        "stale_attack": result["stale_attack"]["status"],
        "retrieval": {name: result["retrieval_evaluation"][name] for name in ("semantic", "fixed_40_words")},
        "output": str(args.output)}, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

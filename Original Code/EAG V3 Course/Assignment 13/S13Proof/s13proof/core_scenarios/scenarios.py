"""Actual-work acceptance replays.

Unit tests prove individual invariants.  These scenarios start from a user
prompt, run a small piece of work, and return the graph, evidence and final
answer a human can inspect.  Workers are deterministic on purpose: an LLM
changing its wording must never be able to turn a proof green.
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from s13code.core.live_graph import GraphPatch, GraphStore, LiveGraphExecutor, TaskSpec
from s13code.core.memory import MemoryKind, MemoryRecord, MemoryScope, MemoryStore, Principal, SourceRef
from s13code.core.memory.chunking import fixed_word_chunks, semantic_chunks
from s13code.core.memory.embeddings import DeterministicEmbedder


USER = Principal("procurement-agent", "agent")
GATEWAY = Principal("glc-gateway", "gateway")
SCOPE = MemoryScope("acme", "travel", "rohan")


async def live_procurement_prompt() -> dict[str, Any]:
    """A conditional task must not exist until a market result requires it."""
    prompt = "Find a laptop under ₹75,000 and recommend one. Check legal terms only if the best option needs it."
    with TemporaryDirectory() as tmp:
        store = GraphStore(Path(tmp) / "live-graph.db")

        class Planner:
            async def plan(self, graph, event):
                if event.kind == "run_started":
                    # The legal task is deliberately absent from the first wave.
                    return GraphPatch(add=(
                        TaskSpec("budget", "read_budget"),
                        TaskSpec("market", "scan_market"),
                    ), reason="first useful frontier")
                if event.node_id == "market":
                    return GraphPatch(add=(TaskSpec("legal", "review_terms"),),
                                      connect=(("market", "legal"),),
                                      reason="best option has a vendor contract")
                if event.node_id == "legal":
                    return GraphPatch(finish=True, reason="recommendation is now safe to make")
                return GraphPatch()

        async def read_budget(_: TaskSpec):
            return {"budget_inr": 75000, "source": "user preference"}

        async def scan_market(_: TaskSpec):
            return {"best_option": "Framework 13", "price_inr": 72000,
                    "requires_legal_review": True}

        async def review_terms(_: TaskSpec):
            return {"vendor": "Framework", "verdict": "approved", "condition": "standard return policy"}

        report = await LiveGraphExecutor(
            store, Planner(),
            {"read_budget": read_budget, "scan_market": scan_market, "review_terms": review_terms},
            max_workers=2,
        ).run("procurement")
        events = store.events("procurement")
        first_patch = next(e for e in events if e.kind == "graph_patched")
        legal_patch = [e for e in events if e.kind == "graph_patched"][2]
        return {
            "prompt": prompt,
            "first_frontier": first_patch.payload["add"],
            "conditional_expansion": legal_patch.payload["add"],
            "executed": list(report.executed),
            "final_answer": "Recommend Framework 13 at ₹72,000; legal review approved its standard return policy.",
        }


def memory_correction_prompt() -> dict[str, Any]:
    """Show that a later user correction wins, with provenance."""
    store = MemoryStore(embedder=DeterministicEmbedder(256))
    try:
        first_prompt = "My laptop budget for this project is ₹50,000."
        first = store.write(MemoryRecord(
            MemoryKind.FACT, SCOPE, "Laptop budget is ₹50,000.",
            [SourceRef("chat://travel/1", "rohan", excerpt=first_prompt)], USER,
        ))
        correction_prompt = "Correction: make that ₹75,000; the old amount is no longer valid."
        second = store.write(MemoryRecord(
            MemoryKind.FACT, SCOPE, "Laptop budget is ₹75,000.",
            [SourceRef("chat://travel/2", "rohan", excerpt=correction_prompt)], USER,
            supersedes_id=first.id,
        ))
        question = "What is my budget for the travel project?"
        hit = store.recall(question, SCOPE, kinds=[MemoryKind.FACT], limit=1)[0]
        return {
            "prompts": [first_prompt, correction_prompt, question],
            "answer": hit.text,
            "evidence": hit.sources[0].uri,
            "old_status": store.get(first.id).status,
            "current_id": second.id,
        }
    finally:
        store.close()


def semantic_document_prompt() -> dict[str, Any]:
    """Show the same real question against a fixed-window control and semantic chunks."""
    document = """# Gemini worker capacity
Each Gemini API key has its own quota. A second Gemini key supplies separate
quota, so independent workers can run at the same time. Do not build another
key scheduler in the planner.

# Browser worker
The browser worker uses Playwright and its accessibility tree."""
    question = "Can a second Gemini key let two independent workers run together?"
    embedder = DeterministicEmbedder(256)
    semantic = semantic_chunks(document, embedder, similarity_threshold=0.05, max_words=40)
    fixed = fixed_word_chunks(document, words=8)
    store = MemoryStore(embedder=embedder)
    try:
        for chunk in semantic:
            store.write(MemoryRecord(
                MemoryKind.DOCUMENT_CHUNK, SCOPE, chunk.text,
                [SourceRef("file://gateway-capacity.md", "indexer")], USER,
                metadata={"heading": chunk.heading, "ordinal": chunk.ordinal},
            ))
        hit = store.recall(question, SCOPE, kinds=[MemoryKind.DOCUMENT_CHUNK], limit=1)[0]
    finally:
        store.close()
    return {
        "prompt": question,
        "semantic_answer_evidence": hit.text,
        "semantic_chunk_count": len(semantic),
        "fixed_windows": fixed,
        "claim": "Yes — the second key has separate quota, and the gateway chooses keys while the graph chooses tasks.",
    }


async def run_all() -> dict[str, Any]:
    return {
        "live_graph": await live_procurement_prompt(),
        "memory": memory_correction_prompt(),
        "semantic_chunking": semantic_document_prompt(),
    }


if __name__ == "__main__":
    import json
    print(json.dumps(asyncio.run(run_all()), indent=2, ensure_ascii=False))

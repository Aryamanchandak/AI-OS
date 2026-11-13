"""The four new Session 7 queries (E to H), run for real.

They make paid model and embedding calls, so they are skipped by default:

    uv run pytest -m live -s tests/test_rag_queries.py

They run in order and share one state folder, because F, G and H depend on
the papers indexed earlier, exactly as in the brief.
"""

from __future__ import annotations

import asyncio
import json
import re

import pytest

import agent7
import memory
from paths import STATE_DIR

pytestmark = pytest.mark.live

MAX_ROUNDS = 8  # the loop's own cap; each round may complete several goals


def _run(query: str) -> str:
    return asyncio.run(agent7.run(query))


def _indexed_sources() -> set[str]:
    items = json.loads((STATE_DIR / "memory.json").read_text())
    return {i["source"] for i in items if i["kind"] == "fact" and i["source"].startswith("sandbox:papers/")}


def test_query_e_index_one_paper_and_answer_from_it():
    memory.clear()
    answer = _run(
        "Index the file papers/attention.md and tell me what the three key contributions "
        "of the Transformer architecture are according to this paper."
    )
    assert "sandbox:papers/attention.md" in _indexed_sources()
    assert re.search(r"attention", answer, re.I)
    assert re.search(r"parallel|positional|recurren", answer, re.I)
    assert agent7.last_run_rounds <= MAX_ROUNDS


def test_query_f_index_all_papers_then_recall_in_a_fresh_run():
    memory.clear()
    answer = _run("Index every .md file under papers/. Confirm how many chunks were indexed in total.")
    assert len(_indexed_sources()) == 5
    assert re.search(r"\d+", answer)
    assert agent7.last_run_rounds <= MAX_ROUNDS

    answer = _run("Across the papers I have indexed, what do they say about chain-of-thought reasoning?")
    assert re.search(r"chain[- ]of[- ]thought", answer, re.I)
    assert re.search(r"step", answer, re.I)
    assert agent7.last_run_rounds <= MAX_ROUNDS


def test_query_g_synonym_recall():
    answer = _run("Across these papers, how do they handle the credit assignment problem?")
    named = [p for p in ("ReAct", "LoRA", "DPO", "chain-of-thought", "Transformer") if p.lower() in answer.lower()]
    assert len(named) >= 2
    assert agent7.last_run_rounds <= MAX_ROUNDS


def test_query_h_compare_two_papers():
    answer = _run(
        "Compare how the ReAct paper and the Chain-of-Thought paper differ in their "
        "treatment of intermediate reasoning."
    )
    assert "react" in answer.lower() and re.search(r"chain[- ]of[- ]thought", answer, re.I)
    assert re.search(r"action|tool", answer, re.I)
    assert agent7.last_run_rounds <= MAX_ROUNDS

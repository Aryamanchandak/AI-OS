"""The four target queries from the Session 6 brief, run for real.

These make paid model calls and use the internet, so they are skipped by
default. Run them with:

    uv run pytest -m live -s

Each query must finish within twice the round count documented in the brief.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil

import pytest

import agent7
import memory
from paths import ROOT, STATE_DIR

pytestmark = pytest.mark.live

SANDBOX = ROOT / "sandbox"


@pytest.fixture
def clean_slate():
    """Empty memory and remove scratch files, keeping the papers and the corpus."""
    memory.clear()
    SANDBOX.mkdir(exist_ok=True)
    for child in SANDBOX.iterdir():
        if child.name in {"papers", "corpus"}:
            continue
        shutil.rmtree(child) if child.is_dir() else child.unlink()


def _run(query: str) -> str:
    return asyncio.run(agent7.run(query))


def test_query_a_shannon(clean_slate):
    answer = _run(
        "Fetch https://en.wikipedia.org/wiki/Claude_Shannon and tell me his birth date, "
        "death date, and three key contributions to information theory."
    )
    assert "1916" in answer and "2001" in answer
    assert "April" in answer and "February" in answer
    assert agent7.last_run_rounds <= 6  # brief: 3


def test_query_b_tokyo(clean_slate):
    answer = _run(
        "Find 3 family-friendly things to do in Tokyo this weekend. Check Saturday's "
        "weather forecast there and tell me which one is most appropriate."
    )
    assert "Tokyo" in answer
    assert re.search(r"rain|sun|cloud|clear|weather|forecast|°|degrees", answer, re.I)
    assert agent7.last_run_rounds <= 8  # brief: 6 (the loop's own cap is 8)


def test_query_c_moms_birthday_survives_a_second_run(clean_slate):
    _run(
        "My mom's birthday is 15 May 2026. Remember that and give me a calendar "
        "reminder for two weeks before and on the day."
    )
    assert agent7.last_run_rounds <= 8  # brief: 4

    facts = [i for i in json.loads((STATE_DIR / "memory.json").read_text()) if i["kind"] == "fact"]
    assert any("birthday" in json.dumps(f).lower() and "2026" in json.dumps(f) for f in facts)
    reminders = [
        p for p in SANDBOX.rglob("*")
        if p.is_file() and not {"papers", "corpus"} & set(p.relative_to(SANDBOX).parts)
    ]
    assert len(reminders) >= 1

    answer = _run("When is mom's birthday?")
    assert "15" in answer and "May" in answer and "2026" in answer
    assert agent7.last_run_rounds <= 4  # brief: 2


def test_query_d_asyncio(clean_slate):
    answer = _run(
        "Search for 'Python asyncio best practices', read the top 3 results, and give "
        "me a short numbered list of the advice they agree on."
    )
    assert len(re.findall(r"^\s*\d+[.)]", answer, re.M)) >= 3
    assert "asyncio" in answer.lower()
    assert agent7.last_run_rounds <= 8  # brief: 5 to 7 (the loop's own cap is 8)

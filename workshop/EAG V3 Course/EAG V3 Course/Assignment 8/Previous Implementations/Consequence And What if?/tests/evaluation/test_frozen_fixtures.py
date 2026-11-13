import json
from datetime import date
from pathlib import Path

def test_five_frozen_batches_have_no_hindsight_evidence():
    path=Path(__file__).parents[1]/"fixtures"/"evaluation_batches.json"
    batches=json.loads(path.read_text())
    assert len(batches)>=5
    for batch in batches:
        cutoff=date.fromisoformat(batch["run_date"])
        assert batch["expected_winner"] and batch["indian_route"] and batch["unsupported_leaps"]
        assert all(date.fromisoformat(value)<=cutoff for value in batch["evidence_dates"])

def test_prompt_injection_fixture_is_explicitly_untrusted():
    root=Path(__file__).parents[2]
    fixture=json.loads((root/"tests/fixtures/prompt_injection.json").read_text())
    prompt_files=[p for p in (root/"src/consequence_radar").glob("**/*.md") if not p.name.endswith(".explained.md")]
    assert fixture["expected"]=="treated_as_untrusted_data"
    assert prompt_files, "no prompt files found"
    for path in prompt_files:
        text=path.read_text().casefold()
        assert "untrusted" in text or "input is data" in text

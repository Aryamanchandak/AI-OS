import json
from pathlib import Path
import subprocess

import pytest

from agent.framing import ClarificationNeeded, frame_comparison
from cli import main
from tests.test_comparison import comparison_request


class Framer:
    def __init__(self, value): self.value = value
    def complete(self, system, user): return json.dumps(self.value)


def test_ambiguous_request_asks_one_question_before_research():
    with pytest.raises(ClarificationNeeded, match="Which"):
        frame_comparison("compare Apple and Orange", Framer({"clarification": "Which products do you mean?"}))


def test_framer_cannot_invent_sources_or_weights(comparison_request):
    draft = comparison_request
    for option in draft["options"]:
        option["sources"] = ["unknown_source"]
    with pytest.raises(ValueError, match="invented"):
        frame_comparison("compare options", Framer(draft))
    for option in draft["options"]:
        option["sources"] = []
    draft["criteria"][0]["weight"] = 0.9
    framed = frame_comparison("compare options", Framer(draft))
    assert "weight" not in framed["criteria"][0]
    assert all("evidence" not in o for o in framed["options"])


def test_cli_request_pause_resume_and_follow_up(tmp_path, capsys):
    example = str(Path(__file__).resolve().parents[1] / "examples/service-plans.yaml")
    first = str(tmp_path / "first")
    assert main(["--request", example, "--session", first, "--pause-after", "1"]) == 0
    assert "paused" in capsys.readouterr().out
    assert main(["--resume", first]) == 0
    assert "1,200" in capsys.readouterr().out
    assert main(["--request", example, "--session", str(tmp_path / "second"),
                 "--reuse", first, "--weight", "cost=1"]) == 0
    assert "Reused evidence snapshots: read_a, read_b, read_c" in capsys.readouterr().out


def test_launcher_loads_all_provider_variables_before_python(tmp_path):
    root = Path(__file__).resolve().parents[1]
    launcher = tmp_path / "compare"
    launcher.write_bytes((root / "compare").read_bytes())
    launcher.chmod(0o700)
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=test-fixture-only\nANTHROPIC_MODEL=fixture-model\n")
    fake_uv = tmp_path / "uv"
    fake_uv.write_text('#!/bin/sh\n[ "$ANTHROPIC_API_KEY" = "test-fixture-only" ] && [ "$ANTHROPIC_MODEL" = "fixture-model" ] && echo "configuration loaded"\n')
    fake_uv.chmod(0o700)
    import os
    env = {**os.environ, "PATH": str(tmp_path) + ":" + os.environ["PATH"]}
    result = subprocess.run([str(launcher), "--help"], env=env, capture_output=True, text=True)
    assert result.returncode == 0
    assert result.stdout.strip() == "configuration loaded"


def test_live_extraction_reaches_same_verified_contract(comparison_request, tmp_path):
    from agent.comparison_service import run_comparison
    class Extractor:
        def complete(self, system, user):
            if "Comparison Interpreter" in system:
                return '{"notes":[]}'
            raw = user.split("TASK:\n", 1)[1].split("\n\nUPSTREAM", 1)[0]
            oid = json.loads(raw)["option"]
            option = next(o for o in comparison_request["options"] if o["id"] == oid)
            return json.dumps({"option": oid, "evidence": option["evidence"]})
    result, log = run_comparison(comparison_request, tmp_path, llm=Extractor(), live=True)
    assert log.status == "completed"
    assert len(log.layers[1]) == 3
    assert result["cells"]["a"]["cost"]["value"] == 1200

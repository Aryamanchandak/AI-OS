from pathlib import Path
import os
import shutil
import subprocess
import sys


def test_comparison_runs_from_isolated_copy_without_ai_os(tmp_path):
    root = Path(__file__).resolve().parents[1]
    isolated = tmp_path / "standalone-agent"
    isolated.mkdir()
    for folder in ("agent", "prompts", "examples"):
        shutil.copytree(root / folder, isolated / folder, ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("cli.py", "agent_config.yaml", "units.yaml"):
        shutil.copy2(root / name, isolated / name)
    env = {k: v for k, v in os.environ.items() if not k.startswith("AI_OS_")
           and k not in {"ANTHROPIC_API_KEY", "PYTHONPATH"}}
    result = subprocess.run([sys.executable, "cli.py", "--request", "examples/service-plans.yaml",
                             "--session", str(tmp_path / "run")], cwd=isolated,
                            env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "1,200 INR/year" in result.stdout
    assert "Status: completed" in result.stdout


def test_pinned_sdk_can_construct_direct_client_without_gateway(monkeypatch):
    from agent.llm import AnthropicLLM
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    client = AnthropicLLM(api_key="fixture-only")
    assert client.client.base_url.host == "api.anthropic.com"
    client.client.close()

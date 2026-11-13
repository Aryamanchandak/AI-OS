from agent.sandbox import run


def test_generated_process_does_not_inherit_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("AI_OS_TOKEN", "private-test-fixture")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "private-test-fixture")
    result = run('import os\nprint(any("TOKEN" in k or "API_KEY" in k for k in os.environ))', {}, tmp_path)
    assert result.ok
    assert result.stdout == "False"

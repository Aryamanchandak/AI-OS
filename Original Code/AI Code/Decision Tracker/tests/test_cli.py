import json
from datetime import date, timedelta

from typer.testing import CliRunner

from decision_tracker.cli import app


runner = CliRunner()


def test_cli_end_to_end(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DT_DB_PATH", str(tmp_path / "cli.db"))
    payload = {
        "author": "AC2",
        "class": "FORECAST",
        "source_classification": "public",
        "title": "CLI forecast",
        "claim": {
            "statement": "The event happens",
            "resolution_source": "public close",
            "resolution_date": (date.today() + timedelta(days=10)).isoformat(),
            "type": "binary",
            "probability": 0.6,
        },
        "reasoning": {
            "base_rate": {"value": 0.4, "source": "public history"},
            "falsifiers": ["opposite event"],
        },
    }
    source = tmp_path / "draft.json"
    source.write_text(json.dumps(payload), encoding="utf-8")

    logged = runner.invoke(app, ["log", str(source)])
    assert logged.exit_code == 0, logged.output
    decision_id = json.loads(logged.stdout)["id"]

    committed = runner.invoke(app, ["commit", decision_id])
    assert committed.exit_code == 0, committed.output

    resolved = runner.invoke(
        app,
        [
            "resolve",
            decision_id,
            "--outcome",
            "true",
            "--evidence",
            "published close",
            "--resolver-source",
            "manual:public close",
            "--automated",
        ],
    )
    assert resolved.exit_code == 0, resolved.output

    verified = runner.invoke(app, ["verify"])
    assert verified.exit_code == 0, verified.output
    assert json.loads(verified.stdout)["valid"] is True


def test_cli_captures_one_line_without_fabricating_probability(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DT_DB_PATH", str(tmp_path / "one-line.db"))

    logged = runner.invoke(app, ["log", "Rates rise next month", "--author", "AC2"])

    assert logged.exit_code == 0, logged.output
    decision_id = json.loads(logged.stdout)["id"]
    shown = runner.invoke(app, ["show", decision_id])
    payload = json.loads(shown.stdout)
    assert payload["claim"]["statement"] == "Rates rise next month"
    assert payload["claim"]["probability"] is None

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from scripts import live_smoke


def test_default_main_separates_temp_artifacts_from_shared_neo4j(
    monkeypatch,
    tmp_path: Path,
    capsys,
) -> None:
    fixture = tmp_path / "fixture.md"
    fixture.write_text("A bounded smoke-test document.", encoding="utf-8")
    central_root = tmp_path / "central" / "Database"
    observed: dict[str, Any] = {}

    monkeypatch.setattr(sys, "argv", ["live_smoke.py", str(fixture)])
    monkeypatch.setattr(live_smoke, "load_root_env", lambda *_: None)
    monkeypatch.setattr(
        live_smoke,
        "central_database_root",
        lambda *_: central_root,
    )

    def fake_run(
        config,
        document,
        *,
        keep_graph,
        neo4j_data_root,
    ):
        observed.update(
            {
                "database_root": config.database_root,
                "document": document,
                "keep_graph": keep_graph,
                "neo4j_data_root": neo4j_data_root,
            }
        )
        return {"result": "PASS"}

    monkeypatch.setattr(live_smoke, "_run", fake_run)

    live_smoke.main()

    assert observed["document"] == fixture.resolve()
    assert observed["keep_graph"] is False
    assert observed["neo4j_data_root"] == central_root / "neo4j"
    assert observed["database_root"] != central_root
    assert observed["database_root"].name == "Database"
    assert "ingestion-t5-" in str(observed["database_root"].parent)
    assert not observed["database_root"].parent.exists()
    assert json.loads(capsys.readouterr().out)["result"] == "PASS"


def test_explicit_roots_are_forwarded_independently(
    monkeypatch,
    tmp_path: Path,
) -> None:
    fixture = tmp_path / "fixture.md"
    fixture.write_text("A bounded smoke-test document.", encoding="utf-8")
    artifact_root = tmp_path / "artifacts"
    neo4j_root = tmp_path / "shared-neo4j"
    observed: dict[str, Any] = {}

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "live_smoke.py",
            str(fixture),
            "--database-root",
            str(artifact_root),
            "--neo4j-data-root",
            str(neo4j_root),
            "--keep-graph",
        ],
    )
    monkeypatch.setattr(live_smoke, "load_root_env", lambda *_: None)

    def fake_run(
        config,
        document,
        *,
        keep_graph,
        neo4j_data_root,
    ):
        observed.update(
            {
                "database_root": config.database_root,
                "keep_graph": keep_graph,
                "neo4j_data_root": neo4j_data_root,
            }
        )
        return {"result": "PASS"}

    monkeypatch.setattr(live_smoke, "_run", fake_run)

    live_smoke.main()

    assert observed == {
        "database_root": artifact_root.resolve(),
        "keep_graph": True,
        "neo4j_data_root": neo4j_root.resolve(),
    }

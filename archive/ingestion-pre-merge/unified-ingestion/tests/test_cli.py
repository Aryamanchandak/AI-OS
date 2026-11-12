import json
from pathlib import Path

from unified_ingestion.cli import main


def test_cli_capture_and_status_use_external_database_root(
    tmp_path: Path, capsys: object
) -> None:
    source = tmp_path / "note.md"
    source.write_text("Duration", encoding="utf-8")
    database_root = tmp_path / "Database"

    assert (
        main(
            [
                "--database-root",
                str(database_root),
                "--offline",
                "capture",
                "--source-type",
                "note",
                "--origin",
                str(source),
                "--file",
                str(source),
            ]
        )
        == 0
    )
    assert main(["--database-root", str(database_root), "--offline", "status"]) == 0
    output = capsys.readouterr().out  # type: ignore[attr-defined]
    assert '"source_records": 1' in output
    assert not (Path(__file__).parents[1] / "data").exists()

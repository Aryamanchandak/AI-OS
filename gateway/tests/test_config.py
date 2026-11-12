from __future__ import annotations

from pathlib import Path

import pytest

from gateway.config import load_mapping

SOURCE = Path(__file__).resolve().parents[1] / "src" / "gateway"


def test_load_mapping_reads_a_yaml_mapping(tmp_path: Path) -> None:
    path = tmp_path / "ok.yaml"
    path.write_text("version: 1\n", encoding="utf-8")
    assert load_mapping(path) == {"version": 1}


@pytest.mark.parametrize(("content", "message"), [
    (None, "does not exist"),
    ("version: [1\n", "malformed"),
    ("- version\n", "must be a YAML mapping"),
    ("", "must be a YAML mapping"),
])
def test_load_mapping_gives_a_clear_error(tmp_path: Path, content: str | None, message: str) -> None:
    path = tmp_path / "config.yaml"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match=message) as caught:
        load_mapping(path)
    assert str(path) in str(caught.value)


def test_only_config_imports_yaml() -> None:
    importers = sorted(p.relative_to(SOURCE).as_posix() for p in SOURCE.rglob("*.py") if "import yaml" in p.read_text(encoding="utf-8"))
    assert importers == ["config.py"]


def test_only_the_database_helper_opens_sqlite() -> None:
    openers = sorted(p.relative_to(SOURCE).as_posix() for p in SOURCE.rglob("*.py") if "sqlite3.connect" in p.read_text(encoding="utf-8"))
    assert openers == ["db.py"]

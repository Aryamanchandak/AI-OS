from __future__ import annotations

from pathlib import Path


def test_migrated_domains_do_not_inject_sibling_paths() -> None:
    source_root = Path(__file__).resolve().parents[1] / "src"
    offenders = [
        path.relative_to(source_root).as_posix()
        for path in source_root.rglob("*.py")
        if "sys.path" in path.read_text(encoding="utf-8")
    ]
    assert offenders == []

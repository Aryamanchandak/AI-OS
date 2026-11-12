"""The layout rules, checked by reading the code: trunk never depends on a leaf, leaves never depend on each other."""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The only path to a model is core/llm.py -> the gateway (interface I1).
BANNED_LIBRARIES = {"anthropic", "openai", "any_llm", "ollama", "simple_llm"}


def imports_of(file: Path) -> set[str]:
    """Every module name a Python file imports, e.g. {'core.store', 'leaves.learning.grade'}."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(file.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def violations(root: Path) -> list[str]:
    """Plain-English list of every broken layout rule under root."""
    found: list[str] = []
    for folder in ("core", "leaves"):
        for file in sorted((root / folder).rglob("*.py")):
            where = file.relative_to(root).as_posix()
            if ast.get_docstring(ast.parse(file.read_text(encoding="utf-8"))) is None:
                found.append(f"{where}: no one-line description at the top")
            for name in sorted(imports_of(file)):
                parts = name.split(".")
                if parts[0] in BANNED_LIBRARIES:
                    found.append(f"{where}: imports {name}; models are reached only through core/llm.py")
                if parts[0] != "leaves" or len(parts) < 2:
                    continue
                if folder == "core":
                    found.append(f"{where}: trunk imports leaf {name}")
                elif parts[1] != file.relative_to(root / "leaves").parts[0]:
                    found.append(f"{where}: leaf imports another leaf {name}; call its tool instead")
    return found


def test_repo_follows_the_layout_rules():
    assert violations(ROOT) == []


def test_every_leaf_is_a_package_with_a_description():
    for leaf in sorted(p for p in (ROOT / "leaves").iterdir() if p.is_dir() and p.name != "__pycache__"):
        assert (leaf / "__init__.py").exists(), f"leaves/{leaf.name} has no __init__.py"


def _write(root: Path, path: str, text: str) -> None:
    file = root / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(text, encoding="utf-8")


def test_the_checker_catches_each_broken_rule(tmp_path):
    _write(tmp_path, "core/store.py", '"""Store."""\nfrom leaves.learning import tools\n')
    _write(tmp_path, "core/llm.py", '"""Client."""\nimport anthropic\n')
    _write(tmp_path, "core/bare.py", "x = 1\n")
    _write(tmp_path, "leaves/telegram/bot.py", '"""Bot."""\nimport leaves.learning.grade\n')
    _write(tmp_path, "leaves/learning/tools.py", '"""Tools."""\nfrom leaves.learning import grade\nfrom core import store\n')

    found = violations(tmp_path)

    assert len(found) == 4
    assert any("core/store.py: trunk imports leaf" in v for v in found)
    assert any("core/llm.py: imports anthropic" in v for v in found)
    assert any("core/bare.py: no one-line description" in v for v in found)
    assert any("leaves/telegram/bot.py: leaf imports another leaf" in v for v in found)

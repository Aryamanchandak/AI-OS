"""
Shared sandbox for utility file tools.
All file paths from the model are resolved through _safe() before any I/O.
"""
from pathlib import Path

SANDBOX = Path(__file__).parent / "sandbox"
SANDBOX.mkdir(exist_ok=True)


def _safe(path: str) -> Path:
    """Resolve `path` inside the sandbox. Raises ValueError on traversal attempts."""
    p = (SANDBOX / path).resolve()
    base = SANDBOX.resolve()
    if p != base and base not in p.parents:
        raise ValueError(f"Path '{path}' escapes the sandbox")
    return p

"""Starter tools. Safe, dependency-free, deterministic enough to demo the loop.

Replace/extend these with the tools you copy over — each is just a plain
function with a docstring (which becomes the tool description) and type hints
(which become the input schema). Keep the `@mcp.tool()` decorator.
"""

from __future__ import annotations

import ast
import operator
from datetime import datetime, timezone

from ..app import mcp

# ---------------------------------------------------------------------------
# A safe arithmetic evaluator — no eval(), no names, just numbers + operators.
# ---------------------------------------------------------------------------
_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval(node: ast.AST) -> float:
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPS:
        return _OPS[type(node.op)](_eval(node.operand))
    raise ValueError("unsupported expression")


@mcp.tool()
def calculator(expression: str) -> str:
    """Evaluate a basic arithmetic expression.

    Supports + - * / // % ** and parentheses over numbers only (no variables,
    no function calls). Example: "12.5/100 * 4800".
    """
    try:
        tree = ast.parse(expression, mode="eval")
        result = _eval(tree.body)
    except Exception as e:  # noqa: BLE001 -- surface a clean error to the agent
        return f"ERROR: could not evaluate '{expression}': {e}"
    # Present whole numbers without a trailing .0
    if isinstance(result, float) and result.is_integer():
        result = int(result)
    return str(result)


@mcp.tool()
def get_current_time() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@mcp.tool()
def text_stats(text: str) -> str:
    """Return word count, character count, and line count for a piece of text."""
    words = len(text.split())
    chars = len(text)
    lines = len(text.splitlines()) or (1 if text else 0)
    return f"words={words}, chars={chars}, lines={lines}"

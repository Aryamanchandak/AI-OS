"""
generative_ui.py — the agent builds its OWN UI, live, with Prefab.

This is the "generative UI" model: instead of the agent picking from a fixed
menu of hand-authored screens, it *writes Prefab component code* tailored to
whatever it wants to show, and this tool renders it. The agent decides when a
UI is worth building and what goes in it — the assignment's "communicate back
via a UI (built with Prefab)", done the generative way.

Two tools:
  - list_ui_components  — lets the agent look up the Prefab component catalog
                          (names + import paths) before writing code.
  - render_ui           — executes the agent's Prefab Python, injects the shared
                          React Loop dark theme, and writes an HTML snapshot the
                          web app serves at /ui/latest.

Execution model: the agent's code runs IN-PROCESS via exec() (chosen for a
local single-user setup — zero install). It therefore runs with the same
privileges as this server. For an untrusted/multi-user deployment, swap the
body of _run_code() for Prefab's Deno/Pyodide sandbox (prefab_ui.generative.execute).
"""

from __future__ import annotations

import json
from typing import Any

from prefab_ui.app import PrefabApp
from prefab_ui.generative import get_all_components, search_components

import filestore

from ..app import mcp
from ..config import app_url
from .prefab_theme import REACT_LOOP_THEME

# Snapshot lives in its own subdir so it never shows up as a store "file".
_GENERATED_DIRNAME = "generated_ui"


def _snapshot_path():
    out_dir = filestore.base_dir() / _GENERATED_DIRNAME
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / "index.html"


class _AccessTracker:
    def __init__(self) -> None:
        self.accessed = False

    def mark(self) -> None:
        self.accessed = True


class _TrackedList(list):
    def __init__(self, value: list[Any], tracker: _AccessTracker) -> None:
        super().__init__(_track(v, tracker) for v in value)
        self._tracker = tracker

    def __iter__(self):
        self._tracker.mark()
        return super().__iter__()

    def __getitem__(self, key):
        self._tracker.mark()
        return super().__getitem__(key)

    def __len__(self) -> int:
        self._tracker.mark()
        return super().__len__()


class _TrackedDict(dict):
    def __init__(self, value: dict[str, Any], tracker: _AccessTracker) -> None:
        super().__init__((k, _track(v, tracker)) for k, v in value.items())
        self._tracker = tracker

    def __iter__(self):
        self._tracker.mark()
        return super().__iter__()

    def __getitem__(self, key):
        self._tracker.mark()
        return super().__getitem__(key)

    def __len__(self) -> int:
        self._tracker.mark()
        return super().__len__()

    def get(self, key, default=None):
        self._tracker.mark()
        return super().get(key, default)


def _track(value: Any, tracker: _AccessTracker) -> Any:
    if isinstance(value, list):
        return _TrackedList(value, tracker)
    if isinstance(value, dict):
        return _TrackedDict(value, tracker)
    return value


def _component_names() -> str:
    """Real, importable component names — appended to import/name errors so the
    agent's next retry uses a name that actually exists instead of guessing again."""
    return ", ".join(sorted(get_all_components()))


def _exec_error(exc: Exception, retry_hint: str) -> str:
    message = f"UI code failed to execute — {type(exc).__name__}: {exc}\n{retry_hint}"
    if isinstance(exc, (ImportError, NameError)):
        message += f"\nValid component names: {_component_names()}"
    return message


def _capture_app(namespace: dict) -> PrefabApp | None:
    """Find the PrefabApp the agent's code built (prefer a var named `app`)."""
    candidate = namespace.get("app")
    if isinstance(candidate, PrefabApp):
        return candidate
    return next(
        (v for v in namespace.values() if isinstance(v, PrefabApp)),
        None,
    )


@mcp.tool()
def list_ui_components(query: str = "", detail: bool = False) -> str:
    """List the Prefab UI components available for building a UI with render_ui.

    Call this BEFORE writing render_ui code so you use real component names and
    import paths. Returns a compact catalog by default.

    Args:
        query: Optional filter, e.g. "chart", "card", "table". Empty = all.
        detail: Set true for full prop/usage detail on the matches (larger output).
    """
    return search_components(query, detail=detail or None)


@mcp.tool()
def render_ui(code: str) -> str:
    """Build and show a UI by writing Prefab Python. Use this to communicate
    results back to the user visually instead of (or alongside) plain text.

    Write a short Python snippet that constructs a Prefab component tree. Rules:
      - The outermost object MUST be `with PrefabApp() as app:` (assign it to `app`).
      - Import components from `prefab_ui.components` and the app from
        `prefab_ui.app`. Look up component names with the list_ui_components tool.
      - Do NOT set any theme/colors — the React Loop dark theme is applied for you.
      - Put your real data directly into the components (this renders a snapshot).

    Build a REAL dashboard, not a title with a couple of text lines. Use several
    components together, and reach for `Mermaid` (a real Mermaid.js diagram — use
    it whenever you're asked for a "diagram") and the chart components in
    `prefab_ui.components.charts` (BarChart, PieChart, RadarChart, ...) whenever
    the data has any structure worth visualizing, not just prose in a Card.

    Example (metrics + a diagram, mixed on one screen):
        from prefab_ui.app import PrefabApp
        from prefab_ui.components import Column, Heading, Row, Metric, Card, CardContent, Text, Mermaid

        with PrefabApp() as app:
            with Column(gap=6):
                Heading("Sales Summary", level=2)
                with Row(gap=4):
                    Metric(label="Revenue", value="$1.2M")
                    Metric(label="Deals", value=42)
                with Card():
                    with CardContent():
                        Text("Q3 beat target by 8%.")
                        Mermaid('''
                            graph LR
                                Lead --> Qualified --> Proposal --> Closed[Closed Won]
                        ''')

    On success returns the URL to view the UI. On error returns the Python error
    so you can fix your code and call render_ui again.

    Args:
        code: Prefab Python source that builds a PrefabApp bound to `app`.
    """
    namespace: dict = {}
    try:
        exec(code, namespace)  # in-process by design (see module docstring)
    except Exception as exc:  # surface the error so the agent can self-correct
        return _exec_error(
            exc,
            "Fix the code and call render_ui again. Remember to import what you "
            "use and wrap the tree in `with PrefabApp() as app:`.",
        )

    app = _capture_app(namespace)
    if app is None:
        return (
            "No PrefabApp was created. Your code must contain "
            "`with PrefabApp() as app:` as the outermost block. Try again."
        )

    app.theme = REACT_LOOP_THEME  # native React Loop look, applied for the agent
    try:
        html = app.html()
    except Exception as exc:
        return f"UI was built but failed to render — {type(exc).__name__}: {exc}"

    snapshot = _snapshot_path()
    snapshot.write_text(html, encoding="utf-8")
    return (
        "UI rendered successfully.\n"
        f"View it (while the web app runs): {app_url('/ui/latest')}\n"
        f"Static snapshot: {snapshot}"
    )


@mcp.tool()
def render_ui_from_json(name: str, code: str) -> str:
    """Build a UI from a persisted JSON file in the local store.

    Use this when the UI is supposed to represent data saved in a ``.json`` file.
    The JSON is loaded from the store and exposed to the code as ``data`` and
    ``source_file``. The code must touch ``data`` and create a ``PrefabApp``.
    Missing files, invalid JSON, and code that ignores the persisted data fail.
    """
    try:
        raw = filestore.read(name)
    except ValueError as exc:
        return f"ERROR: {exc}"
    except FileNotFoundError:
        return f"ERROR: '{name}' does not exist. UI was not rendered."

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        return (
            f"ERROR: Invalid JSON at line {exc.lineno}, column {exc.colno}: "
            f"{exc.msg}. UI was not rendered."
        )

    tracker = _AccessTracker()
    tracked_data = _track(parsed, tracker)
    namespace: dict[str, Any] = {"data": tracked_data, "source_file": name}
    try:
        exec(code, namespace)
        builder = namespace.get("build_ui")
        if _capture_app(namespace) is None and callable(builder):
            namespace["app"] = builder(tracked_data)
    except Exception as exc:
        return _exec_error(exc, "Fix the code and call render_ui_from_json again.")

    if not tracker.accessed:
        return (
            "ERROR: UI code did not read the persisted JSON `data`. "
            "UI was not rendered."
        )

    app = _capture_app(namespace)
    if app is None:
        return (
            "No PrefabApp was created. Your code must create `app` or define "
            "`build_ui(data)` returning a PrefabApp. Try again."
        )

    app.theme = REACT_LOOP_THEME
    try:
        html = app.html()
    except Exception as exc:
        return f"UI was built but failed to render — {type(exc).__name__}: {exc}"

    snapshot = _snapshot_path()
    snapshot.write_text(html, encoding="utf-8")
    return (
        f"UI rendered successfully from {name}.\n"
        f"View it (while the web app runs): {app_url('/ui/latest')}\n"
        f"Static snapshot: {snapshot}"
    )

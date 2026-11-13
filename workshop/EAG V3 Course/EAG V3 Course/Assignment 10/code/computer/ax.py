"""Accessibility snapshots preserve cua-driver's turn-scoped indices."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from .backend import CuaError, get_driver

@dataclass
class Element:
    id: int
    role: str
    name: str
    value: str = ""
    def legend_line(self):
        return f'[element_index {self.id}] {self.role} "{self.name}"'

@dataclass
class UISnapshot:
    elements: list[Element]
    app: str
    window_title: str = ""
    pid: int = 0
    window_id: int = 0
    tree: str = ""
    screenshot: dict = field(default_factory=dict)
    def by_id(self, mark):
        return next((e for e in self.elements if e.id == mark), None)
    def legend(self, max_chars=40_000):
        return self.tree[:max_chars]
    def text_dump(self):
        return self.tree

def ax_available():
    return get_driver().call("check_permissions", {"prompt": False}).get("accessibility") is True

def bind_app(app, *, pid=None, window_id=None):
    driver = get_driver()
    response = driver.call("list_windows", {"pid": int(pid)} if pid else {})
    windows = response.get("windows", []) if isinstance(response, dict) else response
    matches = [w for w in windows if
               (int(w.get("pid", 0)) == int(pid) if pid else
                w.get("app_name", "").casefold() == app.casefold())
               and (window_id is None or int(w["window_id"]) == int(window_id))]
    if not matches:
        raise CuaError(f"No window found for {app!r}; launch and activate the target first")
    chosen = next((w for w in matches if w.get("is_on_screen")), matches[0])
    driver.target = {**chosen, "app": app}
    return driver.target

def enumerate_ui(app_name, *, mode="ax", screenshot_path=None, **_):
    driver = get_driver()
    if driver.target is None or driver.target.get("app") != app_name:
        bind_app(app_name)
    args = {"pid": driver.target["pid"], "window_id": driver.target["window_id"], "capture_mode": mode}
    if screenshot_path is not None:
        args["screenshot_out_file"] = str(screenshot_path)
    raw = driver.call("get_window_state", args)
    tree = raw.get("tree_markdown", "")
    elements, seen = [], set()
    for line in tree.splitlines():
        match = re.search(r'\[element_index (\d+)\]\s+(AX\w+)(.*)', line)
        if match and int(match[1]) not in seen:
            seen.add(int(match[1]))
            elements.append(Element(int(match[1]), match[2], match[3].strip(' "')))
    return UISnapshot(elements, app_name, driver.target.get("title", ""),
                      args["pid"], args["window_id"], tree, raw)

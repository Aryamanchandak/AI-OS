"""The four things the agent may do to a workspace, and the rules on them.

The protected-path rule is enforced here, at run time. It is not a request in
the prompt: a write under a protected path is refused before it lands, and the
refusal is returned so the journal records the attempt.
"""
from pathlib import Path

from harness.grader import run_check

MAX_OUTPUT_CHARS = 3000


class Workspace:
    def __init__(self, root, protected, check_timeout_s=30):
        self.root = Path(root).resolve()
        self.protected = [p.strip("/") for p in protected]
        self.check_timeout_s = check_timeout_s

    def call(self, action):
        """Run one tool action. Always returns {"ok", "output", "refused", ...}."""
        tool = action.get("tool")
        try:
            if tool == "list_files":
                return self._list_files()
            if tool == "read_file":
                return self._read_file(action["path"])
            if tool == "write_file":
                return self._write_file(action["path"], action["content"])
            if tool == "run_tests":
                return self._run_tests()
        except (KeyError, TypeError):
            return _refuse("bad_arguments", f"Missing or wrong arguments for {tool}.")
        return _refuse("unknown_tool", f"Unknown tool: {tool!r}.")

    def _resolve(self, relative):
        path = (self.root / str(relative)).resolve()
        return path if path.is_relative_to(self.root) and path != self.root else None

    def _is_protected(self, path):
        relative = path.relative_to(self.root).as_posix()
        return any(relative == p or relative.startswith(p + "/") for p in self.protected)

    def _list_files(self):
        files = sorted(
            p.relative_to(self.root).as_posix()
            for p in self.root.rglob("*")
            if p.is_file() and "__pycache__" not in p.parts
        )
        return {"ok": True, "output": "\n".join(files), "refused": None}

    def _read_file(self, relative):
        path = self._resolve(relative)
        if path is None:
            return _refuse("outside_workspace", "That path is outside the repository.")
        if not path.is_file():
            return {"ok": False, "output": f"No such file: {relative}", "refused": None}
        return {"ok": True, "output": path.read_text(encoding="utf-8")[:MAX_OUTPUT_CHARS * 3], "refused": None}

    def _write_file(self, relative, content):
        path = self._resolve(relative)
        if path is None:
            return _refuse("outside_workspace", "That path is outside the repository.")
        if self._is_protected(path):
            return _refuse("protected_path", f"Refused: {relative} is protected and cannot be changed.")
        if not isinstance(content, str):
            return _refuse("bad_arguments", "content must be a string.")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {"ok": True, "output": f"Wrote {relative}.", "refused": None}

    def _run_tests(self):
        check = run_check(self.root, timeout_s=self.check_timeout_s)
        return {
            "ok": check["exit_code"] == 0,
            "output": check["output"][-MAX_OUTPUT_CHARS:],
            "refused": None,
            "exit_code": check["exit_code"],
        }


def _refuse(reason, message):
    return {"ok": False, "output": message, "refused": reason}

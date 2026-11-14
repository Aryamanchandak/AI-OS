"""Projects on disk, and the one build that may run at a time.

A build is: rebuild the workspace from the agreed sheet, start an engine run
under an id we chose, copy the engine's journal into the build's activity as it
grows, then run the check ourselves and keep the page only if it passes.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from . import activity, interpret, spec, workspace
from .engine import Engine, EngineError


class Busy(RuntimeError):
    pass


class Store:
    """One JSON file per project plus the pages that passed. Small on purpose."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def _dir(self, project_id: str) -> Path:
        if not project_id.isalnum():
            raise KeyError(project_id)
        return self.root / project_id

    def create(self, sheet: dict) -> dict:
        project = {"id": uuid.uuid4().hex[:10], "created": datetime.now().isoformat(timespec="seconds"),
                   "sheet": sheet, "builds": [], "versions": [], "follow_ups": []}
        self.save(project)
        return project

    def load(self, project_id: str) -> dict:
        path = self._dir(project_id) / "project.json"
        if not path.is_file():
            raise KeyError(project_id)
        with self.lock:
            return json.loads(path.read_text(encoding="utf-8"))

    def save(self, project: dict) -> None:
        folder = self._dir(project["id"])
        folder.mkdir(parents=True, exist_ok=True)
        with self.lock:
            temporary = folder / "project.json.tmp"
            temporary.write_text(json.dumps(project, ensure_ascii=False, indent=1), encoding="utf-8")
            temporary.replace(folder / "project.json")

    def list(self) -> list[dict]:
        found = []
        for path in sorted(self.root.glob("*/project.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            project = json.loads(path.read_text(encoding="utf-8"))
            found.append({"id": project["id"], "title": project["sheet"]["title"] or "(untitled)",
                          "created": project["created"], "versions": len(project["versions"])})
        return found

    def page_path(self, project_id: str, version: int) -> Path:
        return self._dir(project_id) / "versions" / f"{int(version)}.html"

    def latest_page(self, project: dict) -> str | None:
        if not project["versions"]:
            return None
        return self.page_path(project["id"], project["versions"][-1]["number"]).read_text(encoding="utf-8")


class Builder:
    def __init__(self, *, engine: Engine, store: Store, workspace_root: Path, run_timeout: int,
                 poll_seconds: float = 0.5) -> None:
        self.engine, self.store, self.workspace_root = engine, store, workspace_root
        self.run_timeout, self.poll_seconds = run_timeout, poll_seconds
        self._slot = threading.Lock()          # the engine has one workspace, so one build at a time
        self.thread: threading.Thread | None = None

    @property
    def busy(self) -> bool:
        return self._slot.locked()

    def start(self, project_id: str) -> dict:
        project = self.store.load(project_id)
        problems = spec.blockers(project["sheet"])
        if problems:
            raise spec.SheetError("Not agreed yet: " + " ".join(problems))
        if not self._slot.acquire(blocking=False):
            raise Busy("another build is running; the engine has one workspace")
        try:
            # Reach the engine before promising anything. No engine, no progress to show.
            self.engine.health()
            previous = self.store.latest_page(project)
            change = project["follow_ups"][-1]["text"] if previous is not None and project["follow_ups"] else None
            goal = interpret.build_goal(project["sheet"], has_previous_page=previous is not None,
                                        change_request=change)
            prints = workspace.prepare(self.workspace_root, spec_markdown=spec.spec_markdown(project["sheet"]),
                                       cases=spec.cases(project["sheet"]), previous_page=previous)
            build = {"id": uuid.uuid4().hex[:10], "run_id": f"ftb-{uuid.uuid4().hex[:16]}",
                     "started": datetime.now().isoformat(timespec="seconds"), "status": "running",
                     "reason": "", "activity": [], "verification": None, "version": None,
                     "kind": "change" if previous is not None else "first build",
                     "rules": [rule["text"] for rule in project["sheet"]["rules"]]}
            project["builds"].append(build)
            self.store.save(project)
        except BaseException:
            self._slot.release()
            raise
        self.thread = threading.Thread(target=self._run, args=(project_id, build["id"], goal, prints),
                                       daemon=True, name=f"build-{build['id']}")
        self.thread.start()
        return build

    # ------------------------------------------------------------------ the build thread

    def _update(self, project_id: str, build_id: str, **changes) -> dict:
        with self.store.lock:
            project = self.store.load(project_id)
            build = next(item for item in project["builds"] if item["id"] == build_id)
            new_lines = changes.pop("add_activity", [])
            build["activity"].extend(new_lines)
            build.update(changes)
            self.store.save(project)
            return build

    def _note(self, project_id: str, build_id: str, title: str, detail: str = "", tone: str = "info") -> None:
        self._update(project_id, build_id, add_activity=[
            {"seq": None, "kind": "app", "node": None, "capability": "", "title": title,
             "detail": detail, "tone": tone}])

    def _run(self, project_id: str, build_id: str, goal: str, prints: dict[str, str]) -> None:
        try:
            build = self._update(project_id, build_id)
            run_id = build["run_id"]
            self._note(project_id, build_id, "Workspace rebuilt from the agreed sheet",
                       "Protected: " + ", ".join(workspace.PROTECTED))
            outcome: dict = {}

            def call_engine() -> None:
                try:
                    outcome["result"] = self.engine.start_run(run_id, goal, timeout=self.run_timeout)
                except EngineError as error:
                    outcome["error"] = str(error)
                except Exception as error:              # anything else is still a visible failure
                    outcome["error"] = f"{type(error).__name__}: {error}"

            caller = threading.Thread(target=call_engine, daemon=True)
            caller.start()

            seen, journal, lost = 0, None, False
            while True:
                finished = not caller.is_alive()
                try:
                    latest = self.engine.journal(run_id)
                    if lost:
                        self._note(project_id, build_id, "Engine is answering again")
                        lost = False
                except EngineError as error:
                    latest = None
                    if not lost:
                        self._note(project_id, build_id, "Lost contact with the engine", str(error), "bad")
                        lost = True
                if latest is not None:
                    journal = latest
                    fresh = activity.lines(journal, after=seen)
                    if fresh:
                        seen = fresh[-1]["seq"]
                        self._update(project_id, build_id, add_activity=fresh)
                if finished:
                    break
                time.sleep(self.poll_seconds)

            self._finish(project_id, build_id, outcome, journal, prints)
        except Exception as error:
            self._update(project_id, build_id, status="failed",
                         reason=f"The app failed while running the build: {type(error).__name__}: {error}")
        finally:
            self._slot.release()

    def _finish(self, project_id: str, build_id: str, outcome: dict, journal: dict | None,
                prints: dict[str, str]) -> None:
        if "error" in outcome:
            self._note(project_id, build_id, "The engine call failed", outcome["error"], "bad")
            self._update(project_id, build_id, status="failed", reason=outcome["error"])
            return
        result = outcome["result"]
        # Our own run of the check, whatever the engine reported.
        check = workspace.verify(self.workspace_root, prints)
        self._note(project_id, build_id,
                   f"App re-ran `{check['command']}` itself → "
                   + ("PASS" if check["passed"] else f"FAIL (exit {check['exit_code']})"),
                   check["output"] or check["reason"], "ok" if check["passed"] else "bad")
        engine_status = result.get("status")
        if engine_status != "completed":
            said = activity.stop_reason(journal) or f"S17Code reported status {engine_status!r}"
            planner_error = ((result.get("trace") or {}).get("planner") or {}).get("error")
            reason = f"The engine stopped without finishing: {said}"
            if planner_error and planner_error not in reason:
                reason += f" ({planner_error})"
            self._update(project_id, build_id, status="failed", reason=reason, verification=check)
            return
        if not check["passed"]:
            self._update(project_id, build_id, status="failed", verification=check,
                         reason="The engine said it was done, but " + check["reason"] + ".")
            return
        with self.store.lock:
            project = self.store.load(project_id)
            number = len(project["versions"]) + 1
            page = self.store.page_path(project_id, number)
            page.parent.mkdir(parents=True, exist_ok=True)
            page.write_text((self.workspace_root / "index.html").read_text(encoding="utf-8"), encoding="utf-8")
            project["versions"].append({"number": number, "build": build_id,
                                        "created": datetime.now().isoformat(timespec="seconds")})
            self.store.save(project)
        self._update(project_id, build_id, status="passed", verification=check, version=number,
                     reason=str(result.get("answer") or "")[:2_000])

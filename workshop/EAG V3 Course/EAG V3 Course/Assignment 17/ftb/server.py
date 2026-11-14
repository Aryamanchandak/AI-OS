"""The local web app: a JSON API over the modules beside it, and one page.

Bound to 127.0.0.1. The browser never receives a credential: the engine token
and the gateway address stay in this process.
"""
from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import interpret, spec
from .builds import Builder, Busy, Store
from .config import ROOT, Settings
from .engine import Engine, EngineError
from .gateway import Gateway, GatewayError

STATIC = Path(__file__).parent / "static"
EXAMPLES = ROOT / "examples"
# A generated page is shown in a sandboxed frame and may load or call nothing.
PAGE_POLICY = ("default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
               "img-src data:; font-src data:; form-action 'none'; base-uri 'none'")


class Problem(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status, self.message = status, message


class App:
    def __init__(self, settings: Settings, *, engine: Engine | None = None, gateway=None) -> None:
        self.settings = settings
        self.engine = engine or Engine(settings.engine_url, settings.engine_token)
        self.gateway = gateway or Gateway(settings.gateway_url, settings.gateway_provider)
        self.store = Store(settings.data / "projects")
        self.builder = Builder(engine=self.engine, store=self.store, workspace_root=settings.workspace,
                               run_timeout=settings.run_timeout)
        self._close_interrupted_builds()

    def _close_interrupted_builds(self) -> None:
        for item in self.store.list():
            project = self.store.load(item["id"])
            stale = [build for build in project["builds"] if build["status"] == "running"]
            for build in stale:
                build["status"] = "failed"
                build["reason"] = "The app was restarted while this build was running."
            if stale:
                self.store.save(project)

    # ---------------------------------------------------------------- routes

    def status(self) -> dict:
        try:
            self.engine.health()
            engine = {"ok": True, "detail": self.settings.engine_url}
        except EngineError as error:
            engine = {"ok": False, "detail": str(error)}
        if engine["ok"] and not self.settings.engine_token:
            engine = {"ok": False, "detail": "S17_CONTROL_TOKEN is not set in .env, so the engine will refuse runs"}
        return {"engine": engine, "busy": self.builder.busy}

    def examples(self) -> list[dict]:
        def cases(name: str) -> list[dict]:
            return json.loads((EXAMPLES / name / "cases.json").read_text(encoding="utf-8"))["cases"]
        return [
            {"id": "rebalance", "route": "prompt", "label": "Portfolio rebalancing calculator",
             "request": (EXAMPLES / "rebalance" / "request.md").read_text(encoding="utf-8"),
             "document": None, "cases": cases("rebalance")},
            {"id": "fees", "route": "document", "label": "Fee calculator from a fee schedule",
             "request": "Build a fee calculator from this fee schedule.",
             "document": (EXAMPLES / "fees" / "fee_schedule.md").read_text(encoding="utf-8"),
             "cases": cases("fees")},
        ]

    def create_project(self, body: dict) -> dict:
        sheet = spec.new_sheet(str(body.get("route")), str(body.get("request") or ""), body.get("document"))
        sheet = interpret.first_interpretation(self.gateway, sheet)
        for case in body.get("cases") or []:
            # Known answers supplied with the request. Still unconfirmed until the user ticks them.
            spec.add_example(sheet, case.get("name") or "Supplied example", case.get("input"),
                             case.get("expected"), origin="user")
        return self._view(self.store.create(sheet))

    def _editable(self, project_id: str) -> dict:
        if self.builder.busy:
            raise Problem(409, "A build is running. Wait for it to finish before changing the rules.")
        return self.store.load(project_id)

    def review(self, project_id: str, body: dict) -> dict:
        with self.store.lock:
            project = self._editable(project_id)
            project["sheet"] = spec.apply_review(project["sheet"], body)
            self.store.save(project)
        return self._view(project)

    def follow_up(self, project_id: str, body: dict) -> dict:
        project = self._editable(project_id)
        text = str(body.get("text") or "")
        sheet = interpret.follow_up(self.gateway, project["sheet"], text)
        with self.store.lock:
            project = self._editable(project_id)
            project["sheet"] = sheet
            project["follow_ups"].append({"text": text.strip()[:4_000]})
            self.store.save(project)
        return self._view(project)

    def build(self, project_id: str) -> dict:
        build = self.builder.start(project_id)
        return {"build_id": build["id"]}

    def build_progress(self, project_id: str, build_id: str, after: int) -> dict:
        project = self.store.load(project_id)
        build = next((item for item in project["builds"] if item["id"] == build_id), None)
        if build is None:
            raise KeyError(build_id)
        return {**{key: build[key] for key in ("id", "run_id", "status", "reason", "verification",
                                               "version", "kind", "started")},
                "activity": build["activity"][after:], "next": len(build["activity"])}

    def _view(self, project: dict) -> dict:
        return {"id": project["id"], "sheet": project["sheet"], "versions": project["versions"],
                "blockers": spec.blockers(project["sheet"]),
                "builds": [{key: build[key] for key in ("id", "status", "reason", "version", "kind", "started")}
                           for build in project["builds"]]}


def make_handler(app: App):
    get_routes = [
        (r"/api/status", lambda m, q: app.status()),
        (r"/api/examples", lambda m, q: app.examples()),
        (r"/api/projects", lambda m, q: app.store.list()),
        (r"/api/projects/(\w+)", lambda m, q: app._view(app.store.load(m[1]))),
        (r"/api/projects/(\w+)/builds/(\w+)", lambda m, q: app.build_progress(m[1], m[2], int(q.get("after", 0)))),
    ]
    post_routes = [
        (r"/api/projects", lambda m, body: app.create_project(body)),
        (r"/api/projects/(\w+)/review", lambda m, body: app.review(m[1], body)),
        (r"/api/projects/(\w+)/followup", lambda m, body: app.follow_up(m[1], body)),
        (r"/api/projects/(\w+)/build", lambda m, body: app.build(m[1])),
    ]

    class Handler(BaseHTTPRequestHandler):
        server_version = "FinancialToolBuilder"

        def log_message(self, *args) -> None:      # request bodies can hold personal figures
            pass

        def _send(self, status: int, body: bytes, content_type: str, extra: dict | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for name, value in (extra or {}).items():
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, value) -> None:
            self._send(status, json.dumps(value, ensure_ascii=False).encode(), "application/json")

        def _dispatch(self, routes, argument) -> None:
            path = self.path.split("?", 1)[0].rstrip("/") or "/"
            for pattern, handler in routes:
                match = re.fullmatch(pattern, path)
                if match:
                    try:
                        self._json(200, handler(match, argument))
                    except Problem as problem:
                        self._json(problem.status, {"error": problem.message})
                    except KeyError:
                        self._json(404, {"error": "not found"})
                    except Busy as error:
                        self._json(409, {"error": str(error)})
                    except spec.SheetError as error:
                        self._json(422, {"error": str(error)})
                    except (EngineError, GatewayError) as error:
                        # A service being down is reported as exactly that, never papered over.
                        self._json(502, {"error": str(error)})
                    return
            self._json(404, {"error": "not found"})

        def do_GET(self) -> None:
            path, _, query_string = self.path.partition("?")
            query = dict(pair.split("=", 1) for pair in query_string.split("&") if "=" in pair)
            if path in {"/", "/index.html"}:
                self._send(200, (STATIC / "index.html").read_bytes(), "text/html; charset=utf-8")
                return
            page = re.fullmatch(r"/tools/(\w+)/(\d+)\.html", path)
            if page:
                try:
                    body = app.store.page_path(page[1], int(page[2])).read_bytes()
                except (KeyError, OSError):
                    self._json(404, {"error": "not found"})
                    return
                extra = {"Content-Security-Policy": PAGE_POLICY + "; sandbox allow-scripts"}
                if query.get("download"):
                    extra = {"Content-Disposition": f'attachment; filename="financial-tool-v{page[2]}.html"'}
                self._send(200, body, "text/html; charset=utf-8", extra)
                return
            self._dispatch(get_routes, query)

        def do_POST(self) -> None:
            # Requiring JSON means another website cannot post here with a plain form.
            if "application/json" not in (self.headers.get("Content-Type") or ""):
                self._json(415, {"error": "send application/json"})
                return
            length = int(self.headers.get("Content-Length") or 0)
            if length > 2_000_000:
                self._json(413, {"error": "request too large"})
                return
            try:
                body = json.loads(self.rfile.read(length) or b"{}")
            except json.JSONDecodeError:
                self._json(400, {"error": "invalid JSON"})
                return
            self._dispatch(post_routes, body if isinstance(body, dict) else {})

    return Handler


def serve(settings: Settings | None = None) -> None:
    settings = settings or Settings.load()
    server = ThreadingHTTPServer(("127.0.0.1", settings.port), make_handler(App(settings)))
    print(f"Financial Tool Builder: http://127.0.0.1:{settings.port}")
    print(f"  engine    {settings.engine_url}")
    print(f"  gateway   {settings.gateway_url}")
    print(f"  workspace {settings.workspace}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass

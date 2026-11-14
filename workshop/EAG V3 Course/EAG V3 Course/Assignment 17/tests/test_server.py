"""The web app over real HTTP: both routes reach an agreed sheet, errors are explicit,
and a generated page is served locked down."""
import json
import shutil
import socket
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from ftb.config import Settings
from ftb.gateway import GatewayError
from ftb.server import App, make_handler
from tests.test_spec import FEE_DOCUMENT, FEE_PROPOSAL

REBALANCE_PROPOSAL = {
    "title": "Portfolio rebalancing calculator", "summary": "Trades needed to reach target weights.",
    "inputs": [{"key": "new_cash", "label": "New cash", "type": "number"},
               {"key": "holdings", "label": "Holdings", "type": "table",
                "columns": [{"key": "name", "label": "Name", "type": "text"},
                            {"key": "units", "label": "Units", "type": "number"}]}],
    "outputs": [{"key": "trades", "label": "Trades", "type": "table",
                 "columns": [{"key": "name", "label": "Name", "type": "text"}]}],
    "rules": [{"text": "Target value of a holding is total value times its target weight.", "quote": None}],
    "questions": [{"question": "May the tool sell holdings?", "why": "", "options": ["Yes", "No"]},
                  {"question": "May units be fractional?", "why": "", "options": ["Yes", "No"]}],
}


class FakeGateway:
    def __init__(self):
        self.reply, self.fail = None, False

    def json_reply(self, system, prompt):
        if self.fail:
            raise GatewayError("glc_v5 is not reachable at http://127.0.0.1:8111: connection refused")
        return self.reply


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


class WebApp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        settings = Settings(port=free_port(), engine_url=f"http://127.0.0.1:{free_port()}", engine_token="secret-token",
                            gateway_url="http://unused", gateway_provider="gemini",
                            workspace=self.tmp / "workspace", data=self.tmp / "data", run_timeout=5)
        self.gateway = FakeGateway()
        self.app = App(settings, gateway=self.gateway)
        self.server = ThreadingHTTPServer(("127.0.0.1", settings.port), make_handler(self.app))
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.base = f"http://127.0.0.1:{settings.port}"

    def call(self, path, body=None, content_type="application/json"):
        request = urllib.request.Request(self.base + path, data=None if body is None else json.dumps(body).encode(),
                                         headers={"Content-Type": content_type} if body is not None else {})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.load(response), response.headers
        except urllib.error.HTTPError as error:
            return error.code, json.load(error), error.headers

    def test_prompt_route_surfaces_the_open_assumptions_and_blocks_until_they_are_settled(self):
        self.gateway.reply = REBALANCE_PROPOSAL
        status, project, _ = self.call("/api/projects", {"route": "prompt", "request": "Rebalance my portfolio."})
        self.assertEqual(status, 200)
        self.assertIn("Unanswered: May the tool sell holdings?", project["blockers"])
        self.assertIn("Unanswered: May units be fractional?", project["blockers"])

        status, error, _ = self.call(f"/api/projects/{project['id']}/build", {})
        self.assertEqual(status, 422)
        self.assertIn("Not agreed yet", error["error"])

    def test_document_route_reaches_agreement_only_through_the_users_review(self):
        self.gateway.reply = {**FEE_PROPOSAL, "rules": FEE_PROPOSAL["rules"][:2]}
        _, project, _ = self.call("/api/projects", {"route": "document", "request": "", "document": FEE_DOCUMENT,
                                                    "cases": [{"name": "AUM 3,000,000", "input": {"aum": 3000000},
                                                               "expected": {"quarterly_fee": 6250}}]})
        sheet = project["sheet"]
        self.assertTrue(all(rule["span"] for rule in sheet["rules"]))
        self.assertTrue(project["blockers"])
        review = {"rules": [{"id": r["id"], "confirmed": True, "text": r["text"]} for r in sheet["rules"]],
                  "answers": {q["id"]: "Per quarter" for q in sheet["questions"]},
                  "examples": [{"id": e["id"], "confirmed": True} for e in sheet["examples"]]}
        status, project, _ = self.call(f"/api/projects/{project['id']}/review", review)
        self.assertEqual((status, project["blockers"]), (200, []))

    def test_with_the_engine_down_the_status_says_so_and_a_build_is_refused(self):
        _, status, _ = self.call("/api/status")
        self.assertFalse(status["engine"]["ok"])
        self.assertIn("not reachable", status["engine"]["detail"])

        self.gateway.reply = {**FEE_PROPOSAL, "rules": FEE_PROPOSAL["rules"][:2], "questions": []}
        _, project, _ = self.call("/api/projects", {"route": "document", "request": "", "document": FEE_DOCUMENT})
        sheet = project["sheet"]
        self.call(f"/api/projects/{project['id']}/review", {
            "rules": [{"id": r["id"], "confirmed": True, "text": r["text"]} for r in sheet["rules"]],
            "examples": [{"id": e["id"], "confirmed": True} for e in sheet["examples"]]})
        code, error, _ = self.call(f"/api/projects/{project['id']}/build", {})
        self.assertEqual(code, 502)
        self.assertIn("S17Code is not reachable", error["error"])
        _, after, _ = self.call(f"/api/projects/{project['id']}")
        self.assertEqual(after["builds"], [])

    def test_a_gateway_failure_is_shown_as_a_gateway_failure(self):
        self.gateway.fail = True
        code, error, _ = self.call("/api/projects", {"route": "prompt", "request": "Anything."})
        self.assertEqual(code, 502)
        self.assertIn("glc_v5 is not reachable", error["error"])

    def test_the_engine_token_never_reaches_the_browser(self):
        self.gateway.reply = REBALANCE_PROPOSAL
        _, project, _ = self.call("/api/projects", {"route": "prompt", "request": "Rebalance."})
        with urllib.request.urlopen(self.base + "/") as page:
            html = page.read().decode()
        for body in (html, json.dumps(project), json.dumps(self.call("/api/status")[1])):
            self.assertNotIn("secret-token", body)

    def test_a_generated_page_is_served_sandboxed_with_no_network_and_downloads_as_a_file(self):
        self.gateway.reply = REBALANCE_PROPOSAL
        _, project, _ = self.call("/api/projects", {"route": "prompt", "request": "Rebalance."})
        page = self.app.store.page_path(project["id"], 1)
        page.parent.mkdir(parents=True)
        page.write_text("<html><body>tool</body></html>")

        with urllib.request.urlopen(f"{self.base}/tools/{project['id']}/1.html") as response:
            policy = response.headers["Content-Security-Policy"]
        self.assertIn("default-src 'none'", policy)
        self.assertIn("sandbox allow-scripts", policy)
        self.assertNotIn("connect-src", policy)       # falls back to default-src 'none'

        with urllib.request.urlopen(f"{self.base}/tools/{project['id']}/1.html?download=1") as response:
            self.assertIn("attachment", response.headers["Content-Disposition"])
            self.assertEqual(response.read().decode(), "<html><body>tool</body></html>")

    def test_a_plain_form_post_from_another_site_is_refused(self):
        code, _, _ = self.call("/api/projects", {"route": "prompt", "request": "x"}, content_type="text/plain")
        self.assertEqual(code, 415)

    def test_a_build_left_running_by_a_restart_is_closed_with_a_reason(self):
        self.gateway.reply = REBALANCE_PROPOSAL
        _, project, _ = self.call("/api/projects", {"route": "prompt", "request": "Rebalance."})
        stored = self.app.store.load(project["id"])
        stored["builds"].append({"id": "b1", "run_id": "r", "status": "running", "reason": "", "activity": [],
                                 "verification": None, "version": None, "kind": "first build", "started": "now",
                                 "rules": []})
        self.app.store.save(stored)
        App(self.app.settings, gateway=self.gateway)          # the app starting again
        build = self.app.store.load(project["id"])["builds"][0]
        self.assertEqual(build["status"], "failed")
        self.assertIn("restarted", build["reason"])


if __name__ == "__main__":
    unittest.main()

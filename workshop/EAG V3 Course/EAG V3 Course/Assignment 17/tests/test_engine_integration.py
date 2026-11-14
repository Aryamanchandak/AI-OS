"""This app against a real S17Code server, over real HTTP.

Everything is real except the model: S17Code's planner, guard, command runner,
journal and routes, `node` running the real check, and this app's adapter and
builder. The model is replaced by a script so the run is repeatable without
keys. The script plays an agent that gets the fee tiers wrong, tries to rewrite
the expected answers, is refused, and then fixes the arithmetic.

Run with S17Code's environment:

    uv run --project S17Code python -m unittest tests.test_engine_integration -v
"""
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "S17Code"))       # the engine's checkout sits beside this app

try:
    import uvicorn
    import s17code.routes as engine_routes
    from s17code.core.memory.embeddings import DeterministicEmbedder
    HAVE_ENGINE = True
except ImportError:
    HAVE_ENGINE = False

from ftb import spec
from ftb.builds import Builder, Store
from ftb.engine import Engine, EngineError

FIXTURES = ROOT / "tests" / "fixtures"
FEE_CASES = json.loads((ROOT / "examples" / "fees" / "cases.json").read_text())["cases"]
CHECK = "node checks/check_tool.js index.html"
WRONG_LINES = ("  var rate = aum <= 1000000 ? 0.01 : (aum <= 5000000 ? 0.0075 : 0.005);\n"
               "  var annual = aum * rate;")
RIGHT_LINES = ("  var annual = Math.min(aum, 1000000) * 0.01\n"
               "             + Math.max(0, Math.min(aum, 5000000) - 1000000) * 0.0075\n"
               "             + Math.max(0, aum - 5000000) * 0.005;")


def task(node_id, capability, arguments, depends_on=()):
    return {"add": [{"id": node_id, "capability": capability, "arguments": arguments,
                     "depends_on": list(depends_on)}], "cancel": [], "finish": False, "reason": node_id}


def agent_that_repairs(nodes):
    """Wrong tiers -> red -> tries to rewrite the answers -> refused -> real fix -> green."""
    done = lambda i: nodes.get(i, {}).get("state") in {"succeeded", "failed"}  # noqa: E731
    if "write" not in nodes:
        return task("write", "create_file", {"path": "index.html", "content": (FIXTURES / "fee_wrong.html").read_text()})
    if "check_1" not in nodes:
        return task("check_1", "run_command", {"command": CHECK}, ["write"])
    if "cheat" not in nodes:
        return task("cheat", "create_file", {"path": "checks/cases.json", "content": '{"cases": []}', "overwrite": True})
    if "fix" not in nodes:
        return task("fix", "edit_code", {"path": "index.html", "old_string": WRONG_LINES, "new_string": RIGHT_LINES})
    if "check_2" not in nodes:
        return task("check_2", "run_command", {"command": CHECK}, ["fix"])
    if not done("answer"):
        return task("answer", "answer_with_evidence", {"query": "Report the result."}, ["check_2"])
    return {"add": [], "cancel": [], "finish": True, "reason": "done"}


def agent_that_never_fixes_it(nodes):
    """Writes the wrong calculator and just keeps re-running the check."""
    if "write" not in nodes:
        return task("write", "create_file", {"path": "index.html", "content": (FIXTURES / "fee_wrong.html").read_text()})
    return task(f"check_{len(nodes)}", "run_command", {"command": CHECK})


def agent_that_edits_the_previous_version(nodes):
    if "read" not in nodes:
        return task("read", "read_code", {"path": "index.html"})
    if "retitle" not in nodes:
        return task("retitle", "edit_code", {"path": "index.html", "old_string": "<h1>Advisory fee calculator</h1>",
                                             "new_string": "<h1>Advisory fee calculator (v2)</h1>"}, ["read"])
    if "check" not in nodes:
        return task("check", "run_command", {"command": CHECK}, ["retitle"])
    return task("answer", "answer_with_evidence", {"query": "Report the result."}, ["check"])


def agreed_fee_sheet() -> dict:
    sheet = spec.new_sheet("prompt", "Build the advisory fee calculator.")
    sheet = spec.adopt_proposal(sheet, {
        "title": "Advisory fee calculator", "summary": "Quarterly advisory fee from AUM.",
        "inputs": [{"key": "aum", "label": "Assets under management", "type": "number"}],
        "outputs": [{"key": "annual_fee", "label": "Annual fee", "type": "number"},
                    {"key": "quarterly_fee", "label": "Quarterly fee", "type": "number"},
                    {"key": "minimum_applied", "label": "Minimum applied", "type": "boolean"}],
        "rules": [{"text": "1.00% on the first 1,000,000; 0.75% on the next 4,000,000; 0.50% above 5,000,000. "
                           "Each rate applies only to the portion inside its tier."},
                  {"text": "Quarterly fee is a quarter of the annual fee, minimum 2,500 per quarter."}],
    })
    for case in FEE_CASES:
        spec.add_example(sheet, case["name"], case["input"], case["expected"], origin="user")
    return spec.apply_review(sheet, {
        "rules": [{"id": rule["id"], "confirmed": True} for rule in sheet["rules"]],
        "examples": [{"id": example["id"], "confirmed": True} for example in sheet["examples"]]})


@unittest.skipUnless(HAVE_ENGINE and shutil.which("node") and shutil.which("git"),
                     "needs S17Code's environment, node and git")
class AgainstARealEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(os.path.realpath(tempfile.mkdtemp()))
        cls.workspace = cls.tmp / "workspace"
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            cls.port = probe.getsockname()[1]
        cls.saved_env = dict(os.environ)
        os.environ.update({
            "S17_DATA_DIR": str(cls.tmp / "engine-state"), "S17_WORKSPACE": str(cls.workspace),
            "S17_CONTROL_TOKEN": "integration-token", "S17_ALLOWED_COMMANDS": "node",
            "S17_PROTECTED_PATHS": "checks/**,SPEC.md", "S17_MAX_REPEAT_FAILURES": "3",
            "S17_A2A_GRPC_ENABLED": "0", "S17_PORT": str(cls.port)})
        os.environ.pop("S17_SKILLS_DIR", None)
        from s17code.main import app as engine_app

        cls.script = staticmethod(agent_that_repairs)

        async def scripted_model(_app, prompt, system):
            if "evidence-readiness critic" in system:
                return {"text": json.dumps({"ready": True, "missing": [], "reason": "check is green"})}
            if "decision core" not in system:
                return {"text": "The calculator passes every confirmed example."}
            context = json.loads(prompt)
            context = context.get("original_planning_context", context)
            return {"text": json.dumps(cls.script({n["id"]: n for n in context["graph"]["nodes"]}))}

        cls.real_model = engine_routes.gateway_text_llm
        engine_routes.gateway_text_llm = scripted_model
        cls.server = uvicorn.Server(uvicorn.Config(engine_app, host="127.0.0.1", port=cls.port, log_level="error"))
        cls.thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.thread.start()
        deadline = time.time() + 30
        while not cls.server.started:
            if time.time() > deadline:
                raise RuntimeError("S17Code did not start")
            time.sleep(0.05)
        engine_app.state.runtime.memory.embedder = DeterministicEmbedder(128)

    @classmethod
    def tearDownClass(cls):
        cls.server.should_exit = True
        cls.thread.join(timeout=15)
        engine_routes.gateway_text_llm = cls.real_model
        os.environ.clear()
        os.environ.update(cls.saved_env)
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.store = Store(self.tmp / f"projects-{self.id().rsplit('.', 1)[-1]}")
        self.engine = Engine(f"http://127.0.0.1:{self.port}", "integration-token")
        self.builder = Builder(engine=self.engine, store=self.store, workspace_root=self.workspace,
                               run_timeout=120, poll_seconds=0.05)
        self.project = self.store.create(agreed_fee_sheet())

    def build(self, script) -> dict:
        type(self).script = staticmethod(script)
        started = self.builder.start(self.project["id"])
        self.builder.thread.join(timeout=120)
        self.assertFalse(self.builder.busy, "the build did not finish")
        project = self.store.load(self.project["id"])
        return next(item for item in project["builds"] if item["id"] == started["id"])

    def test_a_failed_check_then_a_refused_cheat_then_a_repair_then_a_passing_check(self):
        build = self.build(agent_that_repairs)
        for line in build["activity"]:
            print(f"    [{line['tone']:4}] {line['title']}" + (f"\n           {line['detail'][:300]}" if line["tone"] == "bad" else ""))
        self.assertEqual(build["status"], "passed", build["reason"])

        checks = [line for line in build["activity"] if line.get("check")]
        self.assertEqual([line["check"] for line in checks], ["failed", "passed"])
        self.assertIn("result.quarterly_fee: expected 6250, got 5625", checks[0]["detail"])
        self.assertIn("PASS", checks[1]["detail"])

        refused = next(line for line in build["activity"] if line["node"] == "cheat" and line["tone"] == "bad")
        self.assertIn("protected pattern", refused["detail"])

        order = [line["node"] for line in build["activity"] if line["kind"] == "task_succeeded"]
        self.assertEqual(order, ["write", "check_1", "fix", "check_2", "answer"])

        # The app's own verdict, from its own run of the check.
        self.assertTrue(build["verification"]["passed"])
        self.assertIn("examples passed: 3 of 3", build["verification"]["output"])
        page = self.store.page_path(self.project["id"], build["version"]).read_text()
        self.assertIn("Math.min(aum, 5000000) - 1000000", page)

    def test_a_run_that_never_converges_fails_with_the_engines_own_reason(self):
        build = self.build(agent_that_never_fixes_it)
        self.assertEqual(build["status"], "failed")
        self.assertIn("has failed 3 times without converging", build["reason"])
        self.assertFalse(build["verification"]["passed"])
        self.assertEqual(self.store.load(self.project["id"])["versions"], [])
        self.assertEqual([line["check"] for line in build["activity"] if line.get("check")], ["failed"] * 3)

    def test_a_follow_up_build_edits_the_previous_version_and_keeps_the_agreed_checks(self):
        self.assertEqual(self.build(agent_that_repairs)["status"], "passed")
        build = self.build(agent_that_edits_the_previous_version)
        self.assertEqual((build["status"], build["kind"], build["version"]), ("passed", "change", 2))
        second = self.store.page_path(self.project["id"], 2).read_text()
        self.assertIn("(v2)", second)
        self.assertIn("Math.min(aum, 5000000) - 1000000", second)     # the agreed arithmetic survived
        self.assertIn("examples passed: 3 of 3", build["verification"]["output"])

    def test_a_wrong_token_is_reported_not_retried_or_hidden(self):
        self.builder.engine = Engine(f"http://127.0.0.1:{self.port}", "wrong-token")
        type(self).script = staticmethod(agent_that_repairs)
        started = self.builder.start(self.project["id"])
        self.builder.thread.join(timeout=60)
        build = next(b for b in self.store.load(self.project["id"])["builds"] if b["id"] == started["id"])
        self.assertEqual(build["status"], "failed")
        self.assertIn("401", build["reason"])
        self.assertFalse(any(line["kind"].startswith("task") for line in build["activity"]))


class WithNoEngine(unittest.TestCase):
    def test_a_disconnected_engine_is_an_error_and_no_progress_is_shown(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            dead_port = probe.getsockname()[1]
        store = Store(tmp / "projects")
        project = store.create(agreed_fee_sheet())
        builder = Builder(engine=Engine(f"http://127.0.0.1:{dead_port}", "t"), store=store,
                          workspace_root=tmp / "workspace", run_timeout=5)
        with self.assertRaises(EngineError) as raised:
            builder.start(project["id"])
        self.assertIn("not reachable", str(raised.exception))
        self.assertEqual(store.load(project["id"])["builds"], [])
        self.assertFalse(builder.busy)
        self.assertFalse((tmp / "workspace").exists())


if __name__ == "__main__":
    unittest.main()

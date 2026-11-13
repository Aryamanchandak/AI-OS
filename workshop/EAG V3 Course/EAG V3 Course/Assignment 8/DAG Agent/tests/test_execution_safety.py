import json

import pytest

from agent.executor import Executor, _parse_verdict
from agent.graph import Graph, Node
from agent.skills import Skill


class Scripted:
    def __init__(self, verdicts=()):
        self.verdicts = iter(verdicts)
        self.calls = []

    def complete(self, system, user):
        self.calls.append(system)
        if system == "critic":
            return next(self.verdicts)
        return system


def skills():
    return {name: Skill(name, "llm", name, "")
            for name in ("worker", "critic", "formatter")}


def graph():
    return Graph([Node("produce", "worker", "work", critic=True,
                       critic_property="valid output"),
                  Node("answer", "formatter", "answer", ["produce"])])


@pytest.mark.parametrize("raw", ["cannot check", "", "[]", '{"verdict":"maybe"}'])
def test_invalid_critic_verdict_never_passes(raw):
    assert _parse_verdict(raw)[0] == "fail"


def test_rejected_output_cannot_reach_formatter(tmp_path):
    llm = Scripted(['{"verdict":"fail","reason":"invalid"}'])
    log = Executor(skills(), llm, tmp_path).run(graph(), "test")
    assert "formatter" not in llm.calls
    assert log.status == "failed"
    assert "invalid" in log.error


def test_recovery_is_checked_again(tmp_path):
    llm = Scripted(['{"verdict":"fail","reason":"missing data"}',
                    '{"verdict":"pass","reason":""}'])
    def repair(instruction, failed):
        return [Node("repaired", "worker", "repair")]
    log = Executor(skills(), llm, tmp_path, replan=repair).run(graph(), "test")
    assert [v["verdict"] for v in log.critic_verdicts] == ["fail", "pass"]
    assert log.status == "completed"


def test_failed_dependency_cannot_reach_formatter(tmp_path):
    g = Graph([Node("bad", "unknown", "work"),
               Node("answer", "formatter", "answer", ["bad"])])
    llm = Scripted()
    log = Executor(skills(), llm, tmp_path).run(g, "test")
    assert "formatter" not in llm.calls
    assert log.status == "failed"


def test_resume_keeps_completed_nodes_after_interrupt(tmp_path):
    from agent.state import SessionStore
    class Interrupted(Scripted):
        def complete(self, system, user):
            if system == "formatter":
                raise KeyboardInterrupt()
            return super().complete(system, user)
    g = Graph([Node("a", "worker", "work"),
               Node("answer", "formatter", "answer", ["a"])])
    store = SessionStore(tmp_path / "session")
    with pytest.raises(KeyboardInterrupt):
        Executor(skills(), Interrupted(), tmp_path, store=store).run(g, "test")
    resumed = Scripted()
    log = Executor(skills(), resumed, tmp_path, store=store).run(None, None)
    assert resumed.calls == ["formatter"]
    assert log.answer == "formatter"
    assert log.status == "completed"
    assert json.loads(store.path.read_text())["results"]["a"]["output"] == "worker"


def test_splice_is_atomic_when_replacement_is_invalid():
    g = Graph([Node("a", "worker", "work"),
               Node("b", "formatter", "answer", ["a"])])
    with pytest.raises(ValueError):
        g.splice([Node("repair", "worker", "repair", ["b"])], {"b": ["repair"]})
    assert set(g.nodes) == {"a", "b"}
    assert g.nodes["b"].depends_on == ["a"]


def test_real_process_kill_resumes_without_repeating_completed_work(tmp_path):
    import os
    from pathlib import Path
    import subprocess
    import sys
    import time
    from agent.state import SessionStore

    script = tmp_path / "interrupted.py"
    script.write_text('''import pathlib, sys, time
from agent.executor import Executor
from agent.graph import Graph, Node
from agent.skills import Skill
from agent.state import SessionStore
root = pathlib.Path(sys.argv[1])
class Model:
    def complete(self, system, user):
        if system == "formatter":
            (root / "in-flight").write_text("ready")
            time.sleep(30)
        return system
skills = {n: Skill(n, "llm", n, "") for n in ("worker", "formatter")}
graph = Graph([Node("a", "worker", "work"), Node("answer", "formatter", "answer", ["a"])])
Executor(skills, Model(), root, store=SessionStore(root / "state")).run(graph, "kill test")
''')
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
    process = subprocess.Popen([sys.executable, str(script), str(tmp_path)], env=env)
    try:
        deadline = time.monotonic() + 5
        while not (tmp_path / "in-flight").exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert (tmp_path / "in-flight").exists(), "child did not reach the interrupted node"
        process.kill()
        process.wait(timeout=5)
        resumed = Scripted()
        log = Executor(skills(), resumed, tmp_path, store=SessionStore(tmp_path / "state")).run(None, None)
        assert process.returncode < 0
        assert resumed.calls == ["formatter"]
        assert log.status == "completed"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)


def test_recovery_is_wired_to_its_final_node_whatever_order_the_planner_lists(tmp_path):
    llm = Scripted(['{"verdict":"fail","reason":"missing data"}',
                    '{"verdict":"pass","reason":""}'])
    def repair(instruction, failed):
        # The final repair step is listed FIRST.
        return [Node("final", "worker", "finish", ["first"]), Node("first", "worker", "start")]
    log = Executor(skills(), llm, tmp_path, replan=repair).run(graph(), "test")
    assert log.status == "completed"
    assert log.recoveries[0]["rewired"] == {"answer": ["final"]}
    assert log.critic_verdicts[-1] == {"node": "final", "verdict": "pass", "reason": ""}


def test_recovery_with_no_single_final_node_fails_closed(tmp_path):
    llm = Scripted(['{"verdict":"fail","reason":"missing data"}'])
    def repair(instruction, failed):
        return [Node("one", "worker", "a"), Node("two", "worker", "b")]
    log = Executor(skills(), llm, tmp_path, replan=repair).run(graph(), "test")
    assert log.status == "failed"
    assert "formatter" not in llm.calls

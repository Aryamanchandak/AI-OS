"""Executor.

Runs the graph the Planner emitted. It knows about three generic mechanisms
(llm / sandbox / tool), about layering and concurrency, and about the
Critic-between-producer-and-successor rule. It knows nothing about any
specific skill — that is the whole point.

Adding a skill should never require editing this file.
"""

from __future__ import annotations

import json
import pathlib
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from agent import recovery as recovery_mod
from agent import sandbox
from agent.graph import Graph, Node
from agent.skills import Skill
from agent.tools import REGISTRY

MAX_RECOVERIES = 2


@dataclass
class NodeResult:
    node_id: str
    skill: str
    output: str
    seconds: float
    artifacts: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.error is None


@dataclass
class RunLog:
    query: str
    layers: list[list[str]] = field(default_factory=list)
    layer_seconds: list[float] = field(default_factory=list)
    node_seconds: dict[str, float] = field(default_factory=dict)
    critic_verdicts: list[dict] = field(default_factory=list)
    recoveries: list[dict] = field(default_factory=list)
    answer: str = ""
    total_seconds: float = 0.0
    iterations: int = 0

    def to_json(self) -> str:
        return json.dumps(self.__dict__, indent=2)


class Executor:
    def __init__(self, skills: dict[str, Skill], llm, artifacts_dir: pathlib.Path,
                 replan=None, max_workers: int = 8):
        self.skills = skills
        self.llm = llm
        self.artifacts_dir = artifacts_dir
        self.replan = replan          # callable(instruction, node) -> list[Node]
        self.max_workers = max_workers

    # ---------------- generic mechanisms ----------------

    def _run_node(self, node: Node, upstream: dict[str, NodeResult]) -> NodeResult:
        started = time.perf_counter()
        skill = self.skills.get(node.skill)
        if skill is None:
            return NodeResult(node.id, node.skill, "", 0.0,
                              error=f"unknown skill {node.skill!r}")

        context = {nid: upstream[nid].output for nid in node.depends_on if nid in upstream}

        try:
            if skill.runtime == "tool":
                fn = REGISTRY[skill.tool]
                output, artifacts = fn(node.input), []

            elif skill.runtime == "llm":
                output = self.llm.complete(skill.prompt, _render(node, context))
                artifacts = []

            elif skill.runtime == "sandbox":
                response = self.llm.complete(skill.prompt, _render(node, context))
                code = sandbox.extract_code(response)
                result = sandbox.run(code, context, self.artifacts_dir)
                if not result.ok:
                    raise sandbox.SandboxError(
                        f"sandbox exited {result.returncode}: {result.stderr[:800]}")
                output, artifacts = result.stdout, result.artifacts

            else:  # unreachable — skills.py validates this
                raise ValueError(f"unknown runtime {skill.runtime!r}")

        except Exception as exc:  # noqa: BLE001 - surfaced as a node error
            return NodeResult(node.id, node.skill, "", time.perf_counter() - started,
                              error=f"{type(exc).__name__}: {exc}")

        return NodeResult(node.id, node.skill, output,
                          time.perf_counter() - started, artifacts)

    # ---------------- the Critic gate ----------------

    def _criticise(self, node: Node, result: NodeResult) -> tuple[str, str]:
        """Runs between a flagged producer and its successors."""
        critic = self.skills["critic"]
        user = (
            f"PROPERTY TO VERIFY:\n{node.critic_property}\n\n"
            f"PRODUCER SKILL: {node.skill}\n\n"
            f"PRODUCER OUTPUT:\n{result.output}\n"
        )
        raw = self.llm.complete(critic.prompt, user)
        return _parse_verdict(raw)

    # ---------------- the loop ----------------

    def run(self, graph: Graph, query: str) -> RunLog:
        log = RunLog(query=query)
        results: dict[str, NodeResult] = {}
        recoveries_used = 0
        # Nodes whose successors were rewired away from them. They are no
        # longer part of the answer, even though the graph now shows them
        # with no successors (i.e. they look terminal).
        superseded: set[str] = set()
        started = time.perf_counter()

        while True:
            log.iterations += 1
            spliced = False

            for layer in graph.layers():
                pending = [n for n in layer if n.id not in results]
                if not pending:
                    continue

                log.layers.append([n.id for n in pending])
                layer_start = time.perf_counter()

                # A layer is by construction independent -> run it concurrently.
                if len(pending) == 1:
                    layer_results = [self._run_node(pending[0], results)]
                else:
                    with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
                        layer_results = list(
                            pool.map(lambda n: self._run_node(n, results), pending))

                log.layer_seconds.append(time.perf_counter() - layer_start)
                for res in layer_results:
                    results[res.node_id] = res
                    log.node_seconds[res.node_id] = round(res.seconds, 3)

                # Critic gate for any flagged producer in this layer.
                for node in pending:
                    if not node.critic or not results[node.id].ok:
                        continue

                    verdict, reason = self._criticise(node, results[node.id])
                    log.critic_verdicts.append(
                        {"node": node.id, "verdict": verdict, "reason": reason})

                    if verdict == "pass":
                        continue

                    if recoveries_used >= MAX_RECOVERIES or self.replan is None:
                        log.recoveries.append(
                            {"node": node.id, "strategy": "escalate",
                             "note": "recovery budget exhausted"})
                        continue

                    rec = recovery_mod.classify(verdict, reason)
                    instruction = recovery_mod.recovery_instruction(rec, node.input)
                    new_nodes = self.replan(instruction, node)

                    if not new_nodes:
                        log.recoveries.append(
                            {"node": node.id, "strategy": rec.strategy.value,
                             "note": "planner returned no recovery nodes"})
                        continue

                    # Splice: successors of the failed node now depend on the
                    # tail of the recovery chain instead of the failed node.
                    tail = new_nodes[-1].id
                    rewire = {s.id: [tail if d == node.id else d for d in s.depends_on]
                              for s in graph.successors(node.id)}
                    graph.splice(new_nodes, rewire)

                    log.recoveries.append({
                        "node": node.id,
                        "strategy": rec.strategy.value,
                        "reason": rec.reason,
                        "spliced": [n.id for n in new_nodes],
                        "rewired": rewire,
                    })
                    superseded.add(node.id)
                    recoveries_used += 1
                    spliced = True
                    break

                if spliced:
                    break

            if not spliced:
                break

        log.total_seconds = round(time.perf_counter() - started, 3)
        log.answer = _final_answer(graph, results, superseded)
        return log


def _render(node: Node, context: dict[str, str]) -> str:
    parts = [f"TASK:\n{node.input}"]
    if context:
        parts.append("UPSTREAM NODE OUTPUTS (JSON keys are node ids):")
        parts.append(json.dumps(context, indent=2))
    return "\n\n".join(parts)


def _parse_verdict(raw: str) -> tuple[str, str]:
    """Critic returns JSON; fall back to a text scan if it wanders."""
    try:
        start, end = raw.index("{"), raw.rindex("}") + 1
        data = json.loads(raw[start:end])
        verdict = str(data.get("verdict", "")).strip().lower()
        if verdict in {"pass", "fail"}:
            return verdict, str(data.get("reason", "")).strip()
    except (ValueError, json.JSONDecodeError):
        pass

    lowered = raw.lower()
    if "fail" in lowered:
        return "fail", raw.strip()[:500]
    return "pass", raw.strip()[:500]


def _final_answer(graph: Graph, results: dict[str, NodeResult],
                  superseded: set[str] | None = None) -> str:
    """The answer is the output of the terminal node(s).

    A node replaced by a recovery splice has no successors any more, so it
    looks terminal — exclude it, or the failed output leaks into the answer.
    """
    superseded = superseded or set()
    terminals = [n for n in graph.nodes.values()
                 if not graph.successors(n.id) and n.id not in superseded]
    chunks = []
    for node in terminals:
        res = results.get(node.id)
        if res is None:
            continue
        chunks.append(res.output if res.ok else f"[{node.id} failed: {res.error}]")
    return "\n\n".join(c for c in chunks if c)

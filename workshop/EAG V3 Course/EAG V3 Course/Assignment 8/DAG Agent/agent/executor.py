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
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field

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
    status: str = "running"
    error: str = ""
    planning_seconds: float = 0.0
    resumed: bool = False
    reused_nodes: list[str] = field(default_factory=list)

    def to_json(self) -> str:
        return json.dumps(self.__dict__, indent=2)


class Executor:
    def __init__(self, skills: dict[str, Skill], llm, artifacts_dir: pathlib.Path,
                 replan=None, max_workers: int = 8, store=None, on_node=None,
                 initial_results=None, code_approval=None):
        self.skills = skills
        self.llm = llm
        self.artifacts_dir = artifacts_dir
        self.replan = replan          # callable(instruction, node) -> list[Node]
        self.max_workers = max_workers
        self.store = store
        self.on_node = on_node
        self.initial_results = initial_results or {}
        self.code_approval = code_approval

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
                output = fn(node.input, context) if skill.context else fn(node.input)
                artifacts = []

            elif skill.runtime == "llm":
                output = self.llm.complete(skill.prompt, _render(node, context))
                artifacts = []

            elif skill.runtime == "sandbox":
                response = self.llm.complete(skill.prompt, _render(node, context))
                code = sandbox.extract_code(response)
                if self.code_approval is not None and not self.code_approval(node, code):
                    raise sandbox.SandboxError("Generated code was not approved for execution")
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

    def run(self, graph: Graph | None, query: str | None, stop_after=None) -> RunLog:
        saved = self.store.load() if self.store else None
        if saved:
            if query is not None and query != saved["query"]:
                raise ValueError("Checkpoint belongs to a different query")
            graph = Graph([Node.from_dict(n) for n in saved["nodes"]])
            query = saved["query"]
        if graph is None or query is None:
            raise ValueError("A graph and query are required for a new run")
        graph.layers()
        log = RunLog(query=query)
        results = {nid: NodeResult(**value) for nid, value in
                   (saved or {}).get("results", {}).items()}
        if not saved:
            results.update(self.initial_results)
            log.reused_nodes = sorted(self.initial_results)
        checked = set((saved or {}).get("checked", []))
        recoveries_used = (saved or {}).get("recoveries_used", 0)
        # Nodes whose successors were rewired away from them. They are no
        # longer part of the answer, even though the graph now shows them
        # with no successors (i.e. they look terminal).
        superseded = set((saved or {}).get("superseded", []))
        if saved:
            log = RunLog(**saved["log"])
            log.resumed = True
            if log.status in {"completed", "failed"}:
                return log
        log.status = "running"
        prior_seconds = log.total_seconds
        started = time.perf_counter()
        new_results = 0

        def checkpoint():
            log.total_seconds = round(prior_seconds + time.perf_counter() - started, 4)
            if self.store:
                self.store.save({"query": query,
                                 "nodes": [asdict(n) for n in graph.nodes.values()],
                                 "results": {nid: asdict(r) for nid, r in results.items()},
                                 "checked": sorted(checked),
                                 "superseded": sorted(superseded),
                                 "recoveries_used": recoveries_used,
                                 "log": asdict(log)})

        def failed(message):
            log.status, log.error = "failed", message
            log.answer = "Unable to complete: " + message
            checkpoint()
            return log

        def accept(res):
            results[res.node_id] = res
            log.node_seconds[res.node_id] = round(res.seconds, 4)
            log.layer_seconds[-1] = time.perf_counter() - layer_start
            checkpoint()
            if self.on_node:
                self.on_node(res)

        checkpoint()

        while True:
            log.iterations += 1
            spliced = False

            for layer in graph.layers():
                pending = [n for n in layer if n.id not in results]
                if pending:
                    log.layers.append([n.id for n in pending])
                    log.layer_seconds.append(0.0)
                    layer_start = time.perf_counter()
                    if len(pending) == 1:
                        accept(self._run_node(pending[0], results))
                    else:
                        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
                            futures = [pool.submit(self._run_node, n, dict(results))
                                       for n in pending]
                            for future in as_completed(futures):
                                accept(future.result())
                    log.layer_seconds[-1] = time.perf_counter() - layer_start
                    new_results += len(pending)
                    checkpoint()

                for node in layer:
                    if not results[node.id].ok:
                        return failed(f"{node.id}: {results[node.id].error}")
                if stop_after and new_results >= stop_after:
                    log.status = "paused"
                    checkpoint()
                    return log

                # Critic gate for any flagged producer in this layer.
                for node in layer:
                    if not node.critic or node.id in checked or node.id in superseded:
                        continue
                    try:
                        verdict, reason = self._criticise(node, results[node.id])
                    except Exception as exc:
                        return failed(f"Critic unavailable for {node.id}: {type(exc).__name__}")
                    log.critic_verdicts.append(
                        {"node": node.id, "verdict": verdict, "reason": reason})

                    if verdict == "pass":
                        checked.add(node.id)
                        checkpoint()
                        continue

                    if recoveries_used >= MAX_RECOVERIES or self.replan is None:
                        log.recoveries.append(
                            {"node": node.id, "strategy": "escalate",
                             "note": "recovery budget exhausted"})
                        return failed(f"Critic rejected {node.id}: {reason}; recovery unavailable")

                    rec = recovery_mod.classify(verdict, reason)
                    instruction = recovery_mod.recovery_instruction(rec, node.input)
                    try:
                        new_nodes = self.replan(instruction, node)
                    except Exception as exc:
                        return failed(f"Recovery planning failed: {type(exc).__name__}")

                    if not new_nodes:
                        log.recoveries.append(
                            {"node": node.id, "strategy": rec.strategy.value,
                             "note": "planner returned no recovery nodes"})
                        return failed(f"Critic rejected {node.id}: {reason}; no repair returned")

                    # Splice: successors of the failed node now depend on the
                    # tail of the recovery chain instead of the failed node.
                    # The tail is the one node nothing else in the chain feeds,
                    # whatever order the Planner listed them in.
                    tails = [n for n in new_nodes
                             if not any(n.id in other.depends_on for other in new_nodes)]
                    if len(tails) != 1:
                        return failed("Invalid recovery graph: repair must end in exactly one node")
                    tail = tails[0].id
                    tails[0].critic = True
                    tails[0].critic_property = node.critic_property
                    rewire = {s.id: [tail if d == node.id else d for d in s.depends_on]
                              for s in graph.successors(node.id)}
                    try:
                        graph.splice(new_nodes, rewire)
                    except (ValueError, KeyError) as exc:
                        return failed(f"Invalid recovery graph: {exc}")

                    log.recoveries.append({
                        "node": node.id,
                        "strategy": rec.strategy.value,
                        "reason": rec.reason,
                        "spliced": [n.id for n in new_nodes],
                        "rewired": rewire,
                    })
                    superseded.add(node.id)
                    recoveries_used += 1
                    checkpoint()
                    spliced = True
                    break

                if spliced:
                    break

            if not spliced:
                break

        log.status = "completed"
        log.answer = _final_answer(graph, results, superseded)
        checkpoint()
        return log


def _render(node: Node, context: dict[str, str]) -> str:
    parts = [f"TASK:\n{node.input}"]
    if context:
        parts.append("UPSTREAM NODE OUTPUTS (JSON keys are node ids):")
        parts.append(json.dumps(context, indent=2))
    return "\n\n".join(parts)


def _parse_verdict(raw: str) -> tuple[str, str]:
    """Only an explicit, well-formed verdict can open the gate."""
    try:
        start, end = raw.index("{"), raw.rindex("}") + 1
        data = json.loads(raw[start:end])
        if not isinstance(data, dict):
            return "fail", "malformed Critic verdict"
        verdict = str(data.get("verdict", "")).strip().lower()
        if verdict in {"pass", "fail"}:
            return verdict, str(data.get("reason", "")).strip()
    except (ValueError, json.JSONDecodeError):
        pass

    return "fail", "malformed Critic verdict; no valid pass/fail JSON"


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

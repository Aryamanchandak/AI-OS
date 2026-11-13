"""Planner — emits the graph, and re-plans on a Critic failure."""

from __future__ import annotations

import json
import itertools
import uuid

from agent.graph import Graph, Node
from agent.skills import Skill, catalogue_text

_recovery_ids = itertools.count(1)


class Planner:
    def __init__(self, skills: dict[str, Skill], llm):
        self.skills = skills
        self.llm = llm
        self.catalogue = catalogue_text(skills)

    def plan(self, query: str) -> Graph:
        prompt = self.skills["planner"].prompt.replace("{{CATALOGUE}}", self.catalogue)
        raw = self.llm.complete(prompt, f"USER QUERY:\n{query}")
        return Graph([Node.from_dict(d) for d in _parse_nodes(raw)])

    def comparison_plan(self, request: dict, live: bool = False, artifacts_dir=None) -> Graph:
        """Emit one branch per option from the validated comparison contract."""
        nodes, inputs = [], []
        for option in request["options"]:
            read = "read_" + option["id"]
            nodes.append(Node(read, "evidence_reader", json.dumps(option)))
            inputs.append(read)
            if live:
                extract = "extract_" + option["id"]
                task = {"option": option["id"], "criteria": request["criteria"],
                        "question": request["question"]}
                nodes.append(Node(extract, "evidence_extractor", json.dumps(task), [read]))
                inputs.append(extract)
        nodes.append(Node("comparison", "comparison_aligner", json.dumps(request), inputs))
        answer_inputs = ["comparison"]
        if live:
            nodes.append(Node("interpretation", "comparison_interpreter",
                              "Explain the trade-offs for the user's stated purpose.", ["comparison"]))
            answer_inputs.append("interpretation")
        if request.get("chart"):
            nodes.append(Node("chart", "comparison_chart", json.dumps({"criterion": request["chart"],
                              "directory": str(artifacts_dir)}), ["comparison"]))
            answer_inputs.append("chart")
        nodes.append(Node("answer", "comparison_reporter", "Render the verified comparison", answer_inputs))
        return Graph(nodes)

    def replan(self, instruction: str, failed_node: Node) -> list[Node]:
        """Produce a small recovery chain to splice in place of a failed node."""
        prompt = self.skills["planner"].prompt.replace("{{CATALOGUE}}", self.catalogue)
        user = (
            "You are producing a RECOVERY SUBGRAPH, not a full plan.\n"
            "Emit the smallest chain of nodes that repairs the failure below.\n"
            f"The failed node was {failed_node.id!r} (skill: {failed_node.skill}).\n"
            "Its dependencies were: "
            f"{json.dumps(failed_node.depends_on)}\n\n{instruction}"
        )
        raw = self.llm.complete(prompt, user)

        raw_nodes = _parse_nodes(raw)
        prefix = f"r{next(_recovery_ids)}_{uuid.uuid4().hex[:8]}_"

        # Namespace every recovery id so repeated recoveries never collide with
        # each other or with the original plan.
        rename = {d["id"]: prefix + d["id"] for d in raw_nodes}

        nodes = []
        for d in raw_nodes:
            deps = []
            for dep in d.get("depends_on", []):
                if dep == failed_node.id:
                    continue          # the failed node is being replaced
                deps.append(rename.get(dep, dep))  # unknown dep = external, keep
            nodes.append(Node(
                id=rename[d["id"]],
                skill=d["skill"],
                input=d.get("input", ""),
                depends_on=deps,
                critic=False,          # recovery nodes are not re-gated
            ))
        return nodes


def _parse_nodes(raw: str) -> list[dict]:
    try:
        start, end = raw.index("{"), raw.rindex("}") + 1
        data = json.loads(raw[start:end])
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"planner did not emit parseable JSON: {exc}\n---\n{raw[:1000]}")

    nodes = data.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        raise ValueError(f"planner emitted no nodes: {raw[:500]}")
    return nodes

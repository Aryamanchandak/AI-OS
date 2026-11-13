"""Research and recall skills using S15's durable graph, budget and trace adapters."""
import json
import uuid
from pathlib import Path

from s15code.core.live_graph import GraphPatch, LiveGraphExecutor, TaskSpec
from s15code.economics import BudgetedGateway, EconomicsConfig, call_site
from s15code.telemetry import export_run

from .models import Brief, Cards, Grade, GradeRequest, LearningRequest, ResearchRequest
from .sources import retrieve, verify_citations

SYSTEM = (Path(__file__).parent / "prompts/grounded.md").read_text(encoding="utf-8")


class ResearchAssistant:
    def __init__(self, graph, config=None):
        self.graph = graph
        self.config = config or EconomicsConfig.load()

    async def research(self, body: ResearchRequest, transport):
        evidence = retrieve(body.question, body.documents)
        tier = (self.config.ladder.most_capable if body.strategy == "frontier"
                else self.config.ladder.for_role("research_brief"))
        return await self._run("research", body.question, evidence, Brief, body.budget, tier.name, transport)

    async def cards(self, body: LearningRequest, transport):
        parent = self.read(body.research_run_id)
        if parent["status"] != "completed" or parent["kind"] != "research":
            raise ValueError("study cards require a completed research brief")
        return await self._run("cards", "Make 3 to 6 study cards about: " + parent["question"],
            parent["evidence"], Cards, body.budget, self.config.ladder.for_role("study_cards").name,
            transport, parent_id=body.research_run_id)

    async def grade(self, body: GradeRequest, transport):
        parent = self.read(body.cards_run_id)
        if parent["status"] != "completed" or parent["kind"] != "cards":
            raise ValueError("grading requires a completed study-card run")
        cards = parent["output"]["cards"]
        if body.card_index >= len(cards):
            raise ValueError("card index does not exist")
        return await self._run("grade", "Grade this recall answer", parent["evidence"], Grade,
            body.budget, self.config.ladder.for_role("recall_grader").name, transport,
            extra={"card": cards[body.card_index], "recall_answer": body.answer}, parent_id=body.cards_run_id)

    async def _run(self, kind, question, evidence, schema, amount, tier, transport, extra=None, parent_id=None):
        run_id = uuid.uuid4().hex
        budget = self.config.budget(principal="local/research-desk", amount=amount, run_id=run_id)
        controller = BudgetedGateway(transport, budget=budget, policy=self.config.policy(),
                                    pricing=self.config.pricing, ladder=self.config.ladder)
        context = {"kind": kind, "question": question, "parent_id": parent_id}
        self.graph.start(run_id, context=context)
        graph = self.graph

        class Planner:
            async def plan(self, snapshot, event):
                if event.kind == "run_started":
                    return GraphPatch(add=(TaskSpec("evidence", "select_sources"),), reason="select local passages")
                if event.kind == "task_failed":
                    return GraphPatch(finish=True, reason="failure retained; no automatic paid retry")
                if event.node_id == "evidence":
                    return GraphPatch(add=(TaskSpec("generate", "generate", metadata={"tier": tier}),),
                                      connect=(("evidence", "generate"),), reason="source passages ready")
                if event.node_id == "generate":
                    return GraphPatch(add=(TaskSpec("validate", "validate"),),
                                      connect=(("generate", "validate"),), reason="check output schema and source quotes")
                return GraphPatch(finish=True, reason="source-backed output validated")

        async def select_sources(task):
            if not evidence:
                raise ValueError("documents contain no readable passages")
            return {"evidence": evidence}

        async def generate(task):
            payload = {"task": kind, "question": question, "evidence": evidence,
                       "schema": schema.model_json_schema(), **(extra or {})}
            with call_site(task.id, kind, tier) as site:
                result = await controller.complete(json.dumps(payload), SYSTEM,
                                                   request={"session": run_id, "agent": "research_desk"})
            # Keep the charged reply before validation, including malformed replies.
            return {**result, **site.result_fields()}

        async def validate(task):
            raw = graph.snapshot(run_id).nodes["generate"]["result"]["text"].strip()
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            output = schema.model_validate_json(raw).model_dump()
            verify_citations(output, evidence)
            return {"output": output, "budget": budget.snapshot()}

        await LiveGraphExecutor(graph, Planner(), {"select_sources": select_sources,
            "generate": generate, "validate": validate}, max_workers=1).run(run_id)
        # Persist final accounting even when generation refused or validation failed.
        snapshot = graph.snapshot(run_id)
        failures = [n["result"] for n in snapshot.nodes.values() if n["state"] == "failed"]
        self.graph.db.execute("UPDATE runs SET context_json=? WHERE id=?",
            (json.dumps({**context, "budget": budget.snapshot(), "error": failures[0]["error"] if failures else None}),
             run_id))
        self.graph.db.commit()
        return self.read(run_id)

    def read(self, run_id):
        context = self.graph.context(run_id)
        if context.get("kind") not in {"research", "cards", "grade"}:
            raise ValueError("not a research-desk run")
        snapshot = self.graph.snapshot(run_id)
        events = [e.__dict__ for e in self.graph.events(run_id)]
        output = (snapshot.nodes.get("validate", {}).get("result") or {}).get("output")
        budget = context.get("budget", {})
        journal = {"run_id": run_id, "finished": snapshot.finished, "nodes": snapshot.nodes,
                   "edges": snapshot.edges, "events": events}
        trace = context.get("trace")
        if trace is None:
            trace = export_run(journal, budget=budget).as_dict()
            trace["trace_id"] = next((s["trace_id"] for s in trace["spans"]), None)
            self.graph.db.execute("UPDATE runs SET context_json=? WHERE id=?",
                                  (json.dumps({**context, "trace": trace}), run_id))
            self.graph.db.commit()
        return {"run_id": run_id, "kind": context["kind"], "question": context["question"],
                "parent_id": context.get("parent_id"),
                "status": "completed" if output else "refused" if budget.get("refusals") else "failed",
                "output": output, "error": context.get("error"), "budget": budget,
                "evidence": (snapshot.nodes.get("evidence", {}).get("result") or {}).get("evidence", []),
                "events": events, "trace": trace}

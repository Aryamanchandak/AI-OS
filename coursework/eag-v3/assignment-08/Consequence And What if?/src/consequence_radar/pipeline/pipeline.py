from __future__ import annotations

import json
import uuid
from collections.abc import Callable

from ..cases import select_cases
from ..challenge import adjudicate, challenge, whole_graph_review
from ..config import Settings
from ..graph import GraphPatch, apply_patch, build_initial_graph, validate_graph
from ..ingest import normalize_batch, pre_read
from ..deduplicate import deduplicate
from ..metering import UsageLedger
from ..models import GraphRevision, NewsBatch, RunStatus
from ..providers.fetch import PageFetcher
from ..providers.model import GeminiModelClient, ModelClient
from ..providers.search import GeminiGoogleSearchProvider, SearchProvider
from ..report import write_report
from ..report_context import compile_context
from ..research import extract_claims, generate_tasks, retrieve_for_tasks
from ..select import select_candidate
from ..storage import Repository

Progress = Callable[[str, str], None]


class Pipeline:
    def __init__(self, settings: Settings, repository: Repository, *, model: ModelClient | None = None, search: SearchProvider | None = None, fetcher: PageFetcher | None = None):
        self.settings, self.repo = settings, repository
        self.ledger = UsageLedger(settings.max_model_calls_per_run, settings.max_wall_time_seconds, settings.max_search_queries_per_run)
        self.model = model or GeminiModelClient(settings, self.ledger, on_call=self._record_model_call)
        self.search = search or GeminiGoogleSearchProvider(settings, self.ledger, on_call=self._record_model_call, run_id_getter=lambda: self._active_run_id)
        self.fetcher = fetcher or PageFetcher(settings)
        self._active_run_id: str | None = None
        self._last_model_call_id: str | None = None

    def _record_model_call(self, record):
        if self._active_run_id:
            self._last_model_call_id = "M" + uuid.uuid4().hex[:10]
            self.repo.save_artifact(self._active_run_id, "model_call", {"id": self._last_model_call_id, **record})

    def _save_revision(self, run_id, before, after, patch, *, repair=False):
        revision = GraphRevision(id="R" + uuid.uuid4().hex[:10], run_id=run_id, model_call_id=self._last_model_call_id, reason=patch.reason, evidence_ids=patch.evidence_ids, before_version=before.version, after_version=after.version, operations=patch.operations)
        self.repo.save_artifact(run_id, "graph_revision", {**revision.model_dump(mode="json"), "repair": repair})

    def _stage(self, run_id: str, status: RunStatus, message: str, progress: Progress):
        self.ledger.guard_time(); self.repo.set_status(run_id, status); self.repo.add_event(run_id, str(status), message); progress(str(status), message)

    def run(self, run_id: str, progress: Progress = lambda *_: None) -> None:
        self._active_run_id = run_id
        run = self.repo.get_run(run_id)
        if not run: raise KeyError(run_id)
        try:
            batch = normalize_batch(NewsBatch.model_validate(run["batch"]))
            self.repo.save_artifact(run_id, "normalized_batch", batch)
            self._stage(run_id, RunStatus.PRE_READING, "Normalising and pre-reading supplied news", progress)
            extracts = pre_read(batch, self.fetcher, guard=self.ledger.guard_time); self.repo.save_artifact(run_id, "discovery_extracts", extracts)
            groups = deduplicate(extracts); self.repo.save_artifact(run_id, "dedup_groups", groups)
            self._stage(run_id, RunStatus.SELECTING, "Ranking grounded research seeds", progress)
            candidates = select_candidate(run_id, extracts, groups, self.model); self.repo.save_artifact(run_id, "candidates", candidates)
            seed = next(c for c in candidates if c.selected)
            self._stage(run_id, RunStatus.BUILDING_GRAPH, "Building the initial causal graph", progress)
            graph = build_initial_graph(run_id, seed, self.model, self.settings); self.repo.save_artifact(run_id, "graph", graph, version=graph.version)
            all_sources, all_claims, rejected_claims, failures, gaps = [], [], [], [], []
            counters = {"queries": 0, "sources": 0}
            self._stage(run_id, RunStatus.RESEARCHING, "Testing graph gaps against evidence", progress)
            for cycle in range(1, self.settings.max_research_cycles + 1):
                tasks = generate_tasks(run_id, graph, self.model, self.settings)
                if not tasks: break
                self.repo.save_artifact(run_id, "research_tasks", tasks, key=f"cycle-{cycle}")
                sources, cycle_failures = retrieve_for_tasks(tasks, self.search, self.fetcher, self.settings, counters, guard=self.ledger.guard_time)
                failures.extend(cycle_failures); all_sources.extend(sources)
                claims, rejected = extract_claims(run_id, tasks, sources, self.model, len(all_claims) + 1)
                completed_tasks = [task.model_copy(update={"status": "complete" if claims else ("failed" if cycle_failures else "not_found")}) for task in tasks]
                self.repo.save_artifact(run_id, "research_tasks", completed_tasks, key=f"cycle-{cycle}")
                all_claims.extend(claims); rejected_claims.extend(rejected)
                self.repo.save_artifact(run_id, "sources", sources, key=f"cycle-{cycle}")
                self.repo.save_artifact(run_id, "accepted_claims", claims, key=f"cycle-{cycle}")
                self.repo.save_artifact(run_id, "rejected_claims", rejected, key=f"cycle-{cycle}")
                patch = self.model.generate(run_id=run_id, stage="graph_patch", prompt_name="graph/graph_patcher.md", prompt_data=json.dumps({"graph": graph.model_dump(mode="json"), "tasks": [t.model_dump(mode="json") for t in tasks], "claims": [c.model_dump(mode="json") for c in claims]}), schema=GraphPatch, model_tier="reasoning")
                applied_patch = patch
                try:
                    revised = apply_patch(graph, patch, self.settings)
                    self._save_revision(run_id, graph, revised, patch)
                    graph = revised; self.repo.save_artifact(run_id, "graph", graph, version=graph.version)
                except Exception as exc:
                    self.repo.save_artifact(run_id, "invalid_graph_patch", {"patch": patch.model_dump(mode="json"), "error": str(exc)})
                    repair = self.model.generate(run_id=run_id, stage="graph_patch_repair", prompt_name="graph/graph_patcher.md", prompt_data=json.dumps({"graph": graph.model_dump(mode="json"), "rejected_patch": patch.model_dump(mode="json"), "validation_errors": getattr(exc, "problems", [str(exc)]), "claims": [c.model_dump(mode="json") for c in claims]}), schema=GraphPatch, model_tier="reasoning", retry_count=1)
                    try:
                        revised = apply_patch(graph, repair, self.settings)
                        self._save_revision(run_id, graph, revised, repair, repair=True)
                        graph = revised; self.repo.save_artifact(run_id, "graph", graph, version=graph.version)
                        applied_patch = repair
                    except Exception as repair_exc:
                        self.repo.save_artifact(run_id, "invalid_graph_patch", {"patch": repair.model_dump(mode="json"), "error": str(repair_exc)}, key=f"cycle-{cycle}-repair")
                gaps = applied_patch.remaining_gaps
                if not gaps: break
            self._stage(run_id, RunStatus.QUANTIFYING, "Checking concrete Indian-equity endpoints and estimates", progress)
            endpoint_errors = validate_graph(graph, self.settings, require_indian_path=True, claim_ids={c.id for c in all_claims})
            if any("no quantified or directional estimate" in error for error in endpoint_errors):
                quant_patch = self.model.generate(run_id=run_id, stage="quantification_patch", prompt_name="graph/graph_patcher.md", prompt_data=json.dumps({"instruction":"For every material Indian-equity terminal, add a sourced/derived estimate or an explicit directional_only estimate with the missing-data caveat. Do not invent numbers.","graph":graph.model_dump(mode="json"),"claims":[c.model_dump(mode="json") for c in all_claims]}), schema=GraphPatch, model_tier="reasoning")
                graph = apply_patch(graph, quant_patch, self.settings)
                self._save_revision(run_id, graph.model_copy(update={"version": graph.version - 1}), graph, quant_patch)
                self.repo.save_artifact(run_id, "graph", graph, version=graph.version)
                endpoint_errors = validate_graph(graph, self.settings, require_indian_path=True, claim_ids={c.id for c in all_claims})
            if endpoint_errors: raise ValueError("; ".join(endpoint_errors))
            review_patch = whole_graph_review(run_id, graph, all_claims, self.model)
            if review_patch.operations:
                before = graph; graph = apply_patch(graph, review_patch, self.settings, require_indian_path=True); self._save_revision(run_id, before, graph, review_patch); self.repo.save_artifact(run_id, "graph", graph, version=graph.version)
            self._stage(run_id, RunStatus.CHALLENGING, "Attempting to disprove the complete hypothesis", progress)
            findings = challenge(run_id, graph, all_claims, failures, self.model); self.repo.save_artifact(run_id, "challenge", findings)
            self._stage(run_id, RunStatus.ADJUDICATING, "Adjudicating challenge findings once", progress)
            before_adjudication = graph
            graph, decisions = adjudicate(run_id, graph, findings, all_claims, self.model, self.settings)
            if graph.version != before_adjudication.version:
                accepted_operations = [op for decision in decisions.decisions if decision.decision.startswith("accept_") for op in decision.operations]
                adjudication_patch = GraphPatch(operations=accepted_operations, reason="Accepted challenger findings", evidence_ids=sorted({cid for finding in findings.findings for cid in finding.claim_ids}))
                self._save_revision(run_id, before_adjudication, graph, adjudication_patch)
            final_errors = validate_graph(graph, self.settings, require_indian_path=True, claim_ids={c.id for c in all_claims})
            if final_errors: raise ValueError("; ".join(final_errors))
            self.repo.save_artifact(run_id, "adjudication", decisions)
            if self.repo.artifact(run_id, "graph", version=graph.version) is None:
                self.repo.save_artifact(run_id, "graph", graph, version=graph.version)
            cases = select_cases(run_id, graph, all_claims, self.model); self.repo.save_artifact(run_id, "cases", cases)
            self._stage(run_id, RunStatus.COMPILING_CONTEXT, "Compiling canonical accepted context", progress)
            context = compile_context(seed=seed, graph=graph, cases=cases, claims=all_claims, sources=all_sources, findings=findings.findings, decisions=decisions.decisions, gaps=gaps, failures=failures, token_budget=self.settings.report_context_token_budget)
            self.repo.save_artifact(run_id, "report_context", context)
            self._stage(run_id, RunStatus.WRITING_REPORT, "Writing the newsletter article in one call", progress)
            report, errors = write_report(run_id, context, self.model, self.settings.report_min_words, self.settings.report_max_words)
            self.repo.save_artifact(run_id, "report_draft" if errors else "report", report)
            self.repo.save_artifact(run_id, "report_validation", {"valid": not errors, "errors": errors})
            self.repo.save_artifact(run_id, "usage", self.ledger.snapshot().__dict__)
            if errors:
                self.repo.set_status(run_id, RunStatus.REPORT_VALIDATION_FAILED, error="; ".join(errors)); self.repo.add_event(run_id, "report_validation_failed", "; ".join(errors), "error")
            else:
                status = RunStatus.COMPLETED_WITH_WARNINGS if failures or rejected_claims else RunStatus.COMPLETED
                self.repo.set_status(run_id, status); self.repo.add_event(run_id, str(status), "Run completed", "complete")
        except Exception as exc:
            self.repo.save_artifact(run_id, "usage", self.ledger.snapshot().__dict__)
            self.repo.set_status(run_id, RunStatus.FAILED, error=str(exc)); self.repo.add_event(run_id, "failed", str(exc), "error")
        finally:
            self._active_run_id = None

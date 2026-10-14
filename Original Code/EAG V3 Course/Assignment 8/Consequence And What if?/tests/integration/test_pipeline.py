from datetime import datetime, timezone

from consequence_radar.models import *
from consequence_radar.pipeline import Pipeline
from consequence_radar.providers.fetch import FetchResult
from consequence_radar.providers.search import SearchResult
from consequence_radar.storage import Repository
from consequence_radar.ingest import stable_item_id

DIMENSIONS = {k:"high" for k in SELECTION_DIMENSIONS}
ITEM_ID = stable_item_id("https://news.test/item")


def fixture_graph():
    return CausalGraph(version=1, nodes=[
        CausalNode(id="N0", label="Solar duty cut announced", node_type="news_seed", description="Supplied announcement", geography="India"),
        CausalNode(id="N1", label="Imported module cost", node_type="intermediate", description="Landed module costs", geography="India", time_horizon="6 months"),
        CausalNode(id="N2", label="Indian developer project EBITDA", node_type="company_metric", description="Project EBITDA for Indian listed developers", geography="India", entity_ids=["NSE:NTPC"], time_horizon="12 months"),
    ], edges=[
        CausalEdge(id="E1", src="N0", dst="N1", mechanism="A lower duty reduces the landed cost of imported modules.", direction="negative", strength="medium", confidence="medium", status="proposed"),
        CausalEdge(id="E2", src="N1", dst="N2", mechanism="Lower module cost raises project EBITDA before tariff repricing.", direction="negative", strength="medium", confidence="medium", assumption_ids=["A1"], estimate_ids=["Q1"], status="assumption_only"),
    ], assumptions=[Assumption(id="A1", statement="Developers retain some procurement savings", required_for_edge_ids=["E2"], basis="Contract timing", likelihood="possible", likelihood_basis="inferred", if_false_effect="Savings pass through to buyers", material=True)], estimates=[Estimate(id="Q1", metric="Project EBITDA implication", estimate_type="directional_only", caveat="No comparable exposure coefficient was verified")])


def case():
    return Case(id="K1", name="Procurement relief", path_node_ids=["N0","N1","N2"], path_edge_ids=["E1","E2"], required_assumption_ids=["A1"], supporting_claim_ids=["C1"], contradicting_claim_ids=[], equity_implication_direction="positive", estimate_ids=["Q1"], quantification_status="directional_only", time_horizon="12 months", weakening_observation="Developers pass through all savings", central=True)


class FakeSearch:
    def search(self, query, *, max_results): return [SearchResult("https://evidence.test/official", "Official notice")]


class FakeFetcher:
    def fetch(self, url):
        text = "The government announced a reduction in the solar module import duty. The measure takes effect next month. " * 8
        return FetchResult(url, url, "Official solar duty notice", text, "text/html", datetime.now(timezone.utc))

class PartialFetcher(FakeFetcher):
    def fetch(self,url):
        if "failed" in url: raise TimeoutError("fixture timeout")
        return super().fetch(url)

class PartialSearch:
    def search(self,query,*,max_results): return [SearchResult("https://evidence.test/official","Official"),SearchResult("https://failed.test/page","Failed")]


class ScriptedModel:
    def __init__(self, *, bad_report=False, invalid_first_graph=False, counter_remove=False):
        self.bad_report=bad_report; self.invalid_first_graph=invalid_first_graph; self.counter_remove=counter_remove; self.calls=[]
    def generate(self, *, run_id, stage, prompt_name, prompt_data, schema, model_tier="fast", retry_count=0):
        self.calls.append(stage)
        if stage == "candidate_selection": return CandidateSelection(candidates=[CandidateSeed(id="X1", source_item_ids=[ITEM_ID], reported_premise="India announced a solar module duty cut", factual_status="announcement", possible_immediate_effect="Imported module landed costs decline", possible_indian_equity_route="Listed Indian developers may see project EBITDA relief", grades=DIMENSIONS, rationale="Grounded and specific")])
        if stage == "initial_graph":
            graph=fixture_graph()
            if self.invalid_first_graph: graph.edges.append(CausalEdge(id="E3",src="N2",dst="N0",mechanism="cycle",direction="positive",strength="low",confidence="low",status="proposed"))
            return graph
        if stage == "initial_graph_repair": return fixture_graph()
        if stage == "gap_analysis": return ResearchTaskList(tasks=[ResearchTask(id="T1",target_type="edge",target_id="E1",question="Was the duty cut announced?",intent="confirm_premise",preferred_source_types=["official"],search_queries=["India solar module duty official notice"],priority="high")])
        if stage == "claim_extraction": return EvidenceClaimDrafts(claims=[EvidenceClaimDraft(source_id="S1",claim="The government announced the duty reduction",exact_passage="The government announced a reduction in the solar module import duty.",claim_type="fact",stance="supports",concepts=["solar duty"],geography="India")])
        if stage == "graph_patch": return GraphPatch(reason="Verified premise",evidence_ids=["C1"],remaining_gaps=[],operations=[GraphOperation(op="update_edge",target_id="E1",value={"status":"supported","supporting_claim_ids":["C1"],"confidence":"high"})])
        if stage == "whole_graph_review": return GraphPatch(reason="Coherent",operations=[],remaining_gaps=[])
        if stage == "challenge": return ChallengeResult(findings=[ChallengeFinding(id="F1",target_type="edge",target_id="E2",failure_mode="Pass-through",explanation="Savings may be passed through",severity="medium")])
        if stage == "adjudication":
            operations=[GraphOperation(op="reject_edge",target_id="E2")] if self.counter_remove else []
            decision="accept_and_remove" if operations else "unresolved"
            return AdjudicationResult(decisions=[AdjudicationDecision(finding_id="F1",decision=decision,reason="Exposure coefficient is unavailable",operations=operations)])
        if stage == "case_selection": return CaseSelection(central_case=case())
        if stage == "newsletter":
            sid="S404" if self.bad_report else "S1"; body=("The supplied announcement is an announcement, not a measured outcome. The causal evidence supports a duty-to-cost transmission while the EBITDA step remains conditional. "*15)+f" [{sid}]"
            return NewsletterReport(headline="A duty cut meets the project ledger",dek="The strongest consequence runs through procurement costs",why_this_matters="Indian listed developers could experience project-level EBITDA relief through lower procurement costs.",article_markdown=body,central_case_summary="The central path is best supported because the premise and first mechanism are verified.",key_assumptions=["Developers retain some procurement savings"],what_changes_the_view=["Complete pass-through of procurement savings"],source_ids_used=[sid])
        raise AssertionError(stage)


def make_run(tmp_path, settings, model):
    repo=Repository(f"sqlite:///{tmp_path/'integration.db'}");repo.init_schema()
    snippet="India announced a cut in the solar module import duty, lowering the likely landed cost of imported modules for project developers. "*3
    run_id=repo.create_run(NewsBatch(items=[NewsItem(id="N1",url="https://news.test/item",headline="India cuts solar import duty",snippet=snippet)]))
    Pipeline(settings.model_copy(update={"database_url":f"sqlite:///{tmp_path/'integration.db'}"}),repo,model=model,search=FakeSearch(),fetcher=FakeFetcher()).run(run_id)
    return repo,run_id


def test_complete_successful_run_stops_early_and_persists_restart(tmp_path,settings):
    model=ScriptedModel();repo,run_id=make_run(tmp_path,settings,model)
    assert repo.get_run(run_id)["status"] == "completed"
    assert model.calls.count("gap_analysis") == 1
    assert repo.artifact(run_id,"graph")["version"] == 2
    restarted=Repository(f"sqlite:///{tmp_path/'integration.db'}");restarted.init_schema()
    assert restarted.artifact(run_id,"report")["source_ids_used"] == ["S1"]

def test_malformed_initial_graph_gets_one_repair(tmp_path,settings):
    model=ScriptedModel(invalid_first_graph=True);repo,run_id=make_run(tmp_path,settings,model)
    assert repo.get_run(run_id)["status"] == "completed" and model.calls.count("initial_graph_repair")==1

def test_report_invented_source_id_fails_closed(tmp_path,settings):
    repo,run_id=make_run(tmp_path,settings,ScriptedModel(bad_report=True))
    assert repo.get_run(run_id)["status"] == "report_validation_failed"
    assert repo.artifact(run_id,"report") is None and repo.artifact(run_id,"report_draft")

def test_no_viable_candidate_is_fatal(tmp_path,settings):
    model=ScriptedModel()
    original=model.generate
    def generate(**kwargs):
        if kwargs['stage']=='candidate_selection':
            c=CandidateSeed(id="X",source_item_ids=[ITEM_ID],reported_premise="Weak",factual_status="unclear",possible_immediate_effect="Unclear effect",possible_indian_equity_route="A forced route",grades={**DIMENSIONS,"grounded_starting_point":"low","indian_equity_transmission":"low"},rationale="Weak")
            return CandidateSelection(candidates=[c])
        return original(**kwargs)
    model.generate=generate
    repo,run_id=make_run(tmp_path,settings,model)
    assert repo.get_run(run_id)["status"] == "failed"

def test_partial_fetch_failure_is_retained_as_warning(tmp_path,settings):
    repo=Repository(f"sqlite:///{tmp_path/'partial.db'}");repo.init_schema();model=ScriptedModel()
    snippet="India announced a cut in the solar module import duty and provided enough supplied discovery context. "*4
    run_id=repo.create_run(NewsBatch(items=[NewsItem(url="https://news.test/item",headline="India cuts solar import duty",snippet=snippet)]))
    Pipeline(settings,repo,model=model,search=PartialSearch(),fetcher=PartialFetcher()).run(run_id)
    assert repo.get_run(run_id)["status"]=="completed_with_warnings"
    context=repo.artifact(run_id,"report_context");assert any("fixture timeout" in f for f in context["research_failures"])

def test_research_stops_at_hard_cycle_limit(tmp_path,settings):
    model=ScriptedModel();original=model.generate
    def generate(**kwargs):
        result=original(**kwargs)
        if kwargs['stage']=='graph_patch': result=result.model_copy(update={"remaining_gaps":["still unresolved"]})
        return result
    model.generate=generate
    limited=settings.model_copy(update={"max_research_cycles":2})
    repo,run_id=make_run(tmp_path,limited,model)
    assert model.calls.count("gap_analysis")==2 and repo.get_run(run_id)["status"] in {"completed","completed_with_warnings"}

def test_invalid_graph_patch_receives_one_repair(tmp_path,settings):
    model=ScriptedModel();original=model.generate
    def generate(**kwargs):
        if kwargs['stage']=='graph_patch':
            model.calls.append('graph_patch')
            return GraphPatch(reason="bad",operations=[GraphOperation(op="add_edge",target_id="E9",value={"src":"N2","dst":"N0","mechanism":"cycle","direction":"positive","strength":"low","confidence":"low","status":"proposed"})])
        if kwargs['stage']=='graph_patch_repair':
            model.calls.append('graph_patch_repair')
            return GraphPatch(reason="repaired",evidence_ids=["C1"],operations=[GraphOperation(op="update_edge",target_id="E1",value={"status":"supported","supporting_claim_ids":["C1"]})])
        return original(**kwargs)
    model.generate=generate
    repo,run_id=make_run(tmp_path,settings,model)
    assert repo.get_run(run_id)["status"]=="completed" and model.calls.count('graph_patch_repair')==1
    assert repo.artifact(run_id,"invalid_graph_patch")

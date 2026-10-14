from steelman.deliberation import FullSteelmanPipeline
from steelman.domains import DomainPack
from steelman.evaluation import ResolvedDispute, ideological_turing_score, score_resolved_dispute
from steelman.integrations import LocalMirfishAdapter, Neo4jGraphStore
from steelman.models import FrameMode, Side, TrackerEntry
from steelman.storage import SQLiteStore


def test_full_dual_pipeline_delivers_all_deliberative_artifacts(tmp_path):
    store = SQLiteStore(tmp_path / "full.db")
    result = FullSteelmanPipeline(verification_cache=store, rounds=3).run(
        "Policy rates will reduce inflation", "India", "2027", domain=DomainPack.RATES_MACRO
    )
    assert set(result.claim.frames) == set(FrameMode)
    assert set(result.negation.frames) == set(FrameMode)
    assert result.claim.hardening and result.negation.hardening
    assert result.claim.retreat_path and result.negation.retreat_path
    assert result.claim.budget.tokens_used == result.negation.budget.tokens_used
    assert result.claim.budget.searches_used == result.negation.budget.searches_used
    assert result.cruxes and result.claim.predictions[0].deadline == "2027-12-31"
    assert result.rubric.regeneration_count == 1
    assert "9:rubric-gate" in result.dag_log
    assert LocalMirfishAdapter().cascade(result.claim.run.graph, result.claim.run.graph.nodes[1].id)


def test_tracker_resolution_and_calibration(tmp_path):
    store = SQLiteStore(tmp_path / "tracker.db")
    result = FullSteelmanPipeline().run("Cash flow will increase", time_horizon="2027")
    prediction = result.claim.predictions[0]
    store.register_prediction(TrackerEntry(prediction=prediction, confidence=0.7))
    resolved = store.resolve_prediction(prediction.id, 1.0)
    assert resolved.outcome is True
    assert store.calibration().brier_score == 0.09


def test_evaluation_harness_scores_voice_and_resolved_dispute():
    result = FullSteelmanPipeline().run("Credit spreads will decline", time_horizon="2027", domain=DomainPack.CREDIT)
    assert ideological_turing_score("A proponent grounds the case in incentives.") == 1.0
    assert ideological_turing_score("Obviously the so-called case is irrational.") < 1.0
    score = score_resolved_dispute(result, ResolvedDispute(claim="Credit spreads will decline", correct_side=Side.CLAIM))
    assert 0 <= score <= 1


class _Session:
    def __init__(self): self.calls = []
    def __enter__(self): return self
    def __exit__(self, *args): return None
    def run(self, query, **params): self.calls.append((query, params))


class _Driver:
    def __init__(self): self.value = _Session()
    def session(self): return self.value


def test_neo4j_adapter_writes_nodes_and_edges_without_live_server():
    result = FullSteelmanPipeline().run("Margins will rise", time_horizon="2027")
    driver = _Driver()
    Neo4jGraphStore("bolt://unused", "user", "password", driver=driver).save_graph(result.claim.run.graph)
    assert len(driver.value.calls) == 1 + len(result.claim.run.graph.nodes) + len(result.claim.run.graph.edges)


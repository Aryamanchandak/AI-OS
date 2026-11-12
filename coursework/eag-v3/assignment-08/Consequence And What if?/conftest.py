from decimal import Decimal

import pytest

from consequence_radar.config import Settings
from consequence_radar.models import Assumption, CausalEdge, CausalGraph, CausalNode, Estimate


@pytest.fixture
def settings(tmp_path):
    return Settings(database_url=f"sqlite:///{tmp_path / 'radar.db'}", report_min_words=100, report_max_words=1200)


@pytest.fixture
def graph():
    return CausalGraph(version=1, nodes=[
        CausalNode(id="N0", label="Policy announced", node_type="news_seed", description="A supplied official policy announcement", geography="Global"),
        CausalNode(id="N1", label="Imported input cost", node_type="intermediate", description="Input cost transmission", geography="India", time_horizon="6 months"),
        CausalNode(id="N2", label="Indian sector EBITDA", node_type="sector_metric", description="Sector EBITDA sensitivity", geography="India", entity_ids=["NSE:SECTOR"], time_horizon="12 months"),
    ], edges=[
        CausalEdge(id="E1", src="N0", dst="N1", mechanism="The policy changes the landed cost of an imported input.", direction="positive", strength="medium", confidence="medium", assumption_ids=["A1"], status="supported", supporting_claim_ids=["C1"]),
        CausalEdge(id="E2", src="N1", dst="N2", mechanism="Higher input costs compress sector EBITDA unless passed through.", direction="negative", strength="medium", confidence="medium", status="assumption_only", estimate_ids=["Q1"]),
    ], assumptions=[Assumption(id="A1", statement="The policy is implemented on schedule", required_for_edge_ids=["E1"], basis="Official timetable", likelihood="likely", likelihood_basis="sourced", supporting_claim_ids=["C1"], if_false_effect="The cost transmission is delayed", material=True)], estimates=[Estimate(id="Q1", metric="EBITDA direction", estimate_type="directional_only", caveat="Company exposure coefficient unavailable")])


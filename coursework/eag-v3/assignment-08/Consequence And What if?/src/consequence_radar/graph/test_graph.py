import pytest

from consequence_radar.graph import GraphValidationError, apply_patch, validate_graph
from consequence_radar.models import GraphOperation, GraphPatch


def test_graph_integrity_and_indian_path(graph, settings):
    assert validate_graph(graph, settings, require_indian_path=True) == []
    broken = graph.model_copy(deep=True); broken.edges[0].dst = "missing"
    assert any("missing endpoint" in p for p in validate_graph(broken, settings))

def test_dag_enforcement_and_patch_rollback(graph, settings):
    patch = GraphPatch(reason="bad cycle", operations=[GraphOperation(op="add_edge", target_id="E3", value={"src":"N2","dst":"N0","mechanism":"Creates a forbidden feedback loop.","direction":"positive","strength":"low","confidence":"low","status":"proposed"})])
    with pytest.raises(GraphValidationError): apply_patch(graph, patch, settings)
    assert graph.version == 1 and len(graph.edges) == 2

def test_direct_seed_to_stock_price_is_invalid(graph, settings):
    broken = graph.model_copy(deep=True); broken.nodes[2].node_type="market_outcome"; broken.nodes[2].label="Stock price"; broken.edges[1].src="N0"
    assert any("direct news_seed" in p for p in validate_graph(broken, settings))

def test_reference_integrity(graph, settings):
    broken = graph.model_copy(deep=True); broken.edges[0].assumption_ids=["missing"]
    assert any("missing assumption" in p for p in validate_graph(broken, settings))


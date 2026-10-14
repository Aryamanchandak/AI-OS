"""DAG layering and splicing — the invariants the parallel claim rests on."""

import pytest

from agent.graph import Graph, Node


def n(nid, deps=(), skill="retriever"):
    return Node(id=nid, skill=skill, input=f"task {nid}", depends_on=list(deps))


class TestLayers:
    def test_independent_nodes_share_one_layer(self):
        g = Graph([n("a"), n("b"), n("c")])
        layers = g.layers()
        assert len(layers) == 1
        assert {x.id for x in layers[0]} == {"a", "b", "c"}

    def test_fan_out_then_fan_in(self):
        g = Graph([n("a"), n("b"), n("c"), n("agg", ["a", "b", "c"])])
        layers = g.layers()
        assert [sorted(x.id for x in layer) for layer in layers] == \
            [["a", "b", "c"], ["agg"]]

    def test_chain_is_one_node_per_layer(self):
        g = Graph([n("a"), n("b", ["a"]), n("c", ["b"])])
        assert [len(layer) for layer in g.layers()] == [1, 1, 1]

    def test_cycle_is_rejected(self):
        g = Graph([n("a", ["b"]), n("b", ["a"])])
        with pytest.raises(ValueError, match="cycle"):
            g.layers()

    def test_unknown_dependency_is_rejected(self):
        with pytest.raises(ValueError, match="unknown node"):
            Graph([n("a", ["ghost"])])

    def test_duplicate_ids_rejected(self):
        with pytest.raises(ValueError, match="duplicate"):
            Graph([n("a"), n("a")])


class TestSplice:
    def test_splice_rewires_successors_to_recovery_tail(self):
        g = Graph([n("fetch"), n("metrics", ["fetch"]), n("answer", ["metrics"])])
        g.splice(
            [n("refetch"), n("recompute", ["refetch"])],
            rewire={"answer": ["recompute"]},
        )
        assert g.nodes["answer"].depends_on == ["recompute"]
        layers = [sorted(x.id for x in layer) for layer in g.layers()]
        assert layers[-1] == ["answer"]

    def test_splice_refuses_to_clobber(self):
        g = Graph([n("a")])
        with pytest.raises(ValueError, match="clobber"):
            g.splice([n("a")], rewire={})

    def test_splice_that_creates_a_cycle_is_rejected(self):
        g = Graph([n("a"), n("b", ["a"])])
        with pytest.raises(ValueError, match="cycle"):
            g.splice([n("r", ["b"])], rewire={"a": ["r"]})

    def test_successors_lookup(self):
        g = Graph([n("a"), n("b", ["a"]), n("c", ["a"])])
        assert sorted(x.id for x in g.successors("a")) == ["b", "c"]
        assert g.successors("b") == []

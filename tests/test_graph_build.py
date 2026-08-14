"""Integration: instantiate templates on the real HOB set and check counts + integrity."""

import pytest

from hobkg import pipeline


@pytest.fixture(scope="module")
def stats():
    pipeline.run()               # ensure Phase 1 outputs exist
    return pipeline.build_templates()


def test_instantiation_counts(stats):
    inst = stats["instantiations"]
    assert inst["recruit"] == 10
    assert inst["storied_payoff"] == 9
    assert inst["hone"] == 2
    assert inst["adventure"] == 17
    assert inst["saga"] == 8


def test_no_dangling_edges(stats):
    assert stats["dangling_edges"] == []


def test_storied_gate_and_contributors(stats):
    # Sagas (8) and other legendary/artifact permanents must contribute; at least the
    # 8 sagas plus qualifying tokens (e.g. Treasure) show up.
    assert stats["instantiations"]["storied_contrib_faces"] >= 8
    assert stats["instantiations"]["storied_contrib_tokens"] >= 1
    assert "CONTRIBUTES_TO" in stats["edge_predicates"]


def test_validate_reloads_graph():
    result = pipeline.validate()
    assert result["data/graph/nodes.jsonl"] > 0
    assert result["data/graph/edges.jsonl"] > 0
    assert result["graph_dangling_edges"] == []

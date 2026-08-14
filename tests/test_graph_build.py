"""Integration: instantiate templates on the real HOB set; check counts, integrity,
object identity, and token enrichment."""

import json

import pytest

from hobkg import pipeline


@pytest.fixture(scope="module")
def stats():
    pipeline.run()               # ensure Phase 1 outputs + token enrichment exist
    return pipeline.build_templates()


def test_instantiation_counts(stats):
    inst = stats["instantiations"]
    assert inst["recruit"] == 10
    assert inst["storied_payoff"] == 9
    assert inst["hone"] == 2
    assert inst["adventure"] == 17
    assert inst["saga"] == 8
    assert inst["storied_qualifier_faces"] >= 8
    assert inst["storied_qualifier_tokens"] >= 1


def test_no_dangling_edges(stats):
    assert stats["dangling_edges"] == []


def test_object_identity(stats):
    edges = [json.loads(l) for l in (pipeline.REPO / "data/graph/edges.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    # exactly one create-Soldier edge across all 10 Recruit cards
    soldier = [e for e in edges if e["predicate"] == "CREATES_OBJECT" and e["target"] == "token:human-soldier"]
    assert len(soldier) == 1
    # card-level Storied uses QUALIFIES_FOR, never CONTRIBUTES_TO
    assert stats["edge_predicates"].get("QUALIFIES_FOR", 0) > 0
    assert "CONTRIBUTES_TO" not in stats["edge_predicates"]
    # each Saga has its own lore-count state node
    nodes = {json.loads(l)["id"] for l in (pipeline.REPO / "data/graph/nodes.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
    lore_states = [n for n in nodes if n.startswith("state:") and n.endswith(":lore-count")]
    assert len(lore_states) == 8


def test_tokens_enriched():
    toks = {json.loads(l)["name"]: json.loads(l)
            for l in (pipeline.REPO / "data/normalized/tokens.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()}
    hs = toks["Human Soldier"]
    assert hs["enriched"] is True
    assert hs["colors"] == ["W"] and hs["power"] == "1" and hs["toughness"] == "1"
    assert "mana" in (toks["Treasure"]["oracle_text"] or "").lower()


def test_validate_reloads_graph():
    result = pipeline.validate()
    assert result["data/graph/nodes.jsonl"] > 0
    assert result["graph_dangling_edges"] == []

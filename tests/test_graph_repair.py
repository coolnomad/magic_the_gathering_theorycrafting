"""Phase 5 graph-repair + reprojection gate tests."""

import hashlib
import json

import pytest

from hobkg import graph_repair
from hobkg.pipeline import REPO, _load_dicts

GLOBAL = REPO / "data" / "graph_global"


@pytest.fixture(scope="module")
def repaired():
    rs = graph_repair.repair()
    ps = graph_repair.reproject()
    return rs, ps


@pytest.fixture(scope="module")
def repair_edges(repaired):
    return [json.loads(l) for l in (GLOBAL / "repair_edges.jsonl").read_text(encoding="utf-8").splitlines()]


@pytest.fixture(scope="module")
def reprojected(repaired):
    return [json.loads(l) for l in
            (GLOBAL / "card_pair_projection_repaired.jsonl").read_text(encoding="utf-8").splitlines()]


def test_all_queue_entries_repaired(repaired):
    rs, ps = repaired
    assert rs["repaired"] == rs["queue"] and rs["skipped"] == 0
    assert ps["reprojected"] == rs["queue"] and ps["unrepaired"] == 0
    assert ps["edges_resolve"] is True


def test_repair_edges_are_a_separate_layer_with_provenance(repair_edges):
    frozen = {e["edge_id"] for e in _load_dicts(GLOBAL / "edges.jsonl")}
    assert repair_edges
    for e in repair_edges:
        assert e["origin"] == "graph_repair"
        assert e["edge_id"] not in frozen                     # frozen Phase 4 graph untouched
        assert e["provenance"] and e["provenance"][0]["source"] == "graph_repair"
        assert e["provenance"][0]["grounding"]                # cites the audit grounding


def test_reprojected_paths_are_faithful(reprojected):
    real = {e["edge_id"] for e in _load_dicts(GLOBAL / "edges.jsonl")}
    rep = {e["edge_id"] for e in _load_dicts(GLOBAL / "repair_edges.jsonl")}
    assert len(reprojected) == 8
    for m in reprojected:
        assert m["origin"] == "graph_repair" and m["path_kind"] == "grounded"
        assert m["uses_repair_edges"]                         # each closes a real gap
        for s in m["steps"]:
            assert s["edge_id"] in real or s["edge_id"] in rep   # every step resolves
        # path is continuous
        seq = m["primitive_path"]
        assert len(seq) == len(m["steps"]) + 1


def test_specific_repairs(reprojected, ):
    nm = {c["id"]: c["name"] for c in _load_dicts(REPO / "data/normalized/cards.jsonl")}
    by = {(nm.get(m["source_card"]), nm.get(m["target_card"])): m for m in reprojected}
    # life-loss -> Master mill: CAUSES event -> TRIGGERS
    gollum = by[("Gollum, Riddle Master", "The Master of Lake-town")]
    assert gollum["relation"] == "ENABLES_TRIGGER"
    assert gollum["path_predicates"] == ["CAUSES", "TRIGGERS"]
    assert gollum["primitive_path"][1] == "event:player-loses-life"
    # Thranduil ObjectModifier: MODIFIES obj:subtype:elf <- HAS_TYPE <- token:elf <- CREATES_OBJECT
    th = by[("Thranduil, Sindarin Liege // Silvan Rally", "Down in the Valley")]
    assert th["relation"] == "AMPLIFIES_EFFECT"
    assert th["path_predicates"] == ["MODIFIES", "HAS_TYPE", "CREATES_OBJECT"]
    assert "obj:subtype:elf" in th["primitive_path"]


def test_frozen_graph_unchanged(repaired):
    # repair/reproject must NOT rewrite the frozen Phase 4 nodes/edges
    def digest(name):
        return hashlib.sha256((GLOBAL / name).read_bytes()).hexdigest()
    before = {n: digest(n) for n in ("nodes.jsonl", "edges.jsonl")}
    graph_repair.repair(); graph_repair.reproject()
    assert {n: digest(n) for n in ("nodes.jsonl", "edges.jsonl")} == before


def test_reprojection_byte_identical():
    def d():
        graph_repair.repair(); graph_repair.reproject()
        return hashlib.sha256((GLOBAL / "card_pair_projection_repaired.jsonl").read_bytes()).hexdigest()
    assert d() == d()

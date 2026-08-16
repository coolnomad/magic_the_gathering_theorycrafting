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


def test_specific_repairs(reprojected):
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


def test_multiface_repairs_attach_to_correct_face(repair_edges):
    """The face-identity fix: on multiface cards the repaired op must be on the SAME face
    as the grounding, not merely the same card UUID."""
    causes = {e["source"] for e in repair_edges if e["predicate"] == "CAUSES"}
    modifies = {e["source"] for e in repair_edges if e["predicate"] == "MODIFIES"}
    # Clap! Snap!'s Amass is on the ADVENTURE face :1, not the front face :0
    assert any(":1:amass" in s and "27e17542" in s for s in causes)
    assert not any("27e17542" in s and ":0:" in s for s in causes)
    # Thranduil's anthem is materialized on face :0 (not Silvan Rally's face :1)
    assert any("f6771d32" in s and ":0:anthem" in s for s in modifies)
    assert not any("f6771d32" in s and ":1:" in s for s in modifies)


def test_repair_op_face_matches_grounding(repair_edges):
    import re
    FACE = re.compile(r"face:[0-9a-f-]{36}:\d+")
    queue = _load_dicts(GLOBAL / "audit_repair_queue.jsonl")
    # map each repair edge (by its cited candidate_concept+card) back to grounding faces
    for e in repair_edges:
        m = FACE.search(e["source"])
        if not m:
            continue
        op_face = m.group(0)
        uuid = op_face.split(":")[1]
        gfaces = {g["face_id"] for q in queue for g in q.get("grounding", [])
                  if uuid in (g.get("face_id") or "")}
        # a repaired/materialized op's face must be one the enabler grounding cited
        assert op_face in gfaces, f"{e['source']} face not in grounding faces {gfaces}"


def test_wolf_multiplicity_preserved(repair_edges):
    wolf = next((e for e in repair_edges if e["predicate"] == "REQUIRES" and e["target"] == "token:wolf"), None)
    assert wolf is not None
    assert wolf.get("quantity") == 2                          # "two or more other Wolves", not one


def test_object_modifier_carries_modification(repair_edges):
    mod = next((e for e in repair_edges if e["predicate"] == "MODIFIES" and e["target"] == "obj:subtype:elf"), None)
    assert mod is not None
    assert mod["modification"] == {"power": "+1", "toughness": "+1"}


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

"""Full-spec completion: the three targeted/stateful mechanisms (second-draw gate,
Dwarf/Equipment -> Dáin's Company, noncreature-cast -> Bothersome Noisemaker)."""

import hashlib
import json

import pytest

from hobkg import complete_mechanisms as cm
from hobkg.pipeline import REPO, _load_dicts

G = REPO / "data" / "graph_global"


@pytest.fixture(scope="module")
def mat():
    return cm.materialize()


@pytest.fixture(scope="module")
def rep(mat):
    return cm.reproject()


@pytest.fixture(scope="module")
def medges():
    return list(_load_dicts(G / "mechanism_edges.jsonl"))


@pytest.fixture(scope="module")
def mrel(rep):
    return list(_load_dicts(G / "card_pair_projection_mechanism.jsonl"))


def _name_to_card():
    return {c["name"]: c["id"] for c in _load_dicts(REPO / "data/normalized/cards.jsonl")}


def test_layer_is_additive_and_signature_valid(mat):
    # 0 predicate-signature violations against the same table as the frozen graph
    assert mat["signature_violations"] == 0
    assert mat["mechanism_nodes"] == 3 and mat["mechanism_edges"] == 111
    # frozen Phase 4 graph is untouched by materialization
    edges = list(_load_dicts(G / "edges.jsonl"))
    assert not any(e.get("origin") == "mechanism_repair" for e in edges)
    for e in _load_dicts(G / "mechanism_edges.jsonl"):
        assert e["origin"] == "mechanism_repair" and e.get("provenance")


def test_second_draw_gate_structure(medges):
    # each draw op PRODUCES the turn count; the count SATISFIES the gate under the second-draw
    # condition; the gate PRODUCES the second-draw event(s)
    draws = [e for e in medges if e["predicate"] == "PRODUCES" and e["target"] == cm.STATE_COUNT]
    assert draws and all("op:" in e["source"] for e in draws)
    sat = [e for e in medges if e["source"] == cm.STATE_COUNT and e["predicate"] == "SATISFIES"
           and e["target"] == cm.GATE_SECOND]
    assert sat and cm.COND_SECOND in (sat[0].get("condition_ids") or [])
    produced = {e["target"] for e in medges if e["source"] == cm.GATE_SECOND and e["predicate"] == "PRODUCES"}
    assert "event:draw_second_card_each_turn" in produced        # the event Councillors triggers on


def test_second_draw_gate_is_transition_not_persistent(mat):
    # pt4 defect #2: the gate fires ONCE on the count transition 1->2, not persistently on >=2;
    # the count resets at the start of the controller's turn.
    nodes = {n["id"]: n for n in _load_dicts(G / "mechanism_nodes.jsonl")}
    gate = nodes[cm.GATE_SECOND]["data"]
    assert gate["comparison"] == "==" and gate["threshold"] == 2
    assert gate["gate_type"] == "turn_scoped_transition_threshold"
    assert gate["transition"] == {"previous": 1, "increment": 1, "new": 2}
    state = nodes[cm.STATE_COUNT]["data"]
    assert state["reset"] == "start_of_controllers_turn"


def test_second_draw_canonicalized_all_genuine_drawers(mat, mrel):
    # gold-set follow-up: ALL genuine card-draw ops feed the counter (not just the 4 producing
    # the canonical draw event), so previously-missed drawers enable the second-draw payoffs —
    # but the Kíli / Dáin's-Company "reveal ... put into hand" TUTOR is correctly excluded.
    assert mat["draw_ops_wired"] >= 15
    n2c = {c["name"]: c["id"] for c in _load_dicts(REPO / "data/normalized/cards.jsonl")}
    mc = n2c["Master's Councillors"]
    enablers = {m["source_card"] for m in mrel if m["target_card"] == mc}
    # previously-missing genuine drawers now enable Councillors
    for name in ("Gollum, Riddle Master", "Azog, Moria's Ruin", "Key to the Side-Door"):
        assert n2c[name] in enablers, f"{name} should now be a second-draw enabler"
    # the tutor is NOT an enabler (it does not draw)
    assert n2c["Kíli the Resourceful"] not in enablers


def test_second_draw_condition_resolves(mat):
    # pt4 defect #1: cond:draw-is-second-this-turn must have a resolvable condition record
    conds = {c["condition_id"]: c for c in _load_dicts(G / "mechanism_conditions.jsonl")}
    assert cm.COND_SECOND in conds
    assert conds[cm.COND_SECOND]["expression"]["op"] == "eq"
    assert mat["unresolved_conditions"] == []                    # every referenced condition resolves


def test_recruit_enables_councillors_with_second_draw_condition(mrel):
    n2c = _name_to_card()
    mc = n2c["Master's Councillors"]
    mech = {}
    for m in _load_dicts(REPO / "data/rules/mechanics.jsonl"):
        mech.setdefault(m["mechanic"], set()).add(m["card_id"])
    r2c = [m for m in mrel if m["target_card"] == mc and m["source_card"] in mech["Recruit"]]
    assert r2c, "at least one Recruit -> Councillors relation"
    for m in r2c:
        assert m["relation"] == "ENABLES_TRIGGER"
        assert cm.COND_SECOND in (m.get("condition_ids") or [])   # principle #5: only as the 2nd draw
        # the path is grounded end-to-end and passes through the gate
        assert "gate:second-draw" in m["primitive_path"] and m["path_kind"] == "grounded"
    # feeds all three second-draw payoffs, not only Councillors
    payoffs = {m["target_card"] for m in mrel if "gate:second-draw" in m["primitive_path"]}
    assert {n2c["Master's Councillors"], n2c["Bard the Bowman"], n2c["Lakeshore Apothecary"]} <= payoffs


def test_dwarf_equipment_supplies_dains_company(medges, mrel):
    n2c = _name_to_card()
    dc = n2c["Dáin's Company"]
    # the find op REQUIRES the Dwarf/Equipment object classes
    req = {e["target"] for e in medges if e["predicate"] == "REQUIRES"}
    assert {"obj:subtype:dwarf", "obj:subtype:equipment"} <= req
    suppliers = [m for m in mrel if m["target_card"] == dc and m["relation"] == "SUPPLIES_RESOURCE"]
    assert len(suppliers) >= 10
    for m in suppliers:
        assert m["connecting_node"] in ("obj:subtype:dwarf", "obj:subtype:equipment")
        assert m["path_predicates"][0] == "HAS_TYPE" and "REQUIRES" in m["path_predicates"]


def test_noncreature_cast_enables_noisemaker(medges, mrel):
    n2c = _name_to_card()
    nz = n2c["Bothersome Noisemaker"]
    # the canonical cast op produces the noncreature-cast event(s); many spells link to it
    assert any(e["source"] == cm.OP_CAST and e["predicate"] == "PRODUCES"
               and e["target"] == "event:cast-noncreature-spell" for e in medges)
    haslinks = [e for e in medges if e["predicate"] == "HAS_ABILITY" and e["target"] == cm.OP_CAST]
    assert len(haslinks) >= 50                                    # the noncreature-spell population
    enablers = [m for m in mrel if m["target_card"] == nz and m["relation"] == "ENABLES_TRIGGER"]
    assert len(enablers) >= 50
    for m in enablers:
        assert m["path_predicates"] == ["HAS_ABILITY", "PRODUCES", "TRIGGERS"]
        assert m["source_card"] != nz                            # a spell never enables itself here


def test_no_self_pairs_and_edges_resolve(rep, mrel):
    assert rep["edges_resolve"]
    assert all(m["source_card"] != m["target_card"] for m in mrel)


def test_deterministic():
    def run():
        cm.materialize()
        cm.reproject()
        return hashlib.sha256((G / "mechanism_edges.jsonl").read_bytes()).hexdigest() + \
            hashlib.sha256((G / "card_pair_projection_mechanism.jsonl").read_bytes()).hexdigest()
    assert run() == run()

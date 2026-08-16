"""Additive "resource / trigger completeness" layer for HOB (three related families).

Covers: 0 signature violations; conditions resolve; determinism (hash twice); the continuity
gate re-verified per metaedge (paths_continuous / paths_card_grounded True, adjacent step joins
connect, endpoints resolve to the source/target cards, every step edge_id resolves); family-4
has no reverse relation (target is always a sac-cost card, source always a permanent); and the
flagship pairs — a token creator -> Belladonna Took (FAMILY 2, ENABLES_TRIGGER); Tom, Bert, and
William -> Rhovanion Rampager (FAMILY 3, ENABLES_TRIGGER); Crude Bent Blade -> Stir Up Trouble
AND -> Snowslope Hunter (FAMILY 4, SATISFIES_SACRIFICE_COST). Also: Stone-Giant of High Pass is
NOT a family-3 enabler (it sacrifices only an artifact).
"""

import hashlib

import pytest

from hobkg import completeness as comp
from hobkg.pipeline import REPO, _load_dicts

G = REPO / "data" / "graph_global"


@pytest.fixture(scope="module")
def mat():
    return comp.materialize()


@pytest.fixture(scope="module")
def rep(mat):
    return comp.reproject()


@pytest.fixture(scope="module")
def cnodes(mat):
    return {n["id"]: n for n in _load_dicts(G / "completeness_nodes.jsonl")}


@pytest.fixture(scope="module")
def cedges(mat):
    return list(_load_dicts(G / "completeness_edges.jsonl"))


@pytest.fixture(scope="module")
def cconds(mat):
    return {c["condition_id"]: c for c in _load_dicts(G / "completeness_conditions.jsonl")}


@pytest.fixture(scope="module")
def crel(rep):
    return list(_load_dicts(G / "card_pair_projection_completeness.jsonl"))


def _name_to_card():
    return {c["name"]: c["id"] for c in _load_dicts(REPO / "data/normalized/cards.jsonl")}


def _card_names():
    return {c["id"]: c["name"] for c in _load_dicts(REPO / "data/normalized/cards.jsonl")}


def _has(crel, src_name, tgt_name, relation):
    names = _card_names()
    return [m for m in crel if names.get(m["source_card"]) == src_name
            and names.get(m["target_card"]) == tgt_name and m["relation"] == relation]


def _permanent_cards(cls):
    edges = list(_load_dicts(G / "edges.jsonl"))
    return {c for e in edges if e["predicate"] == "HAS_TYPE" and e["target"] == cls
            for c in [comp._card_of(e["source"])] if c}


# ---- 0. additive + signature valid ----------------------------------------------------
def test_layer_is_additive_and_signature_valid(mat):
    assert mat["signature_violations"] == 0
    # frozen Phase 4 graph is untouched by materialization
    edges = list(_load_dicts(G / "edges.jsonl"))
    assert not any(e.get("origin") == "completeness" for e in edges)
    for e in _load_dicts(G / "completeness_edges.jsonl"):
        assert e["origin"] == "completeness" and e.get("provenance")
    for n in _load_dicts(G / "completeness_nodes.jsonl"):
        assert n["origin"] == "completeness" and n.get("provenance")


# ---- 1. all new conditions resolve ----------------------------------------------------
def test_conditions_resolve(mat, cconds, cedges):
    assert mat["unresolved_conditions"] == []
    frozen = {c["condition_id"] for c in _load_dicts(G / "conditions.jsonl")}
    defined = frozen | set(cconds)
    referenced = {c for e in cedges for c in (e.get("condition_ids") or [])}
    assert referenced - defined == set()
    for cid in (comp.COND_SAC_CONTROLLED, comp.COND_SAC_ON_BATTLEFIELD, comp.COND_SAC_ANOTHER):
        assert cid in cconds


# ---- 2. determinism -------------------------------------------------------------------
def test_deterministic():
    def run():
        comp.materialize()
        comp.reproject()
        return "".join(hashlib.sha256((G / f).read_bytes()).hexdigest() for f in
                       ("completeness_nodes.jsonl", "completeness_edges.jsonl",
                        "completeness_conditions.jsonl", "card_pair_projection_completeness.jsonl"))
    assert run() == run()


# ---- 3. THE continuity gate — re-verified per metaedge --------------------------------
def test_paths_continuous_and_card_grounded(rep, crel):
    assert rep["paths_continuous"] is True
    assert rep["paths_card_grounded"] is True
    assert rep["edges_resolve"] is True
    real_ids = {e["edge_id"] for e in _load_dicts(G / "edges.jsonl")}
    c_ids = {e["edge_id"] for e in _load_dicts(G / "completeness_edges.jsonl")}
    assert crel
    for m in crel:
        steps = m["steps"]
        # (a) adjacent steps share the traversed endpoint
        for a, b in zip(steps, steps[1:]):
            assert a["target"] == b["source"], (
                f"discontinuous {m['relation']} {m['source_card']}->{m['target_card']}: "
                f"{a['target']} != {b['source']}")
        # primitive_path is exactly the traversed node sequence
        assert m["primitive_path"] == [steps[0]["source"]] + [s["target"] for s in steps]
        # (b) endpoints resolve to the source/target cards
        assert comp._card_of(m["primitive_path"][0]) == m["source_card"]
        assert comp._card_of(m["primitive_path"][-1]) == m["target_card"]
        assert m["source_card"] != m["target_card"]
        # (c) every step edge_id resolves to a frozen edge or a completeness-layer edge
        for s in steps:
            assert s["edge_id"] in real_ids or s["edge_id"] in c_ids


# ---- 4. FAMILY 2 — token-entry triggers -----------------------------------------------
def test_family2_token_creator_enables_belladonna(mat, cedges, crel):
    # the canonical event exists and triggers Belladonna's token-entry ability
    assert comp.EVENT_TOKEN_ENTERS in {n["id"] for n in _load_dicts(G / "completeness_nodes.jsonl")}
    assert any(e["source"] == comp.EVENT_TOKEN_ENTERS and e["predicate"] == "TRIGGERS"
               and e["target"] == comp.BELLADONNA_ABILITY for e in cedges)
    # a token creator PRODUCES the event
    assert any(e["predicate"] == "PRODUCES" and e["target"] == comp.EVENT_TOKEN_ENTERS for e in cedges)
    # flagship: a specific token creator -> Belladonna Took (ENABLES_TRIGGER)
    flag = _has(crel, "Bejeweled Warg", "Belladonna Took", "ENABLES_TRIGGER")
    assert flag, "token creator Bejeweled Warg -> Belladonna Took missing"
    # every FAMILY-2 metaedge targets Belladonna and runs through the canonical event
    fam2 = [m for m in crel if m.get("trigger") == "token-you-control-enters"]
    assert fam2
    names = _card_names()
    for m in fam2:
        assert names[m["target_card"]] == "Belladonna Took"
        assert comp.EVENT_TOKEN_ENTERS in m["primitive_path"]


def test_family2_gate_mediated_skipped(mat):
    # some token creators are gate-mediated (no card op) — they cannot be grounded from a card
    assert mat["fam2_skipped_gate_mediated"] >= 1
    # opponent-owned tokens are not "a token you control"
    assert mat["fam2_skipped_opponent_tokens"] >= 1


# ---- 5. FAMILY 3 — sacrifice-outlet -> dies-trigger -----------------------------------
def test_family3_sac_outlet_enables_dies_trigger(crel):
    # flagship: Tom, Bert, and William -> Rhovanion Rampager (ENABLES_TRIGGER)
    flag = _has(crel, "Tom, Bert, and William", "Rhovanion Rampager", "ENABLES_TRIGGER")
    assert flag, "Tom, Bert, and William -> Rhovanion Rampager (dies) missing"
    for m in flag:
        assert m.get("trigger") == "dies" and m.get("via") == "sacrifice"
        # the path runs sac op -CAUSES-> a dies event -TRIGGERS-> the dies-ability
        assert any(nid in comp.DIES_EVENTS for nid in m["primitive_path"])


def test_family3_stone_giant_is_not_an_enabler(crel):
    # Stone-Giant of High Pass sacrifices only an artifact -> it does NOT feed a dies trigger
    fam3 = [m for m in crel if m.get("trigger") == "dies"]
    names = _card_names()
    assert not any(names[m["source_card"]] == "Stone-Giant of High Pass" for m in fam3)


# ---- 6. FAMILY 4 — typed-cost + permanent-consumption ---------------------------------
def test_family4_crude_bent_blade_satisfies_sac_costs(crel):
    # flagship: Crude Bent Blade (artifact) -> Stir Up Trouble AND -> Snowslope Hunter
    stir = _has(crel, "Crude Bent Blade", "Stir Up Trouble", "SATISFIES_SACRIFICE_COST")
    snow = _has(crel, "Crude Bent Blade", "Snowslope Hunter", "SATISFIES_SACRIFICE_COST")
    assert stir, "Crude Bent Blade -> Stir Up Trouble missing"
    assert snow, "Crude Bent Blade -> Snowslope Hunter missing"
    # Crude is an Equipment being sacrificed: terminates_attachment recorded
    assert stir[0].get("terminates_attachment") is True


def test_family4_no_reverse_relation(crel):
    # target of SATISFIES_SACRIFICE_COST is ALWAYS a sac-cost card; source ALWAYS a permanent
    sac_cards = set()
    names = _card_names()
    for fid in comp.SAC_OUTLETS:
        sac_cards.add(comp._card_of(fid))
    permanents = _permanent_cards("obj:type:artifact") | _permanent_cards("obj:type:creature")
    fam4 = [m for m in crel if m["relation"] == "SATISFIES_SACRIFICE_COST"]
    assert fam4
    for m in fam4:
        assert m["target_card"] in sac_cards, f"target {names.get(m['target_card'])} not a sac-cost card"
        assert m["source_card"] in permanents, "source is not a controlled permanent"
        # the sacrificed type is one the outlet accepts, and the path consumes that type
        assert m["sacrificed_type"] in ("artifact", "creature")
        cls = comp.OBJ_TYPE_ARTIFACT if m["sacrificed_type"] == "artifact" else comp.OBJ_TYPE_CREATURE
        assert cls in m["primitive_path"]


def test_family4_gate_carries_cost_alternatives(cnodes):
    # Stir Up Trouble's gate records the OR-pay alternative; Stone-Giant accepts only artifact
    stir_gate = cnodes.get("gate:completeness:sac-cost:face:dda607bd-f419-4b7f-b052-a5ce6ce22bfe:0")
    assert stir_gate and stir_gate["data"]["or_pay"] == "{4}"
    assert set(stir_gate["data"]["alternatives"]) == {"artifact", "creature"}
    stone_gate = cnodes.get("gate:completeness:sac-cost:face:cfaa8b7b-7bfc-4660-bbc7-a717e05df6ef:0")
    assert stone_gate and stone_gate["data"]["alternatives"] == ["artifact"]


# ---- 7. edges resolve + signatures (final gate) ---------------------------------------
def test_paths_and_signatures_validate(mat, rep, crel):
    assert mat["signature_violations"] == 0
    assert rep["edges_resolve"]
    real_ids = {e["edge_id"] for e in _load_dicts(G / "edges.jsonl")}
    c_ids = {e["edge_id"] for e in _load_dicts(G / "completeness_edges.jsonl")}
    for m in crel:
        for s in m["steps"]:
            assert s["edge_id"] in real_ids or s["edge_id"] in c_ids

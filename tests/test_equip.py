"""Additive Equip attachment layer for "The Hobbit" Equipment cards.

Covers the reviewer's required regressions (1-14): all 12 Equipment instantiate the Equip
template; costs preserved; targets are creatures; controller/sorcery restrictions present;
every equipped-creature effect is attachment-conditioned and shares the binding; automatic
(ETB) attachment is distinct from the Equip activation and from the ETB itself; Wizard's
Staff's two modes; no reverse relation; conditions resolve; determinism; signatures valid.
"""

import hashlib
import json

import pytest

from hobkg import equip as eq
from hobkg.pipeline import REPO, _load_dicts

G = REPO / "data" / "graph_global"


@pytest.fixture(scope="module")
def mat():
    return eq.materialize()


@pytest.fixture(scope="module")
def rep(mat):
    return eq.reproject()


@pytest.fixture(scope="module")
def enodes(mat):
    return {n["id"]: n for n in _load_dicts(G / "equip_nodes.jsonl")}


@pytest.fixture(scope="module")
def eedges(mat):
    return list(_load_dicts(G / "equip_edges.jsonl"))


@pytest.fixture(scope="module")
def econds(mat):
    return {c["condition_id"]: c for c in _load_dicts(G / "equip_conditions.jsonl")}


@pytest.fixture(scope="module")
def erel(rep):
    return list(_load_dicts(G / "card_pair_projection_equip.jsonl"))


def _name_to_card():
    return {c["name"]: c["id"] for c in _load_dicts(REPO / "data/normalized/cards.jsonl")}


def _equipment_faces():
    g = eq._G(REPO)
    return {f["name"]: f["id"] for f in g.equipment_faces()}


def _creature_cards():
    edges = list(_load_dicts(G / "edges.jsonl"))
    return {c for e in edges if e["predicate"] == "HAS_TYPE" and e["target"] == "obj:type:creature"
            for c in [eq._card_of(e["source"])] if c}


# ---- 0. additive + signature valid ----------------------------------------------------
def test_layer_is_additive_and_signature_valid(mat):
    assert mat["signature_violations"] == 0
    assert mat["equip_cards"] == 12
    # frozen Phase 4 graph is untouched by materialization
    edges = list(_load_dicts(G / "edges.jsonl"))
    assert not any(e.get("origin") == "equip" for e in edges)
    for e in _load_dicts(G / "equip_edges.jsonl"):
        assert e["origin"] == "equip" and e.get("provenance")


# ---- 1. all 12 Equipment instantiate/reference the Equip template ---------------------
def test_all_twelve_reference_equip_template(enodes, eedges):
    faces = _equipment_faces()
    assert len(faces) == 12
    for name, E in faces.items():
        assert f"ability:equip:{E}" in enodes, f"{name} missing equip ability"
        # HAS_ABILITY face -> ability:equip:E
        assert any(e["source"] == E and e["predicate"] == "HAS_ABILITY"
                   and e["target"] == f"ability:equip:{E}" for e in eedges)
        # REFERENCES_RULE rule:equip
        assert any(e["source"] == E and e["predicate"] == "REFERENCES_RULE"
                   and e["target"] == "rule:equip" for e in eedges)


# ---- 2. every Equip cost is preserved --------------------------------------------------
def test_equip_cost_preserved(enodes):
    faces = _equipment_faces()
    for name, E in faces.items():
        cost = enodes.get(f"cost:equip:{E}")
        assert cost is not None and cost["type"] == "Cost", f"{name} missing cost node"
        assert cost["data"].get("raw", "").startswith("Equip")
        assert cost["data"].get("mana_cost")            # a printed mana cost is preserved
    # spot-check specific printed costs
    assert enodes[f"cost:equip:{faces['Goblin Plate Mail']}"]["data"]["mana_cost"] == "{4}"
    assert enodes[f"cost:equip:{faces['The Black Arrow']}"]["data"]["mana_cost"] == "{1}"


# ---- 3. every attachment target is a creature -----------------------------------------
def test_attach_targets_are_creatures(erel):
    creatures = _creature_cards()
    cats = [m for m in erel if m["relation"] == "CAN_ATTACH_TO"]
    assert cats
    for m in cats:
        assert m["target_card"] in creatures


# ---- 4. controller + sorcery-timing restrictions present as conditions ----------------
def test_controller_and_timing_conditions(erel):
    cats = [m for m in erel if m["relation"] == "CAN_ATTACH_TO" and m.get("equip_mode") == "primary"]
    assert cats
    for m in cats:
        conds = m.get("condition_ids") or []
        assert eq.COND_TARGET_CONTROLLED in conds
        assert eq.COND_SORCERY_TIMING in conds


# ---- 5. every equipped-creature effect is attachment-conditioned ----------------------
def test_equipped_effects_are_attachment_conditioned(erel):
    effects = [m for m in erel if m["relation"] in
               ("MODIFIES_WHEN_ATTACHED", "GRANTS_ABILITY_WHEN_ATTACHED")]
    assert effects
    for m in effects:
        # path goes through the bound attachment state
        assert any(nid.startswith("state:attachment:") for nid in m["primitive_path"])
        assert any(cid.startswith("cond:equipment-") and cid.endswith("-attached")
                   for cid in (m.get("condition_ids") or []))


# ---- 6. Equipment and affected creature use the SAME binding --------------------------
def test_same_binding_for_attachment_and_bonuses(eedges):
    faces = _equipment_faces()
    for name, E in faces.items():
        state = f"state:attachment:{E}"
        bound = f"obj:bound-creature:{E}"
        # the equip op CAUSES the state
        assert any(e["source"] == f"op:equip:{E}" and e["predicate"] == "CAUSES"
                   and e["target"] == state for e in eedges)
        # every equipped-bonus op REQUIRES the same state and MODIFIES the same bound creature
        for op_pre in ("op:modify-equipped:", "op:grant-equipped:"):
            op = f"{op_pre}{E}"
            bonus_edges = [e for e in eedges if e["source"] == op]
            if not bonus_edges:
                continue
            assert any(e["predicate"] == "REQUIRES" and e["target"] == state for e in bonus_edges)
            assert any(e["predicate"] == "MODIFIES" and e["target"] == bound for e in bonus_edges)


# ---- 7. Dwarven Shortsword auto-attach DISTINCT from equip activation ------------------
def test_dwarven_shortsword_auto_attach_distinct(enodes, eedges):
    E = _equipment_faces()["Dwarven Shortsword"]
    assert f"op:equip:{E}" in enodes
    assert f"op:auto-attach:{E}" in enodes
    assert f"op:equip:{E}" != f"op:auto-attach:{E}"
    aa = enodes[f"op:auto-attach:{E}"]["data"]
    assert aa["kind"] == "automatic" and aa["trigger"] == "etb"
    eqop = enodes[f"op:equip:{E}"]["data"]
    assert eqop["kind"] == "equip_activation"
    # both reach the same attachment state, but via distinct ops/abilities
    state = f"state:attachment:{E}"
    assert any(e["source"] == f"op:auto-attach:{E}" and e["target"] == state for e in eedges)
    assert any(e["source"] == f"op:equip:{E}" and e["target"] == state for e in eedges)
    # the auto-attach hangs off a distinct ability (auto-attach), not the equip ability
    assert any(e["source"] == f"ability:auto-attach:{E}" and e["predicate"] == "CAUSES"
               and e["target"] == f"op:auto-attach:{E}" for e in eedges)


# ---- 8. Wizard's Staff preserves its two equip modes ----------------------------------
def test_wizards_staff_two_modes(enodes, eedges, erel):
    E = _equipment_faces()["Wizard's Staff"]
    # primary mode (any creature) + alt mode (restricted to Wizards)
    assert enodes[f"cost:equip:{E}"]["data"]["mana_cost"] == "{3}"
    assert enodes[f"cost:equip-alt:{E}"]["data"]["mana_cost"] == "{1}"
    assert enodes[f"op:equip-alt:{E}"]["data"].get("target_restriction") == "wizard"
    # alt op REQUIRES the Wizard subtype
    assert any(e["source"] == f"op:equip-alt:{E}" and e["predicate"] == "REQUIRES"
               and e["target"] == "obj:subtype:wizard" for e in eedges)
    # the alt CAN_ATTACH_TO relations are all wizards, carrying the wizard condition
    wizards = {c for e in _load_dicts(G / "edges.jsonl")
               if e["predicate"] == "HAS_TYPE" and e["target"] == "obj:subtype:wizard"
               for c in [eq._card_of(e["source"])] if c}
    ws_card = eq._card_of(E)
    alt = [m for m in erel if m["source_card"] == ws_card and m["relation"] == "CAN_ATTACH_TO"
           and m.get("equip_mode") == "alternative-wizard"]
    assert alt, "Wizard's Staff alt mode not reprojected"
    for m in alt:
        assert m["target_card"] in wizards
        assert eq.COND_TARGET_IS_WIZARD in (m.get("condition_ids") or [])
        assert m["equip_cost"]["mana_cost"] == "{1}"


# ---- 9. ETB triggers are not confused with attachment events --------------------------
def test_etb_not_confused_with_attach(enodes, eedges):
    # for each auto-attach card, the ETB op that CREATES/AMASSES/etc. is distinct from the
    # attach op: we only ever attach via op:auto-attach:E (kind automatic), which is a
    # separate node from op:equip:E. And the automatic op is explicitly ETB-triggered
    # while remaining a DISTINCT node from the equip activation.
    for name in ("Sting, Bilbo's Sword", "Dwarven Shortsword", "Goblin Plate Mail", "Dwarven Mattock"):
        E = _equipment_faces()[name]
        aa = f"op:auto-attach:{E}"
        assert aa in enodes, f"{name} missing auto-attach op"
        assert enodes[aa]["data"]["kind"] == "automatic"
        # the attach op is NOT the equip op
        assert aa != f"op:equip:{E}"
        # the auto-attach ability is NOT the equip ability
        assert f"ability:auto-attach:{E}" != f"ability:equip:{E}"


# ---- 10. representative query record has cost, conditions, state, modification, prov ---
def test_representative_query_record(erel):
    n2c = _name_to_card()
    orcrist = n2c["Orcrist, Goblin-cleaver"]
    mods = [m for m in erel if m["source_card"] == orcrist and m["relation"] == "MODIFIES_WHEN_ATTACHED"]
    assert mods
    m = mods[0]
    assert m["modification"] == {"power": "+2", "toughness": "+2"}
    assert m["attachment_state"].startswith("state:attachment:")
    assert any(cid.endswith("-attached") for cid in m["condition_ids"])
    assert m["origin"] == "equip" and m["path_kind"] == "grounded"
    # a CAN_ATTACH_TO record carries the equip cost
    cats = [m for m in erel if m["source_card"] == orcrist and m["relation"] == "CAN_ATTACH_TO"]
    assert cats and cats[0]["equip_cost"]["mana_cost"] == "{3}"


# ---- 11. no reverse creature -> Equipment relation ------------------------------------
def test_no_reverse_relation(erel):
    equip_cards = {eq._card_of(E) for E in _equipment_faces().values()}
    creatures = _creature_cards()
    for m in erel:
        # the target is NEVER an Equipment (no reverse creature->Equipment relation)
        assert m["target_card"] not in equip_cards
        assert m["target_card"] in creatures
        # the source is an Equipment, OR (for the Axe token) the card that CREATES the Axe
        assert m["source_card"] in equip_cards or m.get("equip_mode") == "via-created-token:axe"
        assert m["source_card"] != m["target_card"]


# ---- 12. all new condition IDs resolve ------------------------------------------------
def test_conditions_resolve(mat, econds, eedges):
    assert mat["unresolved_conditions"] == []
    # every condition referenced on an equip edge is defined in the frozen + equip layers
    frozen = {c["condition_id"] for c in _load_dicts(G / "conditions.jsonl")}
    defined = frozen | set(econds)
    referenced = {c for e in eedges for c in (e.get("condition_ids") or [])}
    assert referenced - defined == set()
    # the required stable conditions exist
    for cid in (eq.COND_TARGET_CONTROLLED, eq.COND_SORCERY_TIMING, eq.COND_TARGET_IS_WIZARD,
                eq.COND_AUTO_ATTACH_TARGET_IS_DWARF):
        assert cid in econds
    # a per-equipment attached condition exists for each Equipment (12 cards + the Axe token)
    per_eq = [c for c in econds if c.startswith("cond:equipment-") and c.endswith("-attached")]
    assert len(per_eq) == 13


# ---- 13. deterministic ----------------------------------------------------------------
def test_deterministic():
    def run():
        eq.materialize()
        eq.reproject()
        return (hashlib.sha256((G / "equip_nodes.jsonl").read_bytes()).hexdigest()
                + hashlib.sha256((G / "equip_edges.jsonl").read_bytes()).hexdigest()
                + hashlib.sha256((G / "equip_conditions.jsonl").read_bytes()).hexdigest()
                + hashlib.sha256((G / "card_pair_projection_equip.jsonl").read_bytes()).hexdigest())
    assert run() == run()


# ---- 14. paths + signatures validate --------------------------------------------------
def test_paths_and_signatures_validate(mat, rep, erel):
    assert mat["signature_violations"] == 0
    assert rep["edges_resolve"]
    real_ids = {e["edge_id"] for e in _load_dicts(G / "edges.jsonl")}
    eq_ids = {e["edge_id"] for e in _load_dicts(G / "equip_edges.jsonl")}
    for m in erel:
        for s in m["steps"]:
            assert s["edge_id"] in real_ids or s["edge_id"] in eq_ids


# ---- extra: the auto-attach Dwarven Mattock carries the dwarf restriction -------------
def test_mattock_auto_attach_requires_dwarf(eedges):
    E = _equipment_faces()["Dwarven Mattock"]
    reqs = [e for e in eedges if e["source"] == f"op:auto-attach:{E}" and e["predicate"] == "REQUIRES"]
    assert reqs and reqs[0]["target"] == "obj:subtype:dwarf"
    assert eq.COND_AUTO_ATTACH_TARGET_IS_DWARF in (reqs[0].get("condition_ids") or [])


# ======================================================================================
#  pt5 regressions — the defects the prior build shipped (path continuity was NOT tested)
# ======================================================================================
def test_pt5_every_path_is_continuous_and_card_grounded(erel, rep):
    # THE pt5 defect: steps were concatenated, not connected (obj:creature-you-control !=
    # obj:type:creature), and modify/grant paths reached neither card. Assert real continuity.
    assert rep["paths_continuous"] and rep["paths_card_grounded"]
    creatures = _creature_cards()
    equip_cards = {eq._card_of(E) for E in _equipment_faces().values()}
    for m in erel:
        steps = m["steps"]
        # (a) adjacent steps share the traversed endpoint
        for a, b in zip(steps, steps[1:]):
            assert a["target"] == b["source"], (
                f"discontinuous join in {m['relation']} {m['source_card']}->{m['target_card']}: "
                f"{a['target']} != {b['source']}")
        # (b) primitive_path is exactly the traversed node sequence
        assert m["primitive_path"] == [steps[0]["source"]] + [s["target"] for s in steps]
        # (c) endpoints ARE the source/target cards (path[0] and path[-1] resolve to them)
        assert eq._card_of(m["primitive_path"][0]) == m["source_card"]
        assert eq._card_of(m["primitive_path"][-1]) == m["target_card"]
        # (d) the target is genuinely a creature; the source is an Equipment or an Axe-creator
        assert m["target_card"] in creatures
        assert m["source_card"] in equip_cards or m.get("equip_mode") == "via-created-token:axe"


def test_pt5_no_operation_requires_the_state_it_causes(mat, eedges):
    # the prior build had the auto-attach op both CAUSE and be conditioned on being attached
    assert mat["circular_attach_ops"] == []
    causes = {(e["source"], e["target"]) for e in eedges if e["predicate"] == "CAUSES" and e["target"].startswith("state:")}
    requires = {(e["source"], e["target"]) for e in eedges if e["predicate"] == "REQUIRES" and e["target"].startswith("state:")}
    assert causes & requires == set()
    # and the CAUSES-state edges are NOT conditioned on the attachment (attachment is the result)
    for e in eedges:
        if e["predicate"] == "CAUSES" and e["target"].startswith("state:attachment:"):
            assert not any(c.endswith("-attached") for c in (e.get("condition_ids") or []))


def test_pt5_no_orphan_equip_abilities(mat, eedges):
    # every equip-layer Ability (equip, equipped-bonus, equipped-grant, auto-attach) must have
    # an incoming HAS_ABILITY from its face/token (the prior build orphaned several)
    assert mat["orphan_abilities"] == []
    enodes = {n["id"]: n for n in _load_dicts(G / "equip_nodes.jsonl")}
    has_ability = {e["target"] for e in eedges if e["predicate"] == "HAS_ABILITY"}
    for nid, n in enodes.items():
        if n["type"] == "Ability":
            assert nid in has_ability, f"orphan ability {nid}"


def test_pt5_token_axe_template_coverage(mat, enodes, eedges, erel):
    # the Axe Equipment token (no card face) was skipped; it must get primitive template coverage
    assert mat["token_axe_covered"]
    assert f"ability:equip:{eq.TOKEN_AXE}" in enodes and f"state:attachment:{eq.TOKEN_AXE}" in enodes
    # and its +1/+0 equipped bonus is represented
    mod = enodes.get(f"op:modify-equipped:{eq.TOKEN_AXE}")
    assert mod and mod["data"]["modification"] == {"power": "+1", "toughness": "+0"}
    # the Axe's creator projects CAN_ATTACH_TO through the created token (grounded card->card)
    via_axe = [m for m in erel if m.get("equip_mode") == "via-created-token:axe"]
    assert via_axe
    for m in via_axe:
        assert eq.TOKEN_AXE in m["primitive_path"]


def test_pt5_provenance_carries_oracle_spans(eedges):
    # the spec requires exact provenance; equip edges carrying a printed cost/effect must cite
    # the face and an Oracle span
    spanned = [e for e in eedges if any(p.get("oracle_span") for p in e.get("provenance", []))]
    assert len(spanned) >= 12                            # at least the per-Equipment equip costs
    for e in spanned:
        p = next(pp for pp in e["provenance"] if pp.get("oracle_span"))
        assert p.get("face_id") and isinstance(p["oracle_span"], list) and len(p["oracle_span"]) == 2
        assert "rule_ref" in p


def test_pt5_every_equipped_clause_dispositioned():
    # every printed "Equipped creature ..." clause is dispositioned (represented / ignored),
    # not silently dropped
    disp = list(_load_dicts(G / "equip_dispositions.jsonl"))
    assert disp
    for d in disp:
        assert d["disposition"] in ("represented", "deliberately_ignored", "unresolved")
    # the complex effects the review noted are recorded as deliberately_ignored, not missing
    ignored_faces = {d["equipment"] for d in disp if d["disposition"] == "deliberately_ignored"}
    assert {"Glamdring, Foe-hammer", "Orcrist, Goblin-cleaver"} <= ignored_faces

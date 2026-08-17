"""Effect-semantics Phase 3: the targeted-object families (damage / counters / P-T / grants / tap /
fight / type-change) with same-object variable binding, and the mandated regression + negative cases."""

from hobkg import effect_semantics as es, effect_schema as sch
from hobkg.pipeline import REPO, _load_dicts

G = REPO / "data/graph_global"


def _faces():
    return {f["name"]: f for f in _load_dicts(REPO / "data/normalized/faces.jsonl")}


def _effs(name):
    return es._object_effects(_faces()[name])


def _by_op(name):
    d = {}
    for e in _effs(name):
        d.setdefault(e["op"], []).append(e)
    return d


def test_warg_mode1_counter_and_grant_bind_same_object():
    o = _by_op("Warg Tactics")
    ctr, gr = o["ADD_COUNTER"][0], o["GRANT_ABILITY"][0]
    assert ctr["object_var"] == gr["object_var"] == "obj0"   # SAME creature
    assert gr["abilities"] == ["hexproof", "trample"] and ctr["n"] == 1
    assert ctr["relation"] == "ADDS_COUNTER_TO" and gr["relation"] == "GRANTS_ABILITY_TO"


def test_reverent_howl_mode1_pump_and_grant_same_object():
    o = _by_op("Reverent Howl")
    pt, gr = o["MODIFY_PT"][0], o["GRANT_ABILITY"][0]
    assert pt["object_var"] == gr["object_var"]
    assert pt["pt_mod"] == "+2/+2" and gr["abilities"] == ["lifelink"]
    assert pt["duration"] == "until_end_of_turn"


def test_pinecone_damage_carries_same_object_replacement():
    o = _by_op("Pinecone Strike")
    dmg = o["DEAL_DAMAGE"][0]
    assert dmg["amount"] == "3" and dmg["selector"]["card_types"] == ["creature"]
    assert dmg["replacement"]["kind"] == "die_would_exile_instead"
    assert dmg["replacement"]["object_var"] == dmg["object_var"]     # exile the SAME creature


def test_magnificent_end_damage_and_cost_reduction_condition():
    dmg = _by_op("Magnificent End")["DEAL_DAMAGE"][0]
    assert dmg["amount"] == "5" and dmg["targeted"] is True
    assert dmg["cost_modification"]["amount"] == "{3}"
    assert dmg["cost_modification"]["condition"]["predicate"] == "target_is_tapped"


def test_stone_by_sunlight_mode1_type_change_and_indestructible_same_object():
    o = _by_op("Stone by Sunlight")
    ct, gr = o["CHANGE_TYPE"][0], o["GRANT_ABILITY"][0]
    assert ct["object_var"] == gr["object_var"]
    assert ct["added_type"] == "artifact" and gr["abilities"] == ["indestructible"]
    assert ct["duration"] == "until_end_of_turn"


def test_troll_negotiations_distinct_objects_counter_then_fight():
    o = _by_op("Troll Negotiations")
    ctr, fight = o["ADD_COUNTER"][0], o["FIGHT"][0]
    assert ctr["n"] == 2 and ctr["object_var"] == "obj0" and ctr["selector"]["controller"] == "you"
    assert fight["object_var"] == "obj0" and fight["fight_target_var"] == "obj1"   # distinct objects
    assert fight["fight_target_selector"]["controller"] == "opponent"


def test_quarrel_source_power_damage_distinguishes_source_from_target():
    dmg = _by_op("Quarrel")["DEAL_DAMAGE"][0]
    assert dmg["amount"] == "equal_to_source_power"
    assert dmg["source_var"] == "obj0" and dmg["object_var"] == "obj1"
    assert dmg["source_selector"]["controller"] == "you"
    assert dmg["selector"]["controller"] == "opponent"


def test_concerted_care_grants_two_abilities_keeps_controller_restriction():
    gr = _by_op("Concerted Care")["GRANT_ABILITY"][0]
    assert gr["abilities"] == ["hexproof", "indestructible"]
    assert set(gr["selector"]["card_types"]) == {"artifact", "creature"} and gr["selector"]["or_types"]
    assert gr["selector"]["controller"] == "you"            # controller restriction retained


def test_gaze_in_wonder_taps_up_to_two():
    tap = _by_op("Gaze in Wonder")["TAP"][0]
    assert tap["relation"] == "CAN_TAP" and tap["selector"]["quantifier"] == "up_to_2"


def test_projection_relations_present_in_pair_index():
    es.build_effects()
    n2c = {f["name"]: f["card_id"] for f in _load_dicts(REPO / "data/normalized/faces.jsonl")}
    idx = {(r["source_card"], r["target_card"]): r for r in _load_dicts(G / "pair_index.jsonl")}
    # regenerate pair_index to compose the effect layer
    from hobkg import coverage
    coverage.pair_index()
    idx = {(r["source_card"], r["target_card"]): r for r in _load_dicts(G / "pair_index.jsonl")}
    warg = n2c["Warg Tactics"]
    row = next(r for (s, t), r in idx.items() if s == warg and r.get("effect_semantics"))
    assert any(rel in row["effect_semantics"] for rel in ("ADDS_COUNTER_TO", "GRANTS_ABILITY_TO"))


def test_no_tap_false_positive_from_untap_step():
    # 'untap step' / 'doesn't untap' has no target -> emits no CAN_TAP/CAN_UNTAP effect
    effs = es._object_effects({"id": "face:x:0", "name": "X",
                               "oracle_text": "This creature doesn't untap during its untap step."})
    assert not any(e["op"] in ("TAP", "UNTAP") for e in effs)


def test_all_object_effects_validate():
    faces = _load_dicts(REPO / "data/normalized/faces.jsonl")
    for f in faces:
        for e in es._object_effects(f):
            assert sch.validate_effect(e) == [], (f["name"], e["op"])

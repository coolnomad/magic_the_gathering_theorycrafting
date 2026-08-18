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


# ---- review PHASE3 pt1 regression: the generalized behaviour must be SAFE ----

def test_no_cross_ability_target_leak():
    # Dwarven Mattock: "+2/+2" applies to the EQUIPPED creature (equip layer), not the earlier
    # target Dwarf -> no object MODIFY_PT leaks across abilities.
    assert not _effs("Dwarven Mattock")
    # Master's Councillors: its self +2/+0 is NOT bound to the later target player.
    mc = _by_op("Master's Councillors")["MODIFY_PT"][0]
    assert mc["object_var"] == "self" and mc["selector"]["self"] is True


def test_self_effects_are_explicit():
    sting = _by_op("Sting, Bilbo's Sword")["ADD_COUNTER"][0]
    assert sting["object_var"] == "self" and sting["selector"]["self"] is True


def test_duration_attaches_per_operation():
    o = _by_op("Warg Tactics")
    assert o["ADD_COUNTER"][0]["duration"] is None                 # counter is permanent
    assert o["GRANT_ABILITY"][0]["duration"] == "until_end_of_turn"  # only the grant expires
    dmg = _by_op("Pinecone Strike")["DEAL_DAMAGE"][0]
    assert dmg["duration"] is None                                  # damage is immediate
    assert dmg["replacement"]["duration"] == "this_turn"           # the replacement lasts the turn


def test_participant_separated_and_no_empty_object_selectors():
    o = _by_op("Gnashing of Teeth")["MODIFY_PT"]
    mass = [e for e in o if e["affects_each"]][0]
    assert mass["participant"] == "target_player" and mass["targeted"] is False
    faces = _load_dicts(REPO / "data/normalized/faces.jsonl")
    for f in faces:                                                # no object effect has an empty selector
        for e in es._object_effects(f):
            assert not sch.selector_is_empty(e["selector"]), (f["name"], e["op"])


def test_comma_separated_or_subtype_lists_and_controller():
    mk = _by_op("Mirkwood")["ADD_COUNTER"][0]
    assert set(mk["selector"]["subtypes"]) == {"bear", "spider", "wolf"}
    assert mk["selector"]["controller"] == "you"
    assert sch.selector("Bear, Spider, or Wolf you control")["subtypes"] == ["bear", "spider", "wolf"]
    # 'Orc' is not a printed HOB subtype (no Orc permanents) -> vocabulary-validated out; Goblin kept
    assert sch.selector("Goblin or Orc you control")["subtypes"] == ["goblin"]
    ac = sch.selector("artifact or creature you control")
    assert set(ac["card_types"]) == {"artifact", "creature"} and ac["or_types"] and ac["controller"] == "you"
    assert "up_to_2" in str(sch.selector("creatures", quantifier="up_to_2")["quantifier"])


def test_new_families_present():
    assert _by_op("Galion, Elvenking's Butler")["SET_BASE_PT"][0]["object_var"] == "obj0"
    assert _by_op("Mirkwood Meditator")["SET_BASE_PT"][0]["value"] == "4/2"
    assert _by_op("Burglar's Plot")["CONTROL_CHANGE"][0]["relation"] == "EXCHANGES_CONTROL_OF"
    assert _by_op("Old Fat Spider Can't See Me")["PREVENT_DAMAGE"][0]["relation"] == "PREVENTS_DAMAGE_FROM"
    # Enchanted River's Grasp's "loses all abilities" is an aura static -> no targeted removal
    assert not any(e["op"] == "REMOVE_ABILITY" for e in _effs("Enchanted River's Grasp"))


def test_effect_ids_carry_real_clause_ids_not_placeholder():
    for f in _load_dicts(REPO / "data/normalized/faces.jsonl"):
        for e in es._object_effects(f):
            assert "#a?" not in e["clause_id"] and e["clause_id"].split("#")[1].startswith("a")


def test_black_arrow_any_target_damage_preserved():
    dmg = _by_op("The Black Arrow")["DEAL_DAMAGE"][0]
    assert dmg["any_target"] is True and dmg["selector"].get("alternatives")


def test_moment_of_glory_cast_from_graveyard_on_the_right_effect():
    ctrs = _by_op("Moment of Glory")["ADD_COUNTER"]
    targeted = [c for c in ctrs if c["targeted"]][0]
    mass = [c for c in ctrs if c["affects_each"]][0]
    assert targeted["condition"] is None                          # the first counter is unconditional
    assert mass["condition"]["kind"] == "cast_from_graveyard"      # only the each-other counter


def test_reconciliation_has_zero_unresolved():
    r = es.reconcile()
    assert r["unresolved"] == 0 and r["extracted"] > 90


# ---- review PHASE3 pt2 regression: projection-level correctness ----

def _proj():
    res = es.build_effects(write=False)
    n2c = {f["name"]: f["card_id"] for f in _load_dicts(REPO / "data/normalized/faces.jsonl")}
    by = {}
    for p in res["_pairs"]:
        by.setdefault((p["source_card"], p["relation"]), set()).add(p["target_card"])
    return n2c, by


def test_every_emitted_subtype_is_in_the_vocabulary():
    vocab = sch._subtype_vocab()
    for f in _load_dicts(REPO / "data/normalized/faces.jsonl"):
        for e in es._object_effects(f):
            for s in e["selector"].get("subtypes", []):
                assert s in vocab, (f["name"], e["op"], s)


def test_object_var_matches_selector_var():
    for f in _load_dicts(REPO / "data/normalized/faces.jsonl"):
        for e in es._object_effects(f):
            if not e.get("binding"):
                assert e["selector"]["var"] in (e["object_var"], None), (f["name"], e["op"])


def test_key_effects_actually_project_to_eligible_cards():
    n2c, by = _proj()
    creatures = {c for c, fs in
                 {ff["card_id"]: [x for x in _load_dicts(REPO / "data/normalized/faces.jsonl") if x["card_id"] == ff["card_id"]]
                  for ff in _load_dicts(REPO / "data/normalized/faces.jsonl")}.items()
                 if any("Creature" in (x.get("type_line") or {}).get("types", []) for x in fs)}
    n = len(creatures)
    assert len(by[(n2c["Reverent Howl"], "MODIFIES_POWER_TOUGHNESS")]) == n         # +2/+2 -> every creature
    assert len(by[(n2c["The Arkenstone"], "MODIFIES_POWER_TOUGHNESS")]) == n         # anthem -> every creature
    assert len(by[(n2c["Concerted Care"], "GRANTS_ABILITY_TO")]) > 100               # artifact|creature
    assert by[(n2c["Great Ugly-Looking Goblin"], "GRANTS_ABILITY_TO")] == creatures  # mass menace
    # Stone by Sunlight mode-1 grant + type-change share one object and both project
    assert len(by[(n2c["Stone by Sunlight"], "GRANTS_ABILITY_TO")]) == n
    assert len(by[(n2c["Stone by Sunlight"], "CHANGES_TYPE_OF")]) == n


def test_self_effects_project_only_source_to_source():
    n2c, by = _proj()
    for nm, rel in [("Sting, Bilbo's Sword", "ADDS_COUNTER_TO"),
                    ("Master's Councillors", "MODIFIES_POWER_TOUGHNESS"),
                    ("Mirkwood Pathmaker", "SETS_BASE_PT")]:
        assert by[(n2c[nm], rel)] == {n2c[nm]}, nm            # ONLY source→source


def test_old_fat_spider_and_burglar_projection_constraints():
    n2c, by = _proj()
    faces = _load_dicts(REPO / "data/normalized/faces.jsonl")
    by_card = {}
    for f in faces:
        by_card.setdefault(f["card_id"], []).append(f)
    ofs = by[(n2c["Old Fat Spider Can't See Me"], "PREVENTS_DAMAGE_FROM")]
    assert ofs and all(any("Creature" in (cf.get("type_line") or {}).get("types", []) for cf in by_card[t]) for t in ofs)
    burg = by[(n2c["Burglar's Plot"], "EXCHANGES_CONTROL_OF")]
    assert burg and not any(all("Land" in (cf.get("type_line") or {}).get("types", []) for cf in by_card[t]) for t in burg)


def test_reconcile_reports_deferred_separately_from_unresolved():
    r = es.reconcile()
    assert r["unresolved"] == 0 and r["deferred"] >= 3 and r["extracted"] > 100

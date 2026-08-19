"""Effect-semantics Phase 4e: RETURN / recursion (bounce + reanimation).

Object-directed movement TO hand/battlefield FROM graveyard/battlefield — so it PROJECTS to eligible
objects (`CAN_RETURN`), like removal. Blink (exile-and-return, coupled to the deferred exile family)
and stack-object spell-bounce are dispositioned, not extracted. Tests assert the generated records
(object selector, source/destination zones, participant, quantity, optionality, self vs targeted) and
the deterministic projection, while proving the accepted Phase-4a…4d records and non-return pair
projections are untouched."""

from hobkg import effect_semantics as es, effect_schema as sch
from hobkg.pipeline import REPO, _load_dicts


def _faces():
    return {f["name"]: f for f in _load_dicts(REPO / "data/normalized/faces.jsonl")}


def _ret(name):
    return es._return_effects(_faces()[name])


def _one(name):
    r = _ret(name)
    assert len(r) == 1, (name, len(r))
    return r[0]


# ---- reanimation / recursion from graveyard ---------------------------------------------------
def test_reanimation_to_battlefield():
    e = _one("The Mountain-king's Return")
    assert e["selector"]["card_types"] == ["creature"] and e["targeted"] is True
    assert (e["source_zone"], e["dest_zone"]) == ("graveyard", "battlefield") and e["event"] == "return"


def test_recursion_to_hand():
    for name in ("Along the Crooked Way", "Gathering of Darkness"):
        e = _one(name)
        assert e["selector"]["card_types"] == ["creature"]
        assert (e["source_zone"], e["dest_zone"]) == ("graveyard", "hand"), name


# ---- self-return ------------------------------------------------------------------------------
def test_self_return_from_graveyard():
    for name, dest in (("Silvan Reveler", "hand"), ("Gollum the Abandoned", "hand"),
                       ("Eagle's Rescue", "battlefield")):
        e = _one(name)
        assert e["selector"].get("self") is True and e["targeted"] is False
        assert (e["source_zone"], e["dest_zone"]) == ("graveyard", dest), name


def test_dies_self_return_to_battlefield():
    e = _one("Tom, Bert, and William")
    assert e["selector"].get("self") is True
    assert (e["source_zone"], e["dest_zone"]) == ("graveyard", "battlefield")


# ---- bounce (battlefield -> hand) -------------------------------------------------------------
def test_optional_permanent_bounce_to_hand():
    e = _one("Mirkwood Nurturer")
    assert e["selector"].get("generic_permanent") is True and e["targeted"] is True
    assert e["optional"] is True and e["quantity"] == "up_to_1"
    assert (e["source_zone"], e["dest_zone"]) == ("battlefield", "hand")


# ---- deferred cases (dispositioned, not extracted) --------------------------------------------
def test_blink_returns_are_deferred_not_extracted():
    # Elrond / Roll / Gone Fishing exile-and-return: coupled to the deferred exile slice
    for name in ("Elrond, Moon-Reader", "Roll-Roll-Roll-Roll", "Gone Fishing"):
        assert _ret(name) == [], name


def test_spell_bounce_is_deferred():
    assert _ret("Bilbo's Gambit") == []                       # 'Return target spell to its owner's hand'


# ---- projection + invariants ------------------------------------------------------------------
def test_return_projects_to_eligible_objects():
    out = es.build_effects(write=False)
    cr = [p for p in out["_pairs"] if p["relation"] == "CAN_RETURN"]
    assert cr, "reanimation/bounce must project to eligible objects"
    # a self-return projects only source->source
    silvan = _faces()["Silvan Reveler"]["card_id"]
    self_pairs = [p for p in cr if p["source_card"] == silvan]
    assert all(p["self_pair"] for p in self_pairs)


def test_return_records_validate():
    for name in ("The Mountain-king's Return", "Mirkwood Nurturer", "Tom, Bert, and William",
                 "Along the Crooked Way"):
        for e in _ret(name):
            assert sch.validate_effect(e) == [], (name, e)


def test_participant_families_still_do_not_fan_out():
    out = es.build_effects(write=False)
    part_rels = {"DRAWS_CARDS", "GAINS_LIFE", "LOSES_LIFE", "DISCARDS_CARDS", "MILLS_CARDS", "SACRIFICES"}
    assert not [p for p in out["_pairs"] if p["relation"] in part_rels]


def test_accepted_families_present_with_return_added():
    ops = {s["op"] for s in es.build_effects(write=False)["_structured"]}
    assert {"DRAW", "DISCARD", "MILL", "SACRIFICE", "SEARCH", "RETURN"} <= ops


# ================================================================================================
#  Phase 4e REPAIR (review PHASE4_review_pt14)
# ================================================================================================
def test_repair_pt14_mana_value_restriction_preserved_and_projected():
    from hobkg import effect_schema as _sch
    e = _one("The Mountain-king's Return")
    assert e["selector"]["predicates"].get("mana_value_lte") == 3
    out = es.build_effects(write=False)
    faces = _faces()
    by_card = {}
    for f in faces.values():
        by_card.setdefault(f["card_id"], []).append(f)
    mk = faces["The Mountain-king's Return"]["card_id"]
    for p in out["_pairs"]:
        if p["relation"] == "CAN_RETURN" and p["source_card"] == mk:
            assert any(_sch._cmc(cf) <= 3 for cf in by_card[p["target_card"]]), p["target_card"]


def test_repair_pt14_eagles_owner_choice_binding_and_kicked_quantity():
    e = _one("The Eagles Are Coming!")
    assert e["selector"]["card_types"] == ["creature"] and e["selector"].get("owner") == "you"
    assert e["targeted"] is True and e["binding"] == {"kind": "chosen_target", "of": "you"}
    assert e["quantity"] == "1" and e["quantity_alt"] == {"non_kicked": "1", "kicked": "any"}


def test_repair_pt14_graveyard_self_return_selector_zone_matches_source():
    for s in es.build_effects(write=False)["_structured"]:
        if s["op"] == "RETURN" and s["selector"].get("self"):
            assert s["selector"]["zone"] == s["source_zone"], (s["name"], s["selector"]["zone"])


def test_repair_pt14_eagles_rescue_attached_to_binding():
    e = _one("Eagle's Rescue")
    at = e["attach_to"]
    assert at["selector"]["card_types"] == ["creature"] and at["selector"].get("controller") == "you"
    assert at["selector"]["predicates"].get("power_le") == 1

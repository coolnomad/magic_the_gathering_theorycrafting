"""Effect-semantics Phase 4d: SEARCH / tutor — the DETERMINISTIC-projection family.

Unlike the participant-level resource families (draw/life/discard/mill/sacrifice, which never fan
out), a tutor projects to its eligible choices: the searched-for card selector fans out to every
eligible HOB card as a `SEARCHES_FOR` card→card relation (spec: 'Tutors should project to eligible
choices'). Tests assert the generated records (searched selector, source/destination zones, quantity,
optional, participant) AND the deterministic projection, while proving the participant families still
do not fan out and the accepted Phase-4a/4b/4c records are untouched."""

from hobkg import effect_semantics as es, effect_schema as sch
from hobkg.pipeline import REPO, _load_dicts


def _faces():
    return {f["name"]: f for f in _load_dicts(REPO / "data/normalized/faces.jsonl")}


def _search(name):
    return es._search_effects(_faces()[name])


def _one(name):
    s = _search(name)
    assert len(s) == 1, (name, len(s))
    return s[0]


# ---- searched-for selector + zones ------------------------------------------------------------
def test_legendary_creature_tutor_to_hand():
    e = _one("Seek the Heart")
    assert e["selector"]["card_types"] == ["creature"] and e["selector"]["supertypes"] == ["legendary"]
    assert e["source_zone"] == "library" and e["dest_zone"] == "hand" and e["reveal"] is True


def test_forest_tutor_to_battlefield():
    e = _one("Wood Elves")
    assert e["selector"]["subtypes"] == ["forest"] and e["dest_zone"] == "battlefield"


def test_basic_land_tutor_to_hand_with_reveal():
    e = _one("Thrór's Map")
    assert e["selector"]["supertypes"] == ["basic"] and e["selector"]["card_types"] == ["land"]
    assert e["dest_zone"] == "hand" and e["reveal"] is True and e["shuffle"] is True


def test_up_to_two_and_exile_destination():
    e = _one("Roads Go Ever, Ever On")
    assert e["quantity"] == "up_to_2" and e["dest_zone"] == "exile"


def test_battlefield_tapped_destination():
    for name in ("Troop of Ponies", "Elven Passage", "Hobbit Hole"):
        e = _one(name)
        assert e["dest_zone"] == "battlefield" and e["dest_tapped"] is True, name


def test_optional_tutor_to_library_top():
    e = _one("Old Thrush")
    assert e["optional"] is True and e["dest_zone"] == "library_top"


def test_hand_and_or_library_source_zone():
    # Last Light: 'search your hand and/or library for a Dragon card and put it onto the battlefield'
    e = _one("Last Light of Durin's Day")
    assert e["source_zone"] == "hand_and_library" and e["selector"]["subtypes"] == ["dragon"]
    assert e["dest_zone"] == "battlefield"


def test_settle_the_wreckage_search_binds_target_player_and_variable_quantity():
    # spec: P may search their library for that many basic lands, onto the battlefield tapped
    e = _one("Settle the Wreckage")
    assert e["participant"] == "target_player" and e["optional"] is True
    assert e["quantity"] == "variable" and e["dest_zone"] == "battlefield" and e["dest_tapped"] is True
    assert e["selector"]["supertypes"] == ["basic"] and e["selector"]["card_types"] == ["land"]


# ---- cycling-reminder tutors are keyword-layer (not extracted) ---------------------------------
def test_cycling_reminder_search_is_not_extracted():
    # Hobbit Hole's Halflingcycling reminder search is a keyword effect; only its sac-land search extracts
    e = _search("Hobbit Hole")
    assert len(e) == 1 and e[0]["selector"]["card_types"] == ["land"]   # the basic-land sac-land tutor, not Halfling


# ---- deterministic projection -----------------------------------------------------------------
def test_search_fans_out_to_eligible_cards():
    out = es.build_effects(write=False)
    sf = [p for p in out["_pairs"] if p["relation"] == "SEARCHES_FOR"]
    assert sf, "search must project to eligible choices"
    # Seek the Heart projects to legendary creatures in the pool
    seek = _faces()["Seek the Heart"]["card_id"]
    assert [p for p in sf if p["source_card"] == seek]


def test_participant_families_still_do_not_fan_out():
    out = es.build_effects(write=False)
    part_rels = {"DRAWS_CARDS", "GAINS_LIFE", "LOSES_LIFE", "DISCARDS_CARDS", "MILLS_CARDS", "SACRIFICES"}
    assert not [p for p in out["_pairs"] if p["relation"] in part_rels]


def test_search_records_validate():
    for name in ("Seek the Heart", "Settle the Wreckage", "Last Light of Durin's Day", "Wood Elves"):
        for e in _search(name):
            assert sch.validate_effect(e) == [], (name, e)


def test_accepted_participant_families_unchanged_and_search_added():
    ops = {s["op"] for s in es.build_effects(write=False)["_structured"]}
    assert {"DRAW", "GAIN_LIFE", "DISCARD", "MILL", "SACRIFICE", "SEARCH"} <= ops


# ================================================================================================
#  Phase 4d REPAIR (review PHASE4_review_pt11)
# ================================================================================================
def test_repair_pt11_searched_selector_zone_matches_source_not_battlefield():
    # the searched card lives in the library / hand+library, never the battlefield
    for s in es.build_effects(write=False)["_structured"]:
        if s["op"] == "SEARCH":
            assert s["selector"].get("zone") == s["source_zone"], (s["name"], s["selector"].get("zone"))
            assert s["selector"].get("zone") != "battlefield", s["name"]


def test_repair_pt11_settle_binds_that_many_to_exiled_attackers():
    e = _one("Settle the Wreckage")
    qf = e["quantity_formula"]
    assert qf["kind"] == "variable" and qf["source"] == "prior_exile_count"
    assert qf["of"] == "target_player" and "attacking creatures exiled" in qf["binding"]
    assert e["participant"] == "target_player"                # same target player whose creatures were exiled


def test_repair_pt11_last_light_search_gated_by_prior_self_sacrifice():
    e = _one("Last Light of Durin's Day")
    assert e["condition"]["kind"] == "prior_action_taken"     # not a generic conditional_effect marker
    assert e["source_zone"] == "hand_and_library" and e["selector"]["zone"] == "hand_and_library"


# ================================================================================================
#  Phase 4d REPAIR 2 (review PHASE4_review_pt12)
# ================================================================================================
def test_repair_pt12_troop_of_ponies_preserves_split_destinations():
    # 'put one onto the battlefield tapped and the other into your hand'
    dz = _one("Troop of Ponies")["destinations"]
    bf = [d for d in dz if d["zone"] == "battlefield"]
    hd = [d for d in dz if d["zone"] == "hand"]
    assert bf and bf[0]["tapped"] is True and bf[0]["count"] == "one"
    assert hd and hd[0]["count"] == "the other"


def test_repair_pt12_last_light_shuffle_is_conditional_on_searching_library():
    # hand-or-library search: shuffle only if the library was actually searched
    e = _one("Last Light of Durin's Day")
    assert e["shuffle"] is True
    assert e["shuffle_condition"] == {"kind": "searched_zone", "zone": "library"}


def test_repair_pt12_pure_library_search_shuffles_unconditionally():
    for name in ("Seek the Heart", "Wood Elves", "Settle the Wreckage"):
        e = _one(name)
        assert e["source_zone"] == "library" and e["shuffle_condition"] is None, name


def test_repair_pt12_every_search_has_a_destinations_list():
    for s in es.build_effects(write=False)["_structured"]:
        if s["op"] == "SEARCH" and s["dest_zone"] is not None:
            assert s["destinations"] and all("zone" in d for d in s["destinations"]), s["name"]

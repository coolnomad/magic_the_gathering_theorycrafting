"""Effect-semantics Phase 4f: EXILE.

Two sub-families: (a) STOCHASTIC top-library exile — participant-level, no card-pair fan-out, with a
structured play-permission; (b) targeted/mass permanent/card exile — object-directed, projects to
eligible objects (`CAN_EXILE`), source→exile. Blink returns (Elrond/Roll/Gone Fishing) are un-deferred
in the RETURN family, bound to the exiled objects. Adventure/Flashback reminders and death/counter
'exile … instead' replacements are dispositioned, not extracted."""

from hobkg import effect_semantics as es, effect_schema as sch
from hobkg.pipeline import REPO, _load_dicts


def _faces():
    return {f["name"]: f for f in _load_dicts(REPO / "data/normalized/faces.jsonl")}


def _ex(name):
    return es._exile_effects(_faces()[name])


def _one(name):
    e = _ex(name)
    assert len(e) == 1, (name, len(e))
    return e[0]


# ---- targeted / mass object exile (projects) --------------------------------------------------
def test_mass_exile_of_attacking_creatures():
    e = _one("Settle the Wreckage")
    assert e["relation"] == "CAN_EXILE" and e["selector"]["card_types"] == ["creature"]
    assert e["quantity"] == "all" and (e["source_zone"], e["dest_zone"]) == ("battlefield", "exile")


def test_targeted_nonland_permanent_exile():
    e = _one("Elrond, Moon-Reader")
    assert e["selector"].get("generic_permanent") is True and e["quantity"] == "up_to_2"
    assert e["dest_zone"] == "exile"


def test_creature_or_land_exile():
    assert _one("Roll-Roll-Roll-Roll")["selector"]["card_types"] == ["creature", "land"]
    assert _one("Gone Fishing")["selector"]["card_types"] == ["creature", "land"]


def test_generic_card_exile_is_not_projected():
    # Gollum: 'exile up to one target card from an opponent's graveyard' — any card, no static identity
    e = _one("Gollum the Abandoned")
    assert e["binding"] == {"kind": "generic_card"} and "not_projected" in e.get("projection", "")
    out = es.build_effects(write=False)
    gid = _faces()["Gollum the Abandoned"]["card_id"]
    assert not [p for p in out["_pairs"] if p["relation"] == "CAN_EXILE" and p["source_card"] == gid]


# ---- stochastic top-library exile (no fan-out, play permission) -------------------------------
def test_stochastic_top_library_exile_with_play_permission():
    for name, dur in (("Gundabad Opportunist", "until_end_of_next_turn"),
                      ("Snowslope Hunter", "until_end_of_next_turn"),
                      ("Inside Information", "this_turn")):
        e = _one(name)
        assert e["stochastic"] is True and e["selector"].get("participant_level") is True
        assert (e["source_zone"], e["dest_zone"]) == ("library", "exile")
        assert e["play_permission"]["allowed"] is True and e["play_permission"]["duration"] == dur, name


def test_stochastic_exile_targets_opponent_library():
    e = _one("Inside Information")
    assert e["participant"] == "target_opponent" and e["targeted"] is True and e["quantity"] == "X"


def test_stochastic_exile_does_not_fan_out():
    out = es.build_effects(write=False)
    assert not [p for p in out["_pairs"] if p["relation"] == "EXILES"]


# ---- dispositions (not extracted) -------------------------------------------------------------
def test_death_and_counter_replacements_not_extracted_as_exile():
    for name in ("Head of the Hunt", "Thranduil's Decree", "Gnashing of Teeth", "Pinecone Strike"):
        # these carry 'exile it instead' replacement semantics, not a direct EXILE effect
        assert not [e for e in _ex(name)], name


def test_adventure_flashback_reminder_exile_not_extracted():
    for name in ("Seek the Heart", "Clap! Snap!", "Spew Flame"):
        assert not [e for e in _ex(name)], name


# ---- invariants -------------------------------------------------------------------------------
def test_exile_records_validate():
    for name in ("Settle the Wreckage", "Elrond, Moon-Reader", "Gollum the Abandoned",
                 "Gundabad Opportunist", "Inside Information"):
        for e in _ex(name):
            assert sch.validate_effect(e) == [], (name, e)


def test_accepted_families_present_with_exile_added():
    ops = {s["op"] for s in es.build_effects(write=False)["_structured"]}
    assert {"DRAW", "DISCARD", "MILL", "SACRIFICE", "SEARCH", "RETURN", "EXILE"} <= ops

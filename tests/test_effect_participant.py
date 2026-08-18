"""Effect-semantics Phase 4a: participant/resource DRAW and LIFE (gain/lose) records.

Covers the mandatory Reverent Howl regression (one participant both draws two and loses 2 life —
same participant binding), participant resolution, cost-vs-effect separation ('Pay N life' is a cost,
not a life effect), the trigger-vs-effect distinction ('whenever you draw …' is a trigger), and the
false-positive guard that participant-level facts are stochastic and never fan out to card pairs."""

from hobkg import effect_semantics as es, effect_schema as sch
from hobkg.pipeline import REPO, _load_dicts


def _faces():
    return {f["name"]: f for f in _load_dicts(REPO / "data/normalized/faces.jsonl")}


def _part(name):
    return es._participant_effects(_faces()[name])


def _by_op(name):
    d = {}
    for e in _part(name):
        d.setdefault(e["op"], []).append(e)
    return d


# ---- mandatory regression: Reverent Howl — same participant draws two AND loses 2 life ----------
def test_reverent_howl_same_participant_draws_two_and_loses_two_life():
    o = _by_op("Reverent Howl")
    draw, life = o["DRAW"][0], o["LOSE_LIFE"][0]
    assert draw["amount"] == "2" and life["amount"] == "2"
    assert draw["participant"] == life["participant"] == "target_player"
    assert draw["participant_var"] == life["participant_var"]           # SAME participant object
    assert draw["relation"] == "DRAWS_CARDS" and life["relation"] == "LOSES_LIFE"


def test_rage_into_the_valley_you_draw_and_lose_bind_same_participant():
    o = _by_op("Rage into the Valley")
    assert o["DRAW"][0]["amount"] == "1" and o["LOSE_LIFE"][0]["amount"] == "1"
    assert o["DRAW"][0]["participant"] == o["LOSE_LIFE"][0]["participant"] == "you"
    assert o["DRAW"][0]["participant_var"] == o["LOSE_LIFE"][0]["participant_var"]


def test_allure_of_power_plain_draw_two_by_you():
    d = _by_op("Allure of Power")["DRAW"][0]
    assert d["amount"] == "2" and d["participant"] == "you" and d["targeted"] is False


def test_gollum_riddle_master_distinct_participants_get_distinct_vars():
    # 'Each opponent loses 2 life and you gain 2 life' — two participants in one clause, two vars
    life = {e["op"]: e for e in _part("Gollum, Riddle Master") if e["op"] in ("GAIN_LIFE", "LOSE_LIFE")}
    lo, ga = life["LOSE_LIFE"], life["GAIN_LIFE"]
    assert lo["participant"] == "each_opponent" and lo["affects_each"] is True
    assert ga["participant"] == "you"
    assert lo["participant_var"] != ga["participant_var"]               # distinct participants


def test_variable_amount_draw_is_captured():
    # Tom, Bert, and William: 'Draw cards equal to the sacrificed creature's power'
    d = _by_op("Tom, Bert, and William")["DRAW"][0]
    assert d["amount"] == "variable"
    assert d["quantity_formula"]["kind"] == "variable" and "sacrificed creature" in d["quantity_formula"]["binding"]


def test_condition_is_preserved_on_participant_effects():
    # Plunder: cast-from-graveyard draw; Smaug: intervening-if on both draw and life
    assert all(e["condition"] == {"kind": "cast_from_graveyard"}
               for e in _by_op("Plunder the Trollshaws")["DRAW"])
    smaug = _part("Smaug, Wicked Worm")
    assert {e["condition"]["kind"] for e in smaug} == {"intervening_if"}


# ---- negative / false-positive guards -----------------------------------------------------------
def test_pay_life_is_a_cost_not_a_life_effect():
    # 'Pay N life' costs must not become LOSE_LIFE effects
    for name in ("My Precious", "Desolation Prowler", "Elven Passage"):
        assert not [e for e in _part(name) if e["op"] in ("GAIN_LIFE", "LOSE_LIFE")], name


def test_draw_trigger_is_not_a_draw_effect():
    # 'Whenever you draw a card, …' / 'draw your second card' are trigger events, not draw effects
    for name in ("Ravenhill Flock", "Lakeshore Apothecary", "Bard the Bowman"):
        assert not _by_op(name).get("DRAW"), name


def test_life_change_trigger_is_not_a_life_effect():
    # 'Whenever a player loses life, …' is the trigger, not a life effect this ability produces
    assert not [e for e in _part("The Master of Lake-town") if e["op"] in ("GAIN_LIFE", "LOSE_LIFE")]


def test_recruit_reminder_draw_is_not_re_extracted():
    # recruit's '(Draw a card, then discard a card …)' is reminder text handled by the keyword layer
    assert not _by_op("Bard's Company").get("DRAW")


# ---- stochastic projection guard: participant facts never fan out to card pairs ------------------
def test_participant_effects_do_not_fan_out_to_card_pairs():
    out = es.build_effects(write=False)
    part_rels = {"DRAWS_CARDS", "GAINS_LIFE", "LOSES_LIFE"}
    assert not [p for p in out["_pairs"] if p["relation"] in part_rels]
    # but the structured participant records DO exist and are participant-level
    parts = [s for s in out["_structured"] if s["selector"].get("participant_level")]
    assert parts and all(s.get("object_var") is None for s in parts)


def test_participant_records_validate():
    for name in ("Reverent Howl", "Gollum, Riddle Master", "Allure of Power"):
        for e in _part(name):
            assert sch.validate_effect(e) == [], (name, e["op"])


# ================================================================================================
#  Phase 4a REPAIR (review PHASE4_review_pt1) — assertions on the GENERATED structured records
# ================================================================================================
def _structured():
    """The participant-level records as they land in the authoritative effect_records set."""
    out = es.build_effects(write=False)["_structured"]
    by_name = {}
    for s in out:
        if s["selector"].get("participant_level"):
            by_name.setdefault(s["name"], []).append(s)
    return by_name


def test_repair1_target_player_and_opponent_records_carry_targeting():
    rec = _structured()
    # target_player / target_opponent records are real targets; selector.targeted must agree
    for name in ("Reverent Howl", "Meager Meal"):
        tp = [e for e in rec[name] if e["participant"] == "target_player"]
        assert tp and all(e["targeted"] and e["selector"]["targeted"] for e in tp), name
    for name in ("Down, Down to Goblin-town", "The Sackville-Bagginses"):
        to = [e for e in rec[name] if e["participant"] == "target_opponent" and e["op"] == "LOSE_LIFE"]
        assert to and all(e["targeted"] and e["selector"]["targeted"] for e in to), name
    # a companion 'you gain' in the same clause stays untargeted
    you = [e for e in rec["Down, Down to Goblin-town"] if e["participant"] == "you"]
    assert you and all(e["targeted"] is False for e in you)


def test_repair2_two_target_players_each_draw_one():
    d = [e for e in _structured()["Gleaming Splendor"] if e["op"] == "DRAW"]
    assert len(d) == 1
    e = d[0]
    assert e["participant"] == "target_player" and e["participant"] != "you"
    assert e["targeted"] is True and e["affects_each"] is True
    assert e["participant_quantity"] == 2 and e["amount"] == "1"


def test_repair3_owner_participant_binding():
    d = [e for e in _structured()["Gandalf, Wandering Wizard"] if e["op"] == "DRAW"]
    assert d and d[0]["participant"] == "owner" and d[0]["amount"] == "3"


def test_repair4_quoted_granted_ability_is_not_an_immediate_effect():
    # Supper for Spiders' Food tokens have "... : You gain 3 life." — a granted ability, not a source effect
    assert not _structured().get("Supper for Spiders")


def test_repair5_replaced_would_draw_is_not_emitted_as_a_draw():
    d = [e for e in _structured()["Bard, King of Dale"] if e["op"] == "DRAW"]
    assert [e["amount"] for e in d] == ["2"]                # only the replacement 'draw two instead'
    assert d[0].get("replacement", {}).get("kind") == "draw_instead"


def test_repair6_modal_alternatives_carry_choice_metadata():
    recs = _structured()["Gollum, Riddle Master"]
    assert recs and all(e["mode"]["kind"] == "choose_one" and e["mode"]["exclusive"] for e in recs)
    idx = {e["mode"]["index"] for e in recs}
    assert len(idx) >= 2                                    # alternatives keep distinct mode indices


def test_repair_same_participant_binding_survives_targeting():
    # Reverent Howl still binds draw+lose-life to ONE target-player var, now targeted
    r = {e["op"]: e for e in _structured()["Reverent Howl"]}
    assert r["DRAW"]["participant_var"] == r["LOSE_LIFE"]["participant_var"]
    assert r["DRAW"]["targeted"] and r["LOSE_LIFE"]["targeted"]


# ================================================================================================
#  Phase 4a REPAIR 2 (review PHASE4_review_pt2) — per-op optionality + structured formula quantities
# ================================================================================================
def test_repair_pt2_optionality_does_not_leak_from_sibling_instruction():
    # Old Thrush: 'you gain 2 life. You may search …' — the life gain is MANDATORY
    gl = [e for e in _structured()["Old Thrush"] if e["op"] == "GAIN_LIFE"]
    assert gl and all(e["optional"] is False for e in gl)


def test_repair_pt2_draw_gated_by_optional_prior_action_is_conditional_not_optional():
    # 'you may discard/sacrifice … If you do, draw …' — mandatory draw gated by the optional action
    for name in ("Ragged Short Spear", "The Sackville-Bagginses"):
        d = [e for e in _structured()[name] if e["op"] == "DRAW"]
        assert d, name
        assert all(e["optional"] is False for e in d), name
        assert all((e.get("condition") or {}).get("kind") == "prior_action_taken" for e in d), name


def test_repair_pt2_for_each_draw_is_formulaic_not_fixed_one():
    # The Master of Lake-town: 'draw a card for each graveyard with seven or more cards in it'
    d = [e for e in _structured()["The Master of Lake-town"] if e["op"] == "DRAW"][0]
    assert d["amount"] != "1"                                  # not read as a total of one
    qf = d["quantity_formula"]
    assert qf["kind"] == "per_each" and qf["base"] == 1 and "graveyard" in qf["per"]


def test_repair_pt2_x_draw_carries_where_x_binding():
    for name, frag in (("Balin, Loremaster", "cards discarded"),
                       ("Uncover the Moon-Letters", "mana spent")):
        d = [e for e in _structured()[name] if e["op"] == "DRAW"][0]
        assert d["amount"] == "X", name
        qf = d["quantity_formula"]
        assert qf["kind"] == "variable" and qf["var"] == "X" and frag in qf["binding"], name


def test_repair_pt2_may_draw_is_still_optional():
    # Uncover: 'you may draw X cards' — the draw itself IS optional (may governs its own verb)
    d = [e for e in _structured()["Uncover the Moon-Letters"] if e["op"] == "DRAW"][0]
    assert d["optional"] is True

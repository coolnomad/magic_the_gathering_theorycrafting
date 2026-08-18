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
    assert d["amount"] == "variable" and "sacrificed creature" in d["scaling"]


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

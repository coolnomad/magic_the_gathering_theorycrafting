"""Effect-semantics Phase 4b: participant/resource DISCARD and MILL — graveyard-filling ops.

Both move cards into a graveyard (discard: hand→graveyard; mill: library→graveyard), are
participant-level and stochastic, so they never fan out to card pairs. Tests assert the GENERATED
structured records: participant identity, cost-vs-effect boundary, optionality, conditions, zones,
quantities, and the no-fan-out guard — while proving accepted Phase 4a draw/life is untouched."""

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


def _structured_by_name():
    out = {}
    for s in es.build_effects(write=False)["_structured"]:
        if s["selector"].get("participant_level"):
            out.setdefault(s["name"], []).append(s)
    return out


# ---- DISCARD effects --------------------------------------------------------------------------
def test_mandatory_edict_discard_by_each_opponent():
    d = _by_op("Stony-Voiced Goblins")["DISCARD"][0]
    assert d["participant"] == "each_opponent" and d["affects_each"] is True
    assert d["amount"] == "1" and d["optional"] is False
    assert (d["source_zone"], d["dest_zone"], d["event"]) == ("hand", "graveyard", "discard")


def test_optional_discard_your_hand():
    d = _by_op("Balin, Loremaster")["DISCARD"][0]
    assert d["participant"] == "you" and d["amount"] == "hand" and d["optional"] is True


def test_mandatory_then_discard_after_draw():
    for name in ("Thranduil, the Elvenking", "Confusticate and Bebother"):
        d = _by_op(name)["DISCARD"]
        assert len(d) == 1 and d[0]["amount"] == "1" and d[0]["optional"] is False, name


def test_discard_relation_and_zone():
    d = _by_op("Confusticate and Bebother")["DISCARD"][0]
    assert d["relation"] == "DISCARDS_CARDS"
    assert (d["source_zone"], d["dest_zone"], d["event"]) == ("hand", "graveyard", "discard")


# ---- DISCARD cost / condition guards ----------------------------------------------------------
def test_discard_activation_cost_is_not_an_effect():
    # 'Discard a card: Draw a card' / 'Discard a legendary card …: Draw two cards' are COSTS
    for name in ("Óin the Brave", "Key to the Side-Door"):
        assert not _by_op(name).get("DISCARD"), name
        # the paired draw effect is still present (Óin) / present after the cost (Key)
    assert _by_op("Óin the Brave").get("DRAW")


def test_if_you_discard_condition_is_not_a_second_discard():
    # Silvan Reveler: 'draw a card, then discard a card. If you discard a land card this way, put it …'
    d = _by_op("Silvan Reveler")["DISCARD"]
    assert len(d) == 1 and d[0]["optional"] is False


def test_that_player_discard_binds_to_prior_target_opponent():
    # Down, Down to Goblin-town: 'Target opponent reveals … That player discards that card.'
    d = _by_op("Down, Down to Goblin-town")["DISCARD"][0]
    assert d["participant"] == "target_opponent" and d["targeted"] is True and d["amount"] == "1"


# ---- MILL effects -----------------------------------------------------------------------------
def test_plain_mill_by_you():
    for name, n in (("Gleam of Death", "6"), ("Speak Secrets", "4"), ("Silvan Rally", "4")):
        m = _by_op(name)["MILL"][0]
        assert m["participant"] == "you" and m["amount"] == n
        assert (m["source_zone"], m["dest_zone"], m["event"]) == ("library", "graveyard", "mill")


def test_targeted_mill():
    m = _by_op("Master's Councillors")["MILL"][0]
    assert m["participant"] == "target_player" and m["targeted"] is True and m["amount"] == "3"


def test_variable_mill_binds_that_player_and_formula():
    # The Master of Lake-town: 'Whenever a player loses life, that player mills that many cards.'
    m = _by_op("The Master of Lake-town")["MILL"][0]
    assert m["participant"] == "that_player" and m["amount"] == "variable"
    assert m["quantity_formula"]["kind"] == "variable"


# ---- projection + invariants ------------------------------------------------------------------
def test_discard_and_mill_do_not_fan_out_to_card_pairs():
    pairs = es.build_effects(write=False)["_pairs"]
    assert not [p for p in pairs if p["relation"] in ("DISCARDS_CARDS", "MILLS_CARDS")]


def test_discard_mill_records_validate():
    for name in ("Stony-Voiced Goblins", "Gleam of Death", "The Master of Lake-town",
                 "Down, Down to Goblin-town"):
        for e in _part(name):
            assert sch.validate_effect(e) == [], (name, e["op"])


def test_accepted_phase4a_draw_life_records_are_unchanged():
    # Phase 4b must not perturb accepted draw/life records
    s = _structured_by_name()
    rh = {e["op"]: e for e in s["Reverent Howl"]}
    assert rh["DRAW"]["participant_var"] == rh["LOSE_LIFE"]["participant_var"]
    assert rh["DRAW"]["targeted"] and rh["DRAW"]["amount"] == "2"
    assert _by_op("Old Thrush")["GAIN_LIFE"][0]["optional"] is False

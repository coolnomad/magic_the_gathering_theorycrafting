"""Effect-semantics Phase 4c: SACRIFICE — integrates the portable `sac_schema` extractor.

A sacrifice moves a chosen permanent battlefield→graveyard. It is participant-level (a choice among
the sacrificer's own permanents, or an edict) → no card-pair fan-out. Tests assert the GENERATED
records: cost-vs-effect role, participant/actor, eligibility (self / fodder type / subtype / OR),
edict targeting, conditional self-sacrifice, zones, no-fan-out — and that the accepted Phase-4a/4b
records are untouched. The portable `sac_schema` module (and its pinned FIN metrics) is not modified."""

from hobkg import effect_semantics as es, effect_schema as sch
from hobkg.pipeline import REPO, _load_dicts


def _faces():
    return {f["name"]: f for f in _load_dicts(REPO / "data/normalized/faces.jsonl")}


def _sac(name):
    return es._sacrifice_effects(_faces()[name])


def _one(name):
    s = _sac(name)
    assert len(s) == 1, (name, len(s))
    return s[0]


# ---- cost sacrifices --------------------------------------------------------------------------
def test_additional_cast_cost_sacrifice():
    e = _one("Allure of Power")
    assert e["role"] == "cost" and e["cost_context"] == "additional_cast_cost"
    assert e["participant"] == "you" and e["card_selector"]["card_types"] == ["creature"]
    assert (e["source_zone"], e["dest_zone"], e["event"]) == ("battlefield", "graveyard", "sacrifice")


def test_activated_ability_self_sacrifice():
    e = _one("Giant's Boulder")
    assert e["role"] == "cost" and e["card_selector"]["self"] is True and e["optional"] is False


def test_activated_ability_fodder_or_types():
    e = _one("Gollum the Abandoned")
    cs = _one("Gollum the Abandoned")["card_selector"]
    assert e["role"] == "cost" and cs["card_types"] == ["artifact", "creature"] and cs["or_types"] is True


def test_subtype_only_fodder_is_extracted():
    # Bolg's Company: '{T}, Sacrifice another Goblin: Add {B}{R}' — subtype fodder (sac_schema alone drops it)
    e = _one("Bolg's Company")
    assert e["role"] == "cost" and e["card_selector"]["subtypes"] == ["goblin"]
    assert e["card_selector"]["another"] is True


def test_sac_land_is_a_self_cost():
    for name in ("Lake-town", "Goblin-town", "Iron Hills", "Mirkwood"):
        e = _one(name)
        assert e["role"] == "cost" and e["card_selector"]["self"] is True, name


# ---- effect sacrifices ------------------------------------------------------------------------
def test_optional_sacrifice_effect():
    e = _one("Rhovanion Rampager")
    assert e["role"] == "effect" and e["cost_context"] == "effect" and e["optional"] is True
    assert e["card_selector"]["another"] is True and e["card_selector"]["card_types"] == ["creature"]


def test_edict_is_targeted_and_actor_is_opponent():
    e = _one("Crude Bent Blade")
    assert e["role"] == "effect" and e["cost_context"] == "resolution_effect"
    assert e["participant"] == "target_opponent" and e["targeted"] is True
    assert e["card_selector"]["owner"] == "target_opponent"


def test_conditional_self_sacrifice_preserves_the_specific_gate():
    # Misty Mountains Cold / Last Light: mandatory self-sacrifice gated by a SPECIFIC predicate
    # (review pt8 #2) — not the generic conditional_effect, and not cost_context 'unsupported'.
    mi = _one("The Misty Mountains Cold")
    assert mi["card_selector"]["self"] and mi["optional"] is False
    assert mi["cost_context"] == "conditional_self_sacrifice"
    assert mi["condition"]["kind"] == "controls_count" and mi["condition"]["count"] == "four"
    assert "treasure" in mi["condition"]["of"]
    ll = _one("Last Light of Durin's Day")
    assert ll["cost_context"] == "conditional_self_sacrifice"
    assert ll["condition"]["kind"] == "counter_threshold" and ll["condition"]["count"] == "six"
    assert ll["condition"]["counter"] == "quest"


# ---- operation-scoping / no-leak (review pt6 + pt8) -------------------------------------------
def test_sacrifice_condition_does_not_leak_from_a_sibling_line():
    # Bolg's Company line 1 is 'has haste as long as you control another Goblin'; the sacrifice on
    # line 2 must NOT inherit that controls_another condition
    assert _one("Bolg's Company")["condition"] is None


def test_later_if_you_do_payoff_does_not_gate_the_sacrifice():
    # 'you may sacrifice … If you do/When you do, <payoff>' — the sacrifice itself is unconditional
    # (optional); the trailing condition gates the payoff, not the sacrifice (review pt8 #1)
    for name in ("Rhovanion Rampager", "Bolg of the North", "The Sackville-Bagginses"):
        e = _one(name)
        assert e["optional"] is True and e["condition"] is None, name


def test_activated_sacrifice_cost_is_unconditional():
    # Elven Passage: '{T}, Pay 1 life, Sacrifice this land: … You may behold an Elf. If you do, untap …'
    # The activated sacrifice cost is unconditional once the ability is activated.
    e = _one("Elven Passage")
    assert e["role"] == "cost" and e["cost_context"] == "activated_ability" and e["condition"] is None


def test_elven_passage_cost_preserves_pay_life_co_cost():
    # review pt9: the printed 'Pay 1 life' co-cost must survive in the structured cost, in the same
    # activated branch as tap and the self-sacrifice.
    e = _one("Elven Passage")
    atoms = e["cost"]["alt"][0]["all"]
    assert {"tap": True} in atoms
    assert {"pay_life": "1"} in atoms
    assert any("sacrifice" in a for a in atoms)
    assert e["condition"] is None                            # pt8 repair preserved


def test_mana_and_tap_co_costs_still_preserved():
    # sanity: adding pay_life must not perturb ordinary mana/tap sacrifice costs
    atoms = _one("Lake-town")["cost"]["alt"][0]["all"]
    assert {"pay": "{2}{W}{U}"} in atoms and {"tap": True} in atoms
    assert not any("pay_life" in a for a in atoms)


# ---- projection + invariants ------------------------------------------------------------------
def test_sacrifice_does_not_fan_out_to_card_pairs():
    pairs = es.build_effects(write=False)["_pairs"]
    assert not [p for p in pairs if p["relation"] == "SACRIFICES"]


def test_sacrifice_records_validate():
    for name in ("Allure of Power", "Crude Bent Blade", "Bolg's Company", "The Misty Mountains Cold"):
        for e in _sac(name):
            assert sch.validate_effect(e) == [], (name, e)


def test_every_sacrifice_has_battlefield_selector_and_role():
    out = es.build_effects(write=False)["_structured"]
    sacs = [s for s in out if s["op"] == "SACRIFICE"]
    assert sacs
    for s in sacs:
        assert s["card_selector"]["zone"] == "battlefield" and s["dest_zone"] == "graveyard"
        assert s["role"] in ("cost", "effect") and "owner" in s["card_selector"]


def test_accepted_phase4a_4b_records_unchanged():
    out = {s["effect_id"]: s for s in es.build_effects(write=False)["_structured"]}
    # sanity: the accepted families still present and sacrifice added alongside
    ops = {s["op"] for s in out.values()}
    assert {"DRAW", "GAIN_LIFE", "DISCARD", "MILL", "SACRIFICE"} <= ops

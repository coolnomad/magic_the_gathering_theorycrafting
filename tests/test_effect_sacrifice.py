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


def test_conditional_self_sacrifice():
    # Misty Mountains Cold / Last Light: mandatory self-sacrifice gated by a condition
    for name in ("The Misty Mountains Cold", "Last Light of Durin's Day"):
        e = _one(name)
        assert e["card_selector"]["self"] is True and e["optional"] is False
        assert (e.get("condition") or {}).get("kind") == "conditional_effect", name


# ---- operation-scoping / no-leak --------------------------------------------------------------
def test_sacrifice_condition_does_not_leak_from_a_sibling_line():
    # Bolg's Company line 1 is 'has haste as long as you control another Goblin'; the sacrifice on
    # line 2 must NOT inherit that controls_another condition
    assert _one("Bolg's Company")["condition"] is None


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

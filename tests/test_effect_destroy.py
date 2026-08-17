"""Effect-semantics Phase 2: structured targeted-destruction family (CAN_DESTROY), with the
mandated regression + false-positive cases from the instructions."""

import json
import io

from hobkg import effect_semantics as es, effect_schema as sch, coverage
from hobkg.pipeline import REPO, _load_dicts

G = REPO / "data/graph_global"


def _setup():
    es.build_effects()
    faces = _load_dicts(REPO / "data/normalized/faces.jsonl")
    by_card, n2c, cid2name = {}, {}, {}
    for f in faces:
        by_card.setdefault(f["card_id"], []).append(f)
        n2c[f["name"]] = f["card_id"]
        cid2name.setdefault(f["card_id"], f["name"])
    pairs = _load_dicts(G / "card_pair_projection_effect.jsonl")
    structured = _load_dicts(G / "effect_destroy.jsonl")
    return by_card, n2c, cid2name, pairs, structured


def _targets(pairs, n2c, src):
    return {p["target_card"] for p in pairs if p["source_card"] == n2c[src] and p["relation"] == "CAN_DESTROY"}


def test_destroy_is_deterministic():
    es.build_effects()
    a = (G / "card_pair_projection_effect.jsonl").read_bytes()
    es.build_effects()
    assert (G / "card_pair_projection_effect.jsonl").read_bytes() == a


def test_bilbo_and_stir_destroy_all_creatures():
    by_card, n2c, cid2name, pairs, _ = _setup()
    creatures = {c for c, fs in by_card.items() if any("Creature" in (f.get("type_line") or {}).get("types", []) for f in fs)}
    assert _targets(pairs, n2c, "Bilbo's Deadly Slice") == creatures
    assert _targets(pairs, n2c, "Stir Up Trouble") == creatures


def test_warg_tactics_mode1_only_flying_and_is_modal():
    by_card, n2c, cid2name, pairs, structured = _setup()
    tgts = _targets(pairs, n2c, "Warg Tactics")
    assert tgts and all(any(sch._kw(cf, "flying") for cf in by_card[t]) for t in tgts)
    # NEGATIVE: cannot destroy a nonflying creature
    nonflyer = next(c for c, fs in by_card.items()
                    if any("Creature" in (f.get("type_line") or {}).get("types", []) for f in fs)
                    and not any(sch._kw(cf, "flying") for cf in fs))
    assert nonflyer not in tgts
    # the destroy is mode 0 of a choose_one (modal, not unconditional)
    wt = [s for s in structured if s["name"] == "Warg Tactics"]
    assert wt and wt[0]["mode"]["kind"] == "choose_one"


def test_stone_by_sunlight_power_threshold_and_no_reminder_false_positive():
    by_card, n2c, cid2name, pairs, structured = _setup()
    tgts = _targets(pairs, n2c, "Stone by Sunlight")
    assert tgts and all(any((sch._power(cf) or 0) >= 4 for cf in by_card[t]) for t in tgts)
    # its mode-2 reminder ('effects that say "destroy" don't destroy it') must NOT be extracted
    stone = [s for s in structured if s["name"] == "Stone by Sunlight"]
    assert len(stone) == 1 and stone[0]["selector"]["predicates"].get("power_ge") == 4


def test_pinecone_token_mode_does_not_hit_nontoken_artifacts():
    by_card, n2c, cid2name, pairs, structured = _setup()
    # NEGATIVE: Pinecone's artifact-token destroy projects to NO nontoken artifact cards
    assert _targets(pairs, n2c, "Pinecone Strike") == set()
    pine = [s for s in structured if s["name"] == "Pinecone Strike"][0]
    assert pine["selector"]["predicates"].get("token") is True
    assert pine["eligible_token_specs"]                       # it DOES point at artifact token specs


def test_giant_boulder_destroys_any_permanent_and_thorin_is_modal():
    by_card, n2c, cid2name, pairs, structured = _setup()
    perms = {c for c, fs in by_card.items()
             if any(set((f.get("type_line") or {}).get("types", [])) &
                    {"Creature", "Artifact", "Enchantment", "Land", "Planeswalker", "Battle"} for f in fs)}
    assert _targets(pairs, n2c, "Giant's Boulder") == perms
    thorin = [s for s in structured if s["name"] == "Thorin's Last Stand"]
    assert thorin and thorin[0]["mode"]["kind"] == "choose_one"  # destroy is one modal branch
    assert set(thorin[0]["selector"]["card_types"]) == {"artifact", "enchantment"}


def test_all_explicit_target_destroys_are_targeted():
    # BLOCKING bug fix: 'destroy target …' effects must be targeted:true (interacts with hexproof/ward)
    _, _, _, _, structured = _setup()
    by = {s["name"]: s for s in structured}
    for nm in ["Bilbo's Deadly Slice", "Stir Up Trouble", "Warg Tactics", "Stone by Sunlight",
               "Pinecone Strike", "Thorin's Last Stand", "Burn, Burn, Tree and Fern",
               "Giant's Boulder", "Azog, Moria's Ruin"]:
        assert by[nm]["targeted"] is True and by[nm]["selector"]["targeted"] is True, nm
    # NEGATIVE: The Black Arrow's conditional 'destroy it' is NOT independently targeted
    assert by["The Black Arrow"]["targeted"] is False and by["The Black Arrow"]["affects_each"] is False


def test_black_arrow_pronoun_binds_to_antecedent_dragon():
    _, _, _, _, structured = _setup()
    ba = next(s for s in structured if s["name"] == "The Black Arrow")
    b = ba["binding"]
    assert b and b["kind"] == "antecedent" and b["via"] == "dealt damage this way"
    assert b["restriction"]["subtypes"] == ["dragon"]
    assert b["var"] == ba["selector"]["var"]                # destroys the SAME object dealt damage


def test_type_conjunction_or_vs_and():
    # 'artifact or enchantment' = OR (any); 'artifact creature' = AND (both)
    art = {"type_line": {"types": ["Artifact"]}}
    artcre = {"type_line": {"types": ["Artifact", "Creature"]}}
    or_sel = sch.selector("artifact or enchantment")
    assert or_sel["or_types"] and sch.matches_card(or_sel, art)
    and_sel = sch.selector("artifact creature")
    assert not and_sel["or_types"]
    assert sch.matches_card(and_sel, artcre) and not sch.matches_card(and_sel, art)


def test_supertypes_populated_and_enforced():
    sel = sch.selector("legendary creature")
    assert sel["supertypes"] == ["legendary"]
    legend = {"type_line": {"types": ["Creature"], "supertypes": ["Legendary"]}}
    plain = {"type_line": {"types": ["Creature"], "supertypes": []}}
    assert sch.matches_card(sel, legend) and not sch.matches_card(sel, plain)


def test_effect_records_validate_and_carry_full_schema():
    _, _, _, _, structured = _setup()
    for s in structured:
        assert sch.validate_effect(s) == []                 # every emitted record is schema-valid
        for k in ("participant", "mode", "condition", "duration", "attempt", "zone_transition"):
            assert k in s
    # a malformed record is rejected
    assert sch.validate_effect({"op": "DESTROY"}) != []


def test_multimode_extraction_and_supports_aggregation():
    # multimode extraction: a synthetic two-mode destroy yields two effects with distinct mode indices
    effs = es._destroy_effects({"id": "face:test:0", "name": "T",
                                "oracle_text": "Choose one —\n• Destroy target creature.\n• Destroy target artifact."})
    assert len(effs) == 2 and {e["mode"]["index"] for e in effs} == {0, 1}
    # real pairs aggregate supporting effects rather than discarding them
    _, _, _, pairs, _ = _setup()
    assert pairs and all(isinstance(p["supports"], list) and p["supports"] for p in pairs)
    assert all("effect_id" in sup and "mode" in sup for p in pairs for sup in p["supports"])


def test_effect_layer_composed_into_pair_index():
    _setup(); coverage.pair_index()
    n2c = {}
    for f in _load_dicts(REPO / "data/normalized/faces.jsonl"):
        n2c[f["name"]] = f["card_id"]
    idx = {(r["source_card"], r["target_card"]): r for r in _load_dicts(G / "pair_index.jsonl")}
    # a Bilbo->creature pair carries CAN_DESTROY in the effect_semantics column
    row = next(r for (s, t), r in idx.items() if s == n2c["Bilbo's Deadly Slice"] and r.get("effect_semantics"))
    assert "CAN_DESTROY" in row["effect_semantics"]

"""Additive audit_repair layer: applies the human gold-set audit corrections at the object-class
level, derives eligible pairs mechanically (no per-pair hard-coding), and suppresses/retypes wrong
relations — all without touching the frozen core graph."""

import io
import json

from hobkg import audit_repair, coverage
from hobkg.pipeline import REPO, _load_dicts

G = REPO / "data/graph_global"


def _n2c():
    m = {}
    for f in _load_dicts(REPO / "data/normalized/faces.jsonl"):
        m[f["name"]] = f["card_id"]
    return m


def _pair_index():
    return {(r["source_card"], r["target_card"]): r
            for r in _load_dicts(G / "pair_index.jsonl")}


def test_materialize_is_object_class_and_generic():
    s = audit_repair.materialize()
    assert s["class_edges"] == 6                      # one canonical edge per corrected mechanism
    assert s["derived_pairs"] == 462 and s["suppressions"] == 34
    pairs = _load_dicts(G / "card_pair_projection_audit_repair.jsonl")
    assert pairs and all(p["generic"] and p["origin"] == "audit_repair" for p in pairs)
    assert all(not p["self_pair"] for p in pairs)     # a class expansion never yields a self-pair
    # counts follow eligibility, not a hand-picked pair list
    from collections import Counter
    by = Counter(p["relation"] for p in pairs)
    assert by["MODIFIES"] == 223 and by["ADDS_COUNTER"] == 111
    assert by["SUPPLIES_RESOURCE"] == 48 and by["ENABLES_TRIGGER"] == 80


def test_suppressions_remove_the_wrong_relations():
    audit_repair.materialize(); coverage.pair_index()
    n2c, idx = _n2c(), _pair_index()

    def lay(sname, tname, layer):
        return idx.get((n2c[sname], n2c[tname]), {}).get(layer, [])
    # #111 false self-loop gone
    assert "ENABLES_TRIGGER" not in lay("Head of the Hunt", "Head of the Hunt", "mechanical")
    # #58 coincidental resource supply gone (the real cast-trigger relation remains in mechanism)
    assert "SUPPLIES_RESOURCE" not in lay("Plunder the Trollshaws", "Uncover the Moon-Letters", "mechanical")
    assert "ENABLES_TRIGGER" in lay("Plunder the Trollshaws", "Uncover the Moon-Letters", "mechanism")


def test_kili_tribal_entry_is_retyped_not_duplicated():
    audit_repair.materialize(); coverage.pair_index()
    n2c, idx = _n2c(), _pair_index()
    r = idx[(n2c["Nori, Teller of Tales"], n2c["Kíli the Resourceful"])]
    assert "SUPPLIES_RESOURCE" not in r["mechanism"]   # old mis-type suppressed
    assert "ENABLES_TRIGGER" in r["audit_repair"]      # correct relation added
    # every Dwarf/Equipment source is retyped, derived from card types (not enumerated by hand)
    ar = _load_dicts(G / "card_pair_projection_audit_repair.jsonl")
    kili = n2c["Kíli the Resourceful"]
    et_sources = {p["source_card"] for p in ar if p["target_card"] == kili and p["relation"] == "ENABLES_TRIGGER"}
    assert len(et_sources) == 32                       # 33 Dwarf/Equipment cards minus Kíli itself


def test_anthem_derives_all_creatures_and_only_creatures():
    audit_repair.materialize()
    ar = _load_dicts(G / "card_pair_projection_audit_repair.jsonl")
    n2c = _n2c()
    ark = n2c["The Arkenstone"]
    mod_targets = {p["target_card"] for p in ar if p["source_card"] == ark and p["relation"] == "MODIFIES"}
    creatures = audit_repair._Cards(REPO).creatures()
    assert mod_targets == (creatures - {ark})          # exactly the creatures, minus self, nothing else
    # the same card's tutor (Seek the Heart face) supplies only legendary creatures
    sup = {p["target_card"] for p in ar if p["source_card"] == ark and p["relation"] == "SUPPLIES_RESOURCE"}
    assert sup == audit_repair._Cards(REPO).legendary_creatures() - {ark}


def test_frozen_core_untouched_and_deterministic():
    # audit_repair writes ONLY its own files; core nodes/edges are not among its outputs
    before = (G / "edges.jsonl").read_bytes()
    audit_repair.materialize()
    a = (G / "card_pair_projection_audit_repair.jsonl").read_bytes()
    audit_repair.materialize()
    assert (G / "card_pair_projection_audit_repair.jsonl").read_bytes() == a   # deterministic
    assert (G / "edges.jsonl").read_bytes() == before                          # frozen core untouched

"""Query interface (spec §CLI + completion criterion): a human can inspect any pair and see
relation type, direction, conditions, intermediate nodes, provenance, and inference origin."""

from hobkg import query
from hobkg.pipeline import REPO, _load_dicts


def _recruit_card_name():
    mech = {}
    for m in _load_dicts(REPO / "data/rules/mechanics.jsonl"):
        mech.setdefault(m["mechanic"], set()).add(m["card_id"])
    names = {c["id"]: c["name"] for c in _load_dicts(REPO / "data/normalized/cards.jsonl")}
    # a Recruit card that actually projects to Councillors (has the shared recruit draw)
    mrel = list(_load_dicts(REPO / "data/graph_global/card_pair_projection_mechanism.jsonl"))
    mc = next(c["id"] for c in _load_dicts(REPO / "data/normalized/cards.jsonl")
              if c["name"] == "Master's Councillors")
    src = next(m["source_card"] for m in mrel if m["target_card"] == mc and m["source_card"] in mech["Recruit"])
    return names[src]


def test_query_pair_recruit_to_councillors_full_detail():
    out = query.query_pair(_recruit_card_name(), "Master's Councillors")
    # relation type + direction + inference origin + condition + intermediate nodes all present
    assert "ENABLES_TRIGGER" in out
    assert "mechanism-repair" in out                       # inference origin shown
    assert "cond:draw-is-second-this-turn" in out          # the second-draw condition
    assert "gate:second-draw" in out                       # an intermediate node on the path
    assert "--TRIGGERS-->" in out                          # path is rendered with predicates
    # the reverse direction is empty (Councillors does not affect Recruit)
    assert "0 relation(s)" in out


def test_query_pair_dwarf_to_dains_company():
    out = query.query_pair("Balin, Loremaster", "Dáin's Company")
    assert "SUPPLIES_RESOURCE" in out and "obj:subtype:dwarf" in out


def test_query_pair_empty_pair_is_explicit():
    out = query.query_pair("Island", "Forest")
    assert "no mechanistic relation" in out.lower() or "0 relation(s)" in out


def test_query_card_lists_faces_and_relations():
    out = query.query_card("Bothersome Noisemaker")
    assert "Bothersome Noisemaker" in out and "face:" in out
    assert "Incoming relations" in out and "ENABLES_TRIGGER" in out


def test_query_mechanism_resolves_gate_and_lists_on_miss():
    out = query.query_mechanism("gate:second-draw")
    assert "gate:second-draw" in out and "anchors" in out
    miss = query.query_mechanism("no-such-mechanism-xyz")
    assert "no mechanism module matches" in miss and "Available:" in miss


def test_resolve_unknown_and_ambiguous():
    assert query.query_card("zzz-not-a-card") .startswith("no card matches")

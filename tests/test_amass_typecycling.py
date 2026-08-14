"""Amass and typecycling templates (closure pass): parameterized, existing predicates,
invoked per card via INSTANTIATES — NO `AMASSES`/`TYPECYCLES` primitive predicate."""

from hobkg import rules
from hobkg.models import Predicate
from typing import get_args


def _gb():
    gb = rules.GraphBuilder()
    rules.add_shared_nodes(gb)
    return gb


def _has(gb, pred, src=None, tgt=None):
    return any(e.predicate == pred and (src is None or e.source == src)
               and (tgt is None or e.target == tgt) for e in gb.edges)


def test_no_amass_or_typecycling_primitive_predicate():
    preds = set(get_args(Predicate))
    assert "AMASSES" not in preds
    assert "TYPECYCLES" not in preds


def test_amass_generic_conditional_sequence():
    gb = _gb()
    # if no Army -> create the 0/0 Army token (conditional); then add +1/+1 counters
    create = [e for e in gb.edges if e.predicate == "CREATES_OBJECT"
              and e.source == "gate:amass-no-army" and e.target == "token:army"]
    assert create and create[0].condition_ids == ["cond:amass-no-army"]
    assert _has(gb, "CAUSES", "op:amass", "op:amass:add-counters")
    assert _has(gb, "ADDS_COUNTER", "op:amass:add-counters", "counter:+1/+1")
    assert _has(gb, "REFERENCES_RULE", "op:amass", "rule:amass")


def test_amass_instantiation_supplies_params():
    gb = _gb()
    face = {"id": "face:a:0", "card_id": "card:a", "name": "Amasser",
            "oracle_text": "When this enters, amass Goblins 2."}
    rules.expand_amass(gb, face, "Goblin", "2")
    op = gb.nodes["op:face:a:0:amass"]
    assert op.data == {"army_subtype": "Goblin", "n": "2"}
    assert _has(gb, "INSTANTIATES", "op:face:a:0:amass", "op:amass")
    assert _has(gb, "HAS_ABILITY", "face:a:0", "op:face:a:0:amass")


def test_typecycling_generic_and_instantiation():
    gb = _gb()
    assert _has(gb, "MOVES_TO", "op:typecycling", "zone:graveyard")       # discard cost
    assert _has(gb, "MOVES_FROM", "op:typecycling:search", "zone:library")
    assert _has(gb, "MOVES_TO", "op:typecycling:search", "zone:hand")
    face = {"id": "face:h:0", "card_id": "card:h", "name": "Hole",
            "oracle_text": "Halflingcycling {4} ({4}, Discard this card: Search...)"}
    rules.expand_typecycling(gb, face, "Halfling")
    assert gb.nodes["op:face:h:0:typecycling"].data == {"search_type": "Halfling"}
    assert _has(gb, "INSTANTIATES", "op:face:h:0:typecycling", "op:typecycling")

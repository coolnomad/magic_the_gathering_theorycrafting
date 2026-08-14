"""Amass and typecycling templates (closure pass): parameterized, object-bound,
existing predicates, invoked per card via INSTANTIATES — NO `AMASSES` primitive."""

from typing import get_args

from hobkg import rules
from hobkg.models import Predicate


def _gb():
    gb = rules.GraphBuilder()
    rules.add_shared_nodes(gb)
    return gb


def _has(gb, pred, src=None, tgt=None):
    return any(e.predicate == pred and (src is None or e.source == src)
               and (tgt is None or e.target == tgt) for e in gb.edges)


def test_no_amass_or_typecycling_primitive_predicate():
    preds = set(get_args(Predicate))
    assert "AMASSES" not in preds and "TYPECYCLES" not in preds


def test_amass_is_object_bound_on_army_A():
    gb = _gb()
    # the created Army, the selected Army, and the counter target are the SAME node
    create = [e for e in gb.edges if e.predicate == "CREATES_OBJECT"
              and e.source == "gate:amass-no-army" and e.target == "obj:army-A"]
    assert create and create[0].condition_ids == ["cond:amass-no-army"]
    assert _has(gb, "REQUIRES", "op:amass:select", "obj:army-A")        # select the same A
    assert _has(gb, "HAS_STATE", "obj:army-A", "state:army-A:counters")
    assert _has(gb, "HAS_COUNTER_TYPE", "state:army-A:counters", "counter:+1/+1")
    assert _has(gb, "MODIFIES", "op:amass:add-counters", "state:army-A:counters")  # add N to A's count
    assert _has(gb, "HAS_TYPE", "obj:army-A", "obj:army")               # A is an Army (subtype per instance)
    # sequencing: amass -> select -> add-counters
    assert _has(gb, "CAUSES", "op:amass", "op:amass:select")
    assert _has(gb, "CAUSES", "op:amass:select", "op:amass:add-counters")


def test_amass_instantiation_propagates_subtype_and_N():
    gb = _gb()
    face = {"id": "face:a:0", "card_id": "card:a", "name": "Amasser",
            "oracle_text": "When this enters, amass Goblins 2."}
    rules.expand_amass(gb, face, "Goblin", "2")
    op = gb.nodes["op:face:a:0:amass"]
    assert op.data == {"army_subtype": "Goblin", "n": "2"}   # params live on the instance
    assert _has(gb, "INSTANTIATES", "op:face:a:0:amass", "op:amass")
    assert _has(gb, "HAS_ABILITY", "face:a:0", "op:face:a:0:amass")


def test_typecycling_complete_costs_requirement_reveal_shuffle():
    gb = _gb()
    assert _has(gb, "HAS_COST", "op:typecycling", "cost:cycling")           # mana cost
    assert _has(gb, "MOVES_TO", "op:typecycling", "zone:graveyard")         # discard this card
    assert _has(gb, "REQUIRES", "op:typecycling:search", "obj:searched-type")
    assert _has(gb, "MOVES_FROM", "op:typecycling:search", "zone:library")
    assert _has(gb, "MOVES_TO", "op:typecycling:search", "zone:hand")
    assert _has(gb, "CAUSES", "op:typecycling:search", "op:typecycling:reveal")
    assert _has(gb, "CAUSES", "op:typecycling:search", "op:typecycling:shuffle")
    face = {"id": "face:h:0", "card_id": "card:h", "name": "Hole",
            "oracle_text": "Halflingcycling {4} ({4}, Discard this card: Search...)"}
    rules.expand_typecycling(gb, face, "Halfling")
    assert gb.nodes["op:face:h:0:typecycling"].data == {"search_type": "Halfling"}
    assert _has(gb, "INSTANTIATES", "op:face:h:0:typecycling", "op:typecycling")

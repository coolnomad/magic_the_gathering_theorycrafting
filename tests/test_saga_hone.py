"""Saga and hone templates, with the pt2-review fixes: exact Saga chapter-transition
conditions, and hone counters/bonus bound to the same Equipment variable."""

from hobkg import rules


def _gb():
    gb = rules.GraphBuilder()
    rules.add_shared_nodes(gb)
    return gb


def _edges(gb, pred, src=None, tgt=None):
    return [e for e in gb.edges if e.predicate == pred and (src is None or e.source == src)
            and (tgt is None or e.target == tgt)]


def _has(gb, pred, src=None, tgt=None):
    return bool(_edges(gb, pred, src, tgt))


def test_saga_chapter_transition_conditions():
    gb = _gb()
    face = {"id": "face:s:0", "card_id": "card:s", "name": "A Saga",
            "oracle_text": "I — Draw a card.\nII — Create a token.\nIII — Deal 3 damage."}
    rules.expand_saga(gb, face)
    lore = "state:face:s:0:lore-count"
    for n in (1, 2, 3):
        ab = f"ab:face:s:0:chapter-{n}"
        en = _edges(gb, "ENABLES", lore, ab)
        assert en, f"missing ENABLES for chapter {n}"
        cid = en[0].condition_ids[0]
        cond = gb.conditions[cid]
        assert cond.expression["condition_type"] == "state_transition_equals"
        assert cond.expression["accepted_values"] == [n]
        assert cond.expression["state"] == lore
    # sacrifice fires off the final chapter only
    assert gb.nodes["op:face:s:0:sacrifice"].data["after_chapter"] == 3
    assert _has(gb, "CAUSES", "ab:face:s:0:chapter-3", "op:face:s:0:sacrifice")


def test_saga_multi_number_chapter():
    gb = _gb()
    face = {"id": "face:m:0", "card_id": "card:m", "name": "Multi",
            "oracle_text": "I, II — Add a counter.\nIII — Sacrifice."}
    rules.expand_saga(gb, face)
    cond = gb.conditions["cond:face:m:0:chapter-1-2"]
    assert cond.expression["accepted_values"] == [1, 2]
    assert gb.nodes["op:face:m:0:sacrifice"].data["after_chapter"] == 3


def test_hone_counter_and_bonus_share_equipment():
    gb = _gb()
    # generic binding: E has a hone-count state, E is attached to C, boost scales with
    # E's count and modifies C — all referencing the same Equipment variable.
    assert _has(gb, "HAS_STATE", "obj:equipment-E", "state:hone-count:E")
    assert _has(gb, "HAS_COUNTER_TYPE", "state:hone-count:E", "counter:hone")
    assert _has(gb, "ATTACHED_TO", "obj:equipment-E", "obj:creature-C")
    assert _has(gb, "SCALES_WITH", "effect:hone-boost", "state:hone-count:E")
    assert _has(gb, "MODIFIES", "effect:hone-boost", "obj:creature-C")


def test_hone_add_increments_that_equipments_count():
    gb = _gb()
    for h in ("x", "y"):
        rules.expand_hone(gb, {"id": f"face:{h}:0", "card_id": f"card:{h}", "name": h,
                               "oracle_text": "put a hone counter on target Equipment."})
    # each placer increments the (bound) Equipment's hone-count state; generic boost once
    for h in ("x", "y"):
        assert _has(gb, "MODIFIES", f"op:face:{h}:0:add-hone", "state:hone-count:E")
    assert len(_edges(gb, "SCALES_WITH", "effect:hone-boost", "state:hone-count:E")) == 1
    # bonus never attached to a source card/face
    assert gb.nodes["effect:hone-boost"].data["target"] == "obj:creature-C"

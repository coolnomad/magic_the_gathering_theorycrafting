"""Saga and hone templates, with the review's object-identity fixes."""

from hobkg import rules


def _gb():
    gb = rules.GraphBuilder()
    rules.add_shared_nodes(gb)
    return gb


def _has(gb, pred, src=None, tgt=None):
    return any(e.predicate == pred and (src is None or e.source == src)
               and (tgt is None or e.target == tgt) for e in gb.edges)


def test_saga_lore_bound_to_own_object():
    gb = _gb()
    face = {"id": "face:s:0", "card_id": "card:s", "name": "A Saga",
            "oracle_text": "I — Draw a card.\nII — Create a token.\nIII — Deal 3 damage."}
    rules.expand_saga(gb, face)
    lore = "state:face:s:0:lore-count"
    assert lore in gb.nodes and gb.nodes[lore].data["object"] == "face:s:0"
    # lore ops modify THIS saga's own count; the count enables THIS saga's own chapters
    assert _has(gb, "MODIFIES", "op:face:s:0:add-lore-etb", lore)
    assert _has(gb, "HAS_COUNTER_TYPE", lore, "counter:lore")
    for n in (1, 2, 3):
        assert _has(gb, "ENABLES", lore, f"ab:face:s:0:chapter-{n}")
    # the generic counter:lore type must NOT directly enable chapters
    assert not _has(gb, "ENABLES", "counter:lore")
    assert gb.nodes["op:face:s:0:sacrifice"].data["after_chapter"] == 3
    assert _has(gb, "MOVES_TO", "op:face:s:0:sacrifice", "zone:graveyard")


def test_two_sagas_have_separate_lore_states():
    gb = _gb()
    for s in ("a", "b"):
        rules.expand_saga(gb, {"id": f"face:{s}:0", "card_id": f"card:{s}", "name": s,
                               "oracle_text": "I — Do a thing.\nII — Do another."})
    assert "state:face:a:0:lore-count" in gb.nodes
    assert "state:face:b:0:lore-count" in gb.nodes
    # a's lore op must not touch b's state
    assert not _has(gb, "MODIFIES", "op:face:a:0:add-lore-etb", "state:face:b:0:lore-count")


def test_hone_generic_once_and_not_on_source_card():
    gb = _gb()
    # generic boost exists once regardless of how many cards place hone counters
    for h in ("x", "y", "z"):
        rules.expand_hone(gb, {"id": f"face:{h}:0", "card_id": f"card:{h}", "name": h,
                               "oracle_text": "put a hone counter on target Equipment."})
    produces = [e for e in gb.edges if e.predicate == "PRODUCES" and e.source == "counter:hone"
                and e.target == "effect:hone-boost"]
    assert len(produces) == 1
    assert gb.nodes["effect:hone-boost"].data["target"] == "attached_creature"
    # each card places a counter and references the rule; no per-card boost duplication
    for h in ("x", "y", "z"):
        assert _has(gb, "ADDS_COUNTER", f"op:face:{h}:0:add-hone", "counter:hone")
        assert _has(gb, "REFERENCES_RULE", f"op:face:{h}:0:add-hone", "rule:hone")

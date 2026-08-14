"""Recruit template — invariant #1 (draw then discard; Soldier conditional on nonland
discard) plus the review fix: a single generic template, invoked per card, with exactly
ONE create-Soldier edge (not one per Recruit card)."""

from hobkg import rules


def _gb():
    gb = rules.GraphBuilder()
    rules.add_shared_nodes(gb)
    return gb


def _edge(gb, pred, src=None, tgt=None):
    return [e for e in gb.edges if e.predicate == pred
            and (src is None or e.source == src) and (tgt is None or e.target == tgt)]


def test_generic_draw_then_discard_ordering():
    gb = _gb()
    assert gb.nodes["op:recruit:draw"].data["quantity"] == 1
    assert gb.nodes["op:recruit:discard"].data["quantity"] == 1
    assert _edge(gb, "CAUSES", "op:recruit", "op:recruit:draw")
    after = _edge(gb, "CAUSES", "op:recruit:draw", "op:recruit:discard")
    assert after and after[0].timing == "after"
    assert _edge(gb, "MOVES_TO", "op:recruit:discard", "zone:graveyard")


def test_soldier_created_once_and_conditionally():
    gb = _gb()
    create = _edge(gb, "CREATES_OBJECT", "gate:recruit-nonland-discard", "token:human-soldier")
    assert len(create) == 1
    assert create[0].condition_ids == ["cond:recruit-nonland-discard"]


def test_per_card_recruit_instantiates_generic_only():
    # Instantiating Recruit on many cards must NOT add more create-Soldier edges.
    gb = _gb()
    for i in range(5):
        rules.expand_recruit(gb, {"id": f"face:{i}:0", "card_id": f"card:{i}",
                                  "name": f"C{i}", "oracle_text": "...recruit."})
    create = _edge(gb, "CREATES_OBJECT", "gate:recruit-nonland-discard", "token:human-soldier")
    assert len(create) == 1  # still exactly one
    for i in range(5):
        assert _edge(gb, "INSTANTIATES", f"op:face:{i}:0:recruit", "op:recruit")
        assert _edge(gb, "HAS_ABILITY", f"face:{i}:0", f"op:face:{i}:0:recruit")


def test_draw_produces_a_draw_event():
    gb = _gb()
    assert _edge(gb, "PRODUCES", "op:recruit:draw", "event:card-drawn")

"""Recruit template — spec semantic invariant #1: Recruit always yields draw then
discard; Soldier creation is conditional on a nonland discard."""

from hobkg import rules


def _gb_with_recruit():
    gb = rules.GraphBuilder()
    rules.add_shared_nodes(gb)
    face = {"id": "face:o:0", "card_id": "card:o", "name": "Tester",
            "oracle_text": "When this creature enters, recruit."}
    rules.expand_recruit(gb, face)
    return gb


def _edge(gb, pred, src=None, tgt=None):
    return [e for e in gb.edges if e.predicate == pred
            and (src is None or e.source == src) and (tgt is None or e.target == tgt)]


def test_draw_then_discard_ordering():
    gb = _gb_with_recruit()
    draw = "op:face:o:0:recruit:draw"
    disc = "op:face:o:0:recruit:discard"
    assert gb.nodes[draw].data["quantity"] == 1
    assert gb.nodes[disc].data["quantity"] == 1
    assert _edge(gb, "CAUSES", "op:face:o:0:recruit", draw)
    after = _edge(gb, "CAUSES", draw, disc)
    assert after and after[0].timing == "after"


def test_discard_goes_to_graveyard():
    gb = _gb_with_recruit()
    assert _edge(gb, "MOVES_TO", "op:face:o:0:recruit:discard", "zone:graveyard")


def test_soldier_creation_is_conditional_on_nonland_discard():
    gb = _gb_with_recruit()
    create = _edge(gb, "CREATES_OBJECT", "gate:recruit-nonland-discard", "token:human-soldier")
    assert create
    assert create[0].condition_ids == ["cond:recruit-nonland-discard"]
    assert create[0].quantity == 1
    assert "cond:recruit-nonland-discard" in gb.conditions


def test_draw_produces_a_draw_event():
    # substrate for the Recruit->second-draw payoff direction (Phase 5)
    gb = _gb_with_recruit()
    assert _edge(gb, "PRODUCES", "op:face:o:0:recruit:draw", "event:card-drawn")

"""Adventure template — spec invariant #8: Adventure spell and permanent faces remain
distinct; spell casts from hand, resolves to exile, enables casting the permanent from
exile, with the normal-from-hand alternative preserved."""

from hobkg import rules


def _gb():
    gb = rules.GraphBuilder()
    rules.add_shared_nodes(gb)
    prim = {"id": "face:o:0", "card_id": "card:o", "name": "Hero"}
    adv = {"id": "face:o:1", "card_id": "card:o", "name": "Quest"}
    rules.expand_adventure(gb, prim, adv)
    return gb


def test_faces_distinct():
    gb = _gb()
    assert "face:o:0" in gb.nodes and "face:o:1" in gb.nodes
    assert gb.nodes["face:o:0"].label != gb.nodes["face:o:1"].label


def test_spell_from_hand_resolves_to_exile():
    gb = _gb()
    assert any(e.predicate == "MOVES_FROM" and e.source == "op:face:o:1:cast" and e.target == "zone:hand"
               for e in gb.edges)
    assert any(e.predicate == "MOVES_TO" and e.source == "op:face:o:1:resolve" and e.target == "zone:exile"
               for e in gb.edges)


def test_exile_enables_permanent_cast_and_hand_alternative():
    gb = _gb()
    assert any(e.predicate == "ENABLES" and e.source == "zone:exile"
               and e.target == "op:face:o:0:cast-from-exile" for e in gb.edges)
    hand = [e for e in gb.edges if e.source == "op:face:o:0:cast-from-hand" and e.target == "zone:hand"]
    assert hand and hand[0].optional is True

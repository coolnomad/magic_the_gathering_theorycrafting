"""Adventure template — invariant #8 (faces distinct) plus review fixes: exile
permission bound to the specific card via a per-object state, and casting modeled as
CAN_LEAD_TO resolution (not guaranteed)."""

from hobkg import rules


def _gb():
    gb = rules.GraphBuilder()
    rules.add_shared_nodes(gb)
    prim = {"id": "face:o:0", "card_id": "card:o", "name": "Hero"}
    adv = {"id": "face:o:1", "card_id": "card:o", "name": "Quest"}
    rules.expand_adventure(gb, prim, adv)
    return gb


def _has(gb, pred, src, tgt):
    return any(e.predicate == pred and e.source == src and e.target == tgt for e in gb.edges)


def test_faces_distinct():
    gb = _gb()
    assert gb.nodes["face:o:0"].label != gb.nodes["face:o:1"].label


def test_cast_is_not_guaranteed_resolution():
    gb = _gb()
    assert _has(gb, "MOVES_FROM", "op:face:o:1:cast", "zone:hand")
    assert _has(gb, "MOVES_TO", "op:face:o:1:cast", "zone:stack")
    assert _has(gb, "CAN_LEAD_TO", "op:face:o:1:cast", "op:face:o:1:resolve")
    # casting must NOT be a guaranteed CAUSES of resolution
    assert not _has(gb, "CAUSES", "op:face:o:1:cast", "op:face:o:1:resolve")


def test_exile_permission_bound_to_this_card():
    gb = _gb()
    st = "state:card:o:adventure-exiled"
    assert st in gb.nodes and gb.nodes[st].data["object"] == "card:o"
    # resolution exiles THIS object; the per-object state (not the global exile zone)
    # enables casting the permanent face.
    assert _has(gb, "PRODUCES", "op:face:o:1:resolve", st)
    assert _has(gb, "ENABLES", st, "op:face:o:0:cast-from-exile")
    assert not _has(gb, "ENABLES", "zone:exile", "op:face:o:0:cast-from-exile")


def test_normal_from_hand_alternative_preserved():
    gb = _gb()
    hand = [e for e in gb.edges if e.source == "op:face:o:0:cast-from-hand" and e.target == "zone:hand"]
    assert hand and hand[0].optional is True

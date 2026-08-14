"""Saga and hone templates."""

from hobkg import rules


def _gb():
    gb = rules.GraphBuilder()
    rules.add_shared_nodes(gb)
    return gb


def test_saga_chapters_and_sacrifice():
    gb = _gb()
    face = {"id": "face:s:0", "card_id": "card:s", "name": "A Saga",
            "oracle_text": "I — Draw a card.\nII — Create a token.\nIII — Deal 3 damage."}
    rules.expand_saga(gb, face)
    for n in (1, 2, 3):
        assert f"ab:face:s:0:chapter-{n}" in gb.nodes
    assert "op:face:s:0:sacrifice" in gb.nodes
    assert gb.nodes["op:face:s:0:sacrifice"].data["after_chapter"] == 3
    assert any(e.predicate == "ADDS_COUNTER" and e.target == "counter:lore" for e in gb.edges)
    assert any(e.predicate == "MOVES_TO" and e.source == "op:face:s:0:sacrifice"
               and e.target == "zone:graveyard" for e in gb.edges)


def test_hone_boost_not_attached_to_source_card():
    # spec: do NOT attach the power bonus to the source card that placed the counter.
    gb = _gb()
    face = {"id": "face:h:0", "card_id": "card:h", "name": "Honer",
            "oracle_text": "Whenever this attacks, put a hone counter on target Equipment."}
    rules.expand_hone(gb, face)
    assert any(e.predicate == "ADDS_COUNTER" and e.target == "counter:hone" for e in gb.edges)
    assert any(e.predicate == "SCALES_WITH" and e.source == "effect:hone-boost"
               and e.target == "counter:hone" for e in gb.edges)
    # boost targets the attached creature, never the source card/face
    boost = gb.nodes["effect:hone-boost"]
    assert boost.data["target"] == "attached_creature"
    assert not any(e.target == "card:h" or e.target == "face:h:0" for e in gb.edges
                   if e.source == "effect:hone-boost")

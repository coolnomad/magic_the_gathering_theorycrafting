"""Storied template — invariants #4,5,6 plus the review fix: card-definition objects
QUALIFY_FOR the gate (capacity), rather than CONTRIBUTE_TO a runtime count."""

from hobkg import rules


def _gb():
    gb = rules.GraphBuilder()
    rules.add_shared_nodes(gb)
    return gb


def test_gate_definition():
    gb = _gb()
    g = gb.gates["gate:storied"]
    assert g.gate_type == "distinct_object_threshold"
    assert g.definition["threshold"] == 3
    assert g.definition["double_count_multiqualifying_object"] is False
    assert g.definition["population"]["predicate"]["op"] == "or"


def test_union_predicate_counts_three_classes():
    gb = _gb()
    counted = {e.target for e in gb.edges if e.predicate == "COUNTS" and e.source == "gate:storied"}
    assert counted == {"obj:legendary", "obj:artifact", "obj:saga"}


def test_enduring_story_persists():
    gb = _gb()
    st = gb.nodes["state:enduring_story"]
    assert st.data["persistence"] == "rest_of_game"
    assert st.data["removable"] is False
    assert any(e.predicate == "PERSISTS_AS" and e.source == "state:enduring_story" for e in gb.edges)


def test_card_level_uses_qualifies_for_once():
    # a single object that is both legendary and an artifact qualifies exactly once,
    # and via QUALIFIES_FOR (capacity), never CONTRIBUTES_TO (runtime).
    gb = _gb()
    rules.storied_qualifier(gb, "face:leg-art", "CardFace", "Legendary Artifact", [])
    rules.storied_qualifier(gb, "face:leg-art", "CardFace", "Legendary Artifact", [])
    q = [e for e in gb.edges if e.source == "face:leg-art" and e.target == "gate:storied"]
    assert len(q) == 1
    assert q[0].predicate == "QUALIFIES_FOR"
    assert not any(e.predicate == "CONTRIBUTES_TO" for e in gb.edges)


def test_payoff_enabled_by_state():
    gb = _gb()
    rules.expand_storied_payoff(gb, {"id": "face:p:0", "card_id": "card:p",
                                     "name": "Payoff", "oracle_text": "Storied — draw a card."})
    assert any(e.predicate == "ENABLES" and e.source == "state:enduring_story"
               and e.target == "ab:face:p:0:storied" for e in gb.edges)

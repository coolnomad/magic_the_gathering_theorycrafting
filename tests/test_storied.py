"""Storied template — spec invariants #4 (count 3 distinct objects, union predicate),
#5 (a legendary artifact counts once), #6 (enduring story persists)."""

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
    assert g.definition["comparison"] == ">="
    assert g.definition["double_count_multiqualifying_object"] is False
    pred = g.definition["population"]["predicate"]
    assert pred["op"] == "or"  # union: Legendary / Artifact / Saga


def test_union_predicate_counts_three_classes():
    gb = _gb()
    counted = {e.target for e in gb.edges if e.predicate == "COUNTS" and e.source == "gate:storied"}
    assert counted == {"obj:legendary", "obj:artifact", "obj:saga"}


def test_enduring_story_persists():
    gb = _gb()
    st = gb.nodes["state:enduring_story"]
    assert st.data["persistence"] == "rest_of_game"
    assert st.data["removable"] is False
    assert any(e.predicate == "PRODUCES" and e.target == "state:enduring_story" for e in gb.edges)
    assert any(e.predicate == "PERSISTS_AS" and e.source == "state:enduring_story" for e in gb.edges)


def test_legendary_artifact_counts_once():
    # invariant #5: a single object that is BOTH legendary and an artifact contributes
    # exactly one CONTRIBUTES_TO edge.
    gb = _gb()
    prov = []
    rules.storied_contributor(gb, "face:leg-art", "CardFace", "Legendary Artifact", prov)
    rules.storied_contributor(gb, "face:leg-art", "CardFace", "Legendary Artifact", prov)
    edges = [e for e in gb.edges if e.source == "face:leg-art" and e.predicate == "CONTRIBUTES_TO"]
    assert len(edges) == 1


def test_payoff_enabled_by_state():
    gb = _gb()
    face = {"id": "face:p:0", "card_id": "card:p", "name": "Payoff", "oracle_text": "Storied — draw a card."}
    rules.expand_storied_payoff(gb, face)
    assert any(e.predicate == "ENABLES" and e.source == "state:enduring_story"
               and e.target == "ab:face:p:0:storied" for e in gb.edges)

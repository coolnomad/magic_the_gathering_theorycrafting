"""Effect-semantics Phase 1: the deterministic effect-family census over all 210 faces."""

from hobkg import effect_semantics as es
from hobkg.pipeline import REPO, _load_dicts

CENSUS = REPO / "data/graph_global/effect_census.jsonl"


def test_census_covers_all_faces_and_is_deterministic():
    a = es.census()
    assert a["faces"] == 210 and a["families"] == 32   # expanded family set (review pt1 finding 2)
    first = CENSUS.read_bytes()
    es.census()
    assert CENSUS.read_bytes() == first                 # deterministic (acceptance gate #10)


def test_census_is_clause_grouped_with_spans_and_indices():
    # review pt1 finding 1: clause-level rows carry clause_span + per-match match_span + indices,
    # and a clause groups ALL its families (one row per (ability, mode)).
    es.census()
    rows = _load_dicts(CENSUS)
    r0 = rows[0]
    for k in ("clause_id", "clause_span", "clause_text", "ability_index", "families", "matches"):
        assert k in r0
    assert all("match_span" in m and "sentence_index" in m for r in rows for m in r["matches"])
    warg = [r for r in rows if r["name"] == "Warg Tactics" and r["mode_index"] == 1]
    assert warg and set(warg[0]["families"]) >= {"add_counter", "grant_ability"}   # one grouped clause
    assert "trample" in warg[0]["clause_text"] and "hexproof" in warg[0]["clause_text"]
    rh = [r for r in rows if r["name"] == "Reverent Howl" and r["mode_index"] == 0]
    assert rh and set(rh[0]["families"]) == {"draw", "life"}    # same-participant draw+lose-life clause


def test_census_counts_are_sane_and_new_families_present():
    es.census()
    rows = _load_dicts(CENSUS)
    real = {}
    for r in rows:
        for m in r["matches"]:
            if not m["in_reminder"]:
                real.setdefault(m["family"], set()).add(r["face_id"])
    assert len(real["mill"]) == 6 and len(real["counterspell"]) == 3
    assert len(real["return_move"]) == 13 and len(real["life"]) == 22
    # the previously-missing required families now appear in the ledger
    for fam in ("scry_look_reveal", "copy", "cost_modification", "restriction", "replacement",
                "delayed", "remove_counter", "set_switch_pt"):
        assert fam in {f for r in rows for f in r["families"]}, fam


def test_every_clause_pending_and_reminder_flagged():
    es.census()
    rows = _load_dicts(CENSUS)
    assert rows and all(r["disposition"] == "pending_structuring" for r in rows)
    # reminder text flagged, not dropped — Adventure "(Then exile this card…)" reminder
    assert any(m["in_reminder"] for r in rows for m in r["matches"] if m["family"] == "exile")

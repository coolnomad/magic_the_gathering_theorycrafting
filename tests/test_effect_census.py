"""Effect-semantics Phase 1: the deterministic effect-family census over all 210 faces."""

from hobkg import effect_semantics as es
from hobkg.pipeline import REPO, _load_dicts

CENSUS = REPO / "data/graph_global/effect_census.jsonl"


def test_census_covers_all_faces_and_is_deterministic():
    a = es.census()
    assert a["faces"] == 210 and a["families"] == 22
    first = CENSUS.read_bytes()
    es.census()
    assert CENSUS.read_bytes() == first                 # deterministic (acceptance gate #10)


def test_census_counts_are_sane_vs_heuristics():
    es.census()
    rows = _load_dicts(CENSUS)
    by = {}
    for r in rows:
        by.setdefault(r["family"], set())
        if not r["in_reminder"]:
            by[r["family"]].add(r["face_id"])
    # families with clean, stable detectors should land on the instructions' reference counts
    assert len(by["mill"]) == 6 and len(by["counterspell"]) == 3
    assert len(by["return_move"]) == 13 and len(by["life"]) == 22
    # permanents are scanned, not just spells: at least some grant/tap candidates come from creatures
    assert len(by.get("grant_ability", set())) >= 10


def test_every_candidate_is_pending_and_reminder_flagged():
    es.census()
    rows = _load_dicts(CENSUS)
    assert rows and all(r["disposition"] == "pending_structuring" for r in rows)
    # reminder text is flagged, not dropped — Adventure "(Then exile this card…)" is reminder
    exile_rem = [r for r in rows if r["family"] == "exile" and r["in_reminder"]]
    assert exile_rem, "expected reminder-text exile candidates (Adventure cards)"

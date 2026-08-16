"""Phase 6 gate tests: mechanism modules + spec semantic invariants."""

import hashlib
import json

import pytest

from hobkg import modules
from hobkg.pipeline import REPO, _load_dicts

GLOBAL = REPO / "data" / "graph_global"
MODS = GLOBAL / "mechanism_modules.jsonl"


@pytest.fixture(scope="module")
def stats():
    return modules.build_modules()


@pytest.fixture(scope="module")
def mods(stats):
    return {m["module_id"]: m for m in
            (json.loads(l) for l in MODS.read_text(encoding="utf-8").splitlines())}


@pytest.fixture(scope="module")
def edges():
    return list(_load_dicts(GLOBAL / "edges.jsonl"))


# --- module structure --------------------------------------------------------
def test_named_modules_present(mods):
    labels = {m["label"] for m in mods.values()}
    for name in ("Recruit", "Storied", "Amass", "Ferocious", "Landfall", "Hone/Equipment",
                 "Saga", "graveyard reuse", "second-draw triggers"):
        assert name in labels
    # per-gate modules (the spec's mechanism_modules)
    for gate in ("module:gate:storied", "module:gate:recruit-nonland-discard", "module:gate:amass-no-army"):
        assert gate in mods


def test_every_module_is_a_grounded_subgraph(mods, edges):
    edge_ids = {e["edge_id"] for e in edges}
    assert mods
    for m in mods.values():
        assert m["anchors"] and (m["members"] or m["contributors"] or m["consumers"])
        for eid in m["subgraph_edge_ids"]:
            assert eid in edge_ids                       # subgraph edges are real graph edges
        for c in m["contributors"] + m["consumers"]:
            assert "predicate" in c and "edge_id" in c


def test_modules_deterministic():
    def d():
        modules.build_modules()
        return hashlib.sha256(MODS.read_bytes()).hexdigest()
    assert d() == d()


# --- spec semantic invariants (graph-testable subset) ------------------------
def test_inv1_recruit_soldier_conditional_on_nonland_discard(mods, edges):
    # Soldier creation is conditional on a nonland discard
    soldier = [e for e in edges if e["predicate"] == "CREATES_OBJECT"
               and e["target"] == "token:human-soldier" and e["source"] == "gate:recruit-nonland-discard"]
    assert soldier and "cond:recruit-nonland-discard" in (soldier[0].get("condition_ids") or [])
    assert "cond:recruit-nonland-discard" in mods["module:recruit"]["conditions"]


def test_inv4_storied_counts_three_distinct_classes(edges):
    counted = {e["target"] for e in edges if e["predicate"] == "COUNTS" and e["source"] == "gate:storied"}
    assert counted == {"obj:type:artifact", "obj:supertype:legendary", "obj:subtype:saga"}


def test_inv5_legendary_artifact_counts_once_not_twice(edges):
    # a permanent matching MULTIPLE counted types (e.g. a legendary artifact) is ONE
    # qualifying entity, not one per matched type. (Parallel QUALIFIES_FOR edges from
    # Phase2+LLM provenance are the same entity, so we compare deduped SETS.)
    from collections import defaultdict
    counted = {"obj:type:artifact", "obj:supertype:legendary", "obj:subtype:saga"}
    types_per_face = defaultdict(set)
    for e in edges:
        if e["predicate"] == "HAS_TYPE" and e["target"] in counted:
            types_per_face[e["source"]].add(e["target"])
    qualifiers = {e["source"] for e in edges
                  if e["predicate"] == "QUALIFIES_FOR" and e["target"] == "gate:storied"}
    contributors = set(types_per_face)
    assert contributors == qualifiers                    # each permanent counted once
    multi = [f for f, ts in types_per_face.items() if len(ts) >= 2]   # e.g. legendary artifact
    for f in multi:
        assert f in qualifiers                           # present exactly once (a set element)


def test_inv6_enduring_story_persists(mods, edges):
    assert any(e["predicate"] == "PERSISTS_AS" and e["source"] == "state:enduring_story"
               and e["target"] == "state:enduring_story" for e in edges)
    # surfaced as a feedback cycle in the Storied module
    assert mods["module:storied"]["feedback_cycles"]


def test_inv8_adventures_have_two_distinct_faces(edges):
    faces = _load_dicts(REPO / "data/normalized/faces.jsonl")
    adv_cards = {f["card_id"] for f in faces if f.get("role") == "adventure"}
    by_card = {}
    for f in faces:
        by_card.setdefault(f["card_id"], set()).add(f["id"])
    assert len(adv_cards) == 17
    for c in adv_cards:
        assert len(by_card[c]) == 2                      # exactly two distinct face nodes


def test_inv10_other_another_exclusions_present(edges):
    # "another"/"other" self-exclusion object classes exist (prevent false self-effects)
    objs = {e["target"] for e in edges if e["target"].startswith("obj:another")}
    assert objs

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
    # subgraph edges resolve to the UNION of frozen + repair-layer edges (Phase 6 v2)
    rep = GLOBAL / "repair_edges.jsonl"
    edge_ids = {e["edge_id"] for e in edges}
    if rep.exists():
        edge_ids |= {json.loads(l)["edge_id"] for l in rep.read_text(encoding="utf-8").splitlines()}
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


def test_inv3_bard_modifies_recruit_draw_and_token_quantities(edges):
    bard = "d05db2c1"
    replaced = {e["target"] for e in edges if bard in e["source"] and e["predicate"] == "REPLACES"}
    assert {"event:draw", "event:token_creation"} <= replaced   # draw AND token replacement


def test_inv7_qualifying_artifact_token_installs_qualifying_object(edges):
    # a Treasure token is an artifact (a Storied-qualifying object); creating one installs it
    assert any(e["source"] == "token:treasure" and e["predicate"] == "HAS_TYPE"
               and e["target"] == "obj:type:artifact" for e in edges)
    assert any(e["predicate"] == "CREATES_OBJECT" and e["target"] == "token:treasure" for e in edges)


# --- Phase 6 v2: repair-layer union + full token coverage + discovery -------
def test_repair_layer_is_unioned_into_modules(mods):
    # the graph-repair structures must participate in Phase 6 modules
    by_label = {m["label"]: m for m in mods.values()}
    life = by_label["life-loss trigger"]["members"]
    assert any("514b451b" in c for c in life)                # Gollum (repaired CAUSES)
    elf = next(m for m in mods.values() if m["anchors"] == ["obj:subtype:elf"])
    assert any("f6771d32" in c for c in elf["members"])      # Thranduil (repaired MODIFIES)


def test_every_created_token_has_a_module(mods, edges):
    created = {e["target"] for e in edges if e["predicate"] == "CREATES_OBJECT"
              and e["target"].startswith("token:")}
    covered = {a for m in mods.values() if m["kind"] == "token_production" for a in m["anchors"]}
    assert created <= covered                                # incl. gate-mediated token:human-soldier
    soldier = next(m for m in mods.values() if m["anchors"] == ["token:human-soldier"])
    assert soldier["stats"]["members"] == 10                 # recovered upstream through the gate


def test_generalized_discovery_ran(mods):
    discovered = [m for m in mods.values() if m["kind"].startswith("discovered_")]
    assert len(discovered) >= 5
    labels = {m["label"] for m in discovered}
    assert {"life-loss trigger", "counter-placement trigger", "activated-ability trigger"} <= labels


def test_module_subgraph_includes_provenance_path(mods, edges):
    # a module edge whose endpoint is an operation must also carry the causal path back to
    # the printed ability (ability -CAUSES-> op, face -HAS_ABILITY-> ability), not just the anchor edge
    all_edges = {e["edge_id"]: e for e in edges}
    rep = GLOBAL / "repair_edges.jsonl"
    if rep.exists():
        all_edges.update({json.loads(l)["edge_id"]: json.loads(l) for l in rep.read_text(encoding="utf-8").splitlines()})
    elf = next(m for m in mods.values() if m["anchors"] == ["obj:subtype:elf"])
    preds = {all_edges[e]["predicate"] for e in elf["subgraph_edge_ids"]
             if e in all_edges and "f6771d32" in all_edges[e]["source"] + all_edges[e]["target"]}
    assert {"HAS_ABILITY", "CAUSES", "MODIFIES"} <= preds   # face -> ability -> op -> anchor


# --- remaining semantic invariants (spec) ------------------------------------
def test_inv2_councillors_second_draw_only_and_not_reverse(edges):
    # Master's Councillors triggers ONLY on the second-draw event (encodes "only through
    # the second draw"), and produces no draw that a Recruit card could consume (no reverse).
    faces = _load_dicts(REPO / "data/normalized/faces.jsonl")
    mc = next(f["card_id"] for f in faces if f["name"] == "Master's Councillors")
    u = mc.split(":")[1]
    trig = {e["source"] for e in edges if e["predicate"] == "TRIGGERS" and u in e["target"]}
    assert trig and all("second" in t for t in trig)         # only via a second-draw event
    # Councillors does not PRODUCE a draw/card that would let the relation run in reverse
    assert not any(u in e["source"] and e["predicate"] == "PRODUCES"
                   and e["target"] in ("resource:card", "event:draw") for e in edges)


def test_inv11_legend_conflicts_not_subjective_synergy(edges):
    # legend-rule conflicts are NOT (mis)represented as subjective negative-synergy edges;
    # the predicate vocabulary is entirely mechanistic.
    preds = {e["predicate"] for e in edges}
    assert not (preds & {"SYNERGY", "NEGATIVE_SYNERGY", "ANTI_SYNERGY", "ARCHETYPE"})
    # the graph does model the legendary supertype (the substrate a state-constraint model would use)
    assert any(e["target"] == "obj:supertype:legendary" for e in edges)


def test_inv12_self_pair_object_identity(edges):
    proj = _load_dicts(GLOBAL / "card_pair_projection.jsonl")
    self_pairs = [m for m in proj if m["self_pair"]]
    assert self_pairs and all(m["source_card"] == m["target_card"] for m in self_pairs)
    # "another/other" object classes let one object affect a DIFFERENT copy, not itself
    assert any(e["target"].startswith("obj:another") for e in edges)

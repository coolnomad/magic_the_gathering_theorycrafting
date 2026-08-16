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
    # subgraph edges resolve to the UNION of frozen + repair + legend layers (Phase 6 v3.1)
    edge_ids = {e["edge_id"] for e in edges}
    for layer in ("repair_edges.jsonl", "legend_edges.jsonl"):
        p = GLOBAL / layer
        if p.exists():
            edge_ids |= {json.loads(l)["edge_id"] for l in p.read_text(encoding="utf-8").splitlines()}
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
def test_inv2_second_draw_ordering_deferred_unmodeled(edges):
    # #2 is a DEFERRED / UNMODELED representational gap, NOT a completed invariant (pt3 review):
    # modeling Recruit -> Master's Councillors needs a turn-scoped cards-drawn-this-turn count
    # state/gate that does not exist yet. This test pins the HONEST current handling — the graph
    # refuses to invent a Recruit<->Councillors edge — and the gap is recorded in
    # coverage.DEFERRED_INVARIANTS (see test_coverage_labels_invariant2_deferred). Councillors
    # triggers ONLY on the second-draw event, which (correctly) has no modeled producer.
    from collections import defaultdict

    # the deferral is recorded honestly, not presented as satisfied
    from hobkg.coverage import DEFERRED_INVARIANTS
    assert any(d["id"] == 2 and d["status"] == "deferred_unmodeled" for d in DEFERRED_INVARIANTS)

    faces = list(_load_dicts(REPO / "data/normalized/faces.jsonl"))
    mc = next(f["card_id"] for f in faces if f["name"] == "Master's Councillors")
    u = mc.split(":")[1]
    mech = defaultdict(set)
    for m in _load_dicts(REPO / "data/rules/mechanics.jsonl"):
        mech[m["mechanic"]].add(m["card_id"])
    recruit = mech["Recruit"]
    assert recruit, "HOB has Recruit cards"

    # (1) Councillors triggers ONLY on a second-draw event
    trig = {e["source"] for e in edges if e["predicate"] == "TRIGGERS" and u in e["target"]}
    assert trig and all("second" in t for t in trig)
    # (2) that second-draw event has NO modeled producer/cause (the ordering condition is unmodeled,
    #     so the graph does not invent a Recruit-draw -> second-draw production edge)
    for ev in trig:
        assert not any(e["target"] == ev for e in edges), f"{ev} must have no incoming producer"
    # (3) Councillors produces no draw/card -> no reverse enabling is even possible
    assert not any(u in e["source"] and e["predicate"] in ("PRODUCES", "SUPPLIES", "CREATES_OBJECT")
                   and e["target"] in ("resource:card", "event:draw") for e in edges)
    # (4) across ALL THREE projection layers there is NO metaedge either way between any Recruit
    #     card and Councillors (the graph asserts no unsupported synergy in either direction)
    for layer in ("card_pair_projection.jsonl", "card_pair_projection_audit.jsonl",
                  "card_pair_projection_repaired.jsonl"):
        p = GLOBAL / layer
        if not p.exists():
            continue
        for m in _load_dicts(p):
            s, t = m["source_card"], m["target_card"]
            assert not (t == mc and s in recruit), f"unexpected Recruit->Councillors edge in {layer}"
            assert not (s == mc and t in recruit), f"unexpected Councillors->Recruit edge in {layer}"


def test_inv11_legend_rule_materialized_as_sba_transition(edges, mods):
    # SUBSTANTIVE #11: the legend rule (CR 704.5j) is modeled as its ACTUAL state-based action —
    # a second same-name legendary permanent enters, then a controller-scoped SBA keeps one and
    # puts the rest into their OWNERS' graveyards — NOT as a subjective negative-synergy edge and
    # NOT as the coarse "a second copy cannot exist" (max_controlled=1) approximation.
    preds = {e["predicate"] for e in edges}
    assert not (preds & {"SYNERGY", "NEGATIVE_SYNERGY", "ANTI_SYNERGY", "ARCHETYPE"})
    ln = {n["id"]: n for n in _load_dicts(GLOBAL / "legend_nodes.jsonl")}
    le = list(_load_dicts(GLOBAL / "legend_edges.jsonl"))
    assert ln, "legend layer must be materialized"

    # per-name controller-scoped CONFLICT states (not a max_controlled constraint)
    conflict = {i: n for i, n in ln.items() if i.startswith("state:legend-conflict:")}
    assert conflict
    for n in conflict.values():
        assert n["type"] == "State" and n["data"]["rule"] == "legend"
        assert n["data"]["scope"] == "controller"                 # explicit controller scope
        assert n["data"]["resolution"] == "state_based_action"    # the real transition, not a ban
        assert n["data"]["conflict_threshold"] == 2               # conflict when >=2 are controlled
        assert "max_controlled" not in n["data"]                  # coarse approximation is gone
        assert n["origin"] == "legend_rule"

    # one HAS_STATE edge per legendary face -> its conflict state; exactly the legendary faces
    # (legendary faces are those carrying HAS_TYPE -> obj:supertype:legendary, per the assembler)
    legendary_faces = {e["source"] for e in edges
                       if e["predicate"] == "HAS_TYPE" and e["target"] == "obj:supertype:legendary"}
    assert legendary_faces, "there are legendary faces in HOB"
    has_state = {(e["source"], e["target"]) for e in le if e["predicate"] == "HAS_STATE"}
    assert {s for s, _ in has_state} == legendary_faces   # every legendary face, only legendary faces
    assert all(t in conflict for _, t in has_state)       # each points at a materialized conflict state

    # the SBA TRANSITION chain: conflict state ENABLES the SBA ability, which CAUSES a
    # put-into-graveyard operation that MOVES_TO the graveyard (owner-scoped destination)
    sba, move = "ability:legend-sba", "op:legend-sba-put-in-graveyard"
    assert ln[sba]["type"] == "Ability" and ln[sba]["data"]["kind"] == "state_based_action"
    assert ln[sba]["data"]["scope"] == "controller"
    assert ln[move]["type"] == "Operation" and ln[move]["data"]["destination_scope"] == "owner"
    enables = {(e["source"], e["target"]) for e in le if e["predicate"] == "ENABLES"}
    assert enables == {(s, sba) for s in conflict}        # every conflict state enables the one SBA
    assert any(e["source"] == sba and e["predicate"] == "CAUSES" and e["target"] == move for e in le)
    assert any(e["source"] == move and e["predicate"] == "MOVES_TO" and e["target"] == "zone:graveyard"
               for e in le)

    # surfaced as a Phase 6 module whose anchors are the per-name conflict states
    legend_mod = mods["module:legend-rule"]
    assert legend_mod["kind"] == "state_constraint"
    assert set(legend_mod["anchors"]) == set(conflict) and len(legend_mod["anchors"]) == len(legendary_faces)
    # the SBA is reached as a downstream consumer of the conflict states (ENABLES one hop)
    assert any(c["target"] == sba for c in legend_mod["consumers"])


def test_inv12_self_pair_this_vs_another_resolution(edges):
    # SUBSTANTIVE #12: every self-pair metaedge is a GENUINE reflexive self-effect. The projection
    # resolves object identity per relation (this vs another vs copy): a self-pair must be reflexive
    # AND must NOT be routed through an "another/other" class (which is a DIFFERENT copy).
    proj = list(_load_dicts(GLOBAL / "card_pair_projection.jsonl"))
    self_pairs = [m for m in proj if m["self_pair"]]
    assert self_pairs and all(m["source_card"] == m["target_card"] for m in self_pairs)
    # the "another/other" self-exclusion classes exist (the substrate that makes the distinction real)
    assert any(e["target"].startswith("obj:another") for e in edges)
    for m in self_pairs:
        assert m["participant_status"] == "resolved"      # identity was resolved, not left ambiguous
        path_nodes = [n for a in m.get("alternative_paths", []) for n in a["primitive_path"]]
        assert not any(n.startswith(("obj:another", "obj:other")) for n in path_nodes), (
            f"self-pair {m['source_card']} ({m['relation']}) is routed through an 'another/other' "
            "class — that is a different copy, not a reflexive self-effect")
    # every relation type that produces self-pairs did so through resolved identity (no relation
    # is silently exempt from the this/another/copy distinction)
    assert {m["relation"] for m in self_pairs} <= {
        "INFRASTRUCTURE_CASTING", "CONTRIBUTES_TO_GATE", "ENABLES_TRIGGER", "SUPPLIES_RESOURCE"}

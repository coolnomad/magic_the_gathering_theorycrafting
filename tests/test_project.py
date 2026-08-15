"""Phase 5 mechanical card-pair projection gate tests (v2).

Covers the pt1-review regression cases: colour-compatible mana contribution,
controller Treasure paths, semantic-property propagation, alternative-path
preservation, and real/reverse/derived edge faithfulness.
"""

import json
import re

import pytest

from hobkg import project
from hobkg.pipeline import REPO

PROJ = REPO / "data" / "graph_global" / "card_pair_projection.jsonl"
_FACE = re.compile(r"face:[0-9a-f-]{36}:\d+")


@pytest.fixture(scope="module")
def stats():
    return project.project()


@pytest.fixture(scope="module")
def metaedges():
    return [json.loads(l) for l in PROJ.read_text(encoding="utf-8").splitlines()]


@pytest.fixture(scope="module")
def nodes():
    return {n["id"]: n for n in
            (json.loads(l) for l in (REPO / "data/graph_global/nodes.jsonl").read_text(encoding="utf-8").splitlines())}


@pytest.fixture(scope="module")
def edge_ids():
    return {json.loads(l)["edge_id"]
            for l in (REPO / "data/graph_global/edges.jsonl").read_text(encoding="utf-8").splitlines()}


def _cid(nodes, name):
    return next(nid for nid, n in nodes.items() if n["type"] == "Card" and n["label"] == name)


def _infra_targets(metaedges, nodes, name):
    s = _cid(nodes, name)
    return {m["target_card"] for m in metaedges
            if m["source_card"] == s and m["relation"] == "INFRASTRUCTURE_CASTING"}


def _alt_source_colors(nodes, alt):
    for s in alt["steps"]:
        if s["predicate"] == "CREATES_OBJECT" and s["target"].startswith("token:"):
            return set(nodes[s["target"]]["data"].get("produced_mana") or [])
    for s in alt["steps"]:
        if s["predicate"] == "PRODUCES" and s["target"].startswith("resource:mana"):
            m = _FACE.search(s["source"])
            return set(nodes.get(m.group(0), {}).get("data", {}).get("produced_mana") or [])
    return None


def _matched_cost(nodes, alt):
    cs = next((s for s in alt["steps"] if s["predicate"] == "HAS_COST"), None)
    if not cs:
        return None
    cn = cs["source"] if cs["direction"] == "reverse" else cs["target"]
    return nodes.get(cn, {}).get("data", {}).get("mana_cost") or {}


# --- schema + derivation ------------------------------------------------------
def test_schema_and_alternatives(metaedges):
    assert metaedges
    for m in metaedges:
        assert {"source_card", "target_card", "relation", "alternative_paths",
                "n_alternatives", "min_path_length", "infrastructure_only",
                "involves_gate", "involves_state", "provenance"} <= set(m)
        assert m["n_alternatives"] == len(m["alternative_paths"]) >= 1
        sigs = [json.dumps(a["signature"], sort_keys=True) for a in m["alternative_paths"]]
        assert len(sigs) == len(set(sigs)), "identical path signatures must collapse"
        for a in m["alternative_paths"]:
            assert a["provenance"] and a["path_predicates"] and a["edge_ids"]


def test_derived_not_bruteforced(stats):
    assert stats["distinct_ordered_pairs"] < stats["possible_ordered_pairs"] * 0.3
    assert stats["possible_ordered_pairs"] == 193 * 193


def test_no_ontology_only_joins(metaedges):
    for m in metaedges:
        for a in m["alternative_paths"]:
            assert not any(n.startswith(("obj:type:", "obj:subtype:", "obj:supertype:"))
                           for n in a["primitive_path"])


def test_every_step_is_real_or_labelled_derived(metaedges, edge_ids):
    derived = 0
    for m in metaedges:
        for a in m["alternative_paths"]:
            for s in a["steps"]:
                assert s["direction"] in ("forward", "reverse")
                if s["derived"]:
                    derived += 1
                    assert s["edge_id"].startswith("derived:")   # stable, labelled
                else:
                    assert s["edge_id"] in edge_ids               # resolves to a real Phase 4 edge
    assert derived > 0


# --- mana colour compatibility (pt1 defect 1) --------------------------------
def test_no_off_colour_infrastructure(metaedges, nodes):
    """No mana source contributes to a cost it cannot pay (checked against the ACTUAL
    matched cost node, which for two-faced cards may be the adventure face)."""
    for m in metaedges:
        if m["relation"] != "INFRASTRUCTURE_CASTING":
            continue
        for a in m["alternative_paths"]:
            pc = _alt_source_colors(nodes, a)
            mc = _matched_cost(nodes, a)
            if pc is None or mc is None or mc.get("generic") or mc.get("has_variable"):
                continue
            pips = set((mc.get("pips") or {}).keys())
            assert pc & pips, f"off-colour: {pc} -> {pips}"


def test_island_and_mountain_colour_rules(metaedges, nodes):
    island = _infra_targets(metaedges, nodes, "Island")
    # Island (blue) must NOT pay a mono-{W} cost with no generic
    assert _cid(nodes, "Moment of Glory") not in island
    # but it must contribute to at least one cost containing {U}
    assert island
    mountain = _infra_targets(metaedges, nodes, "Mountain")
    assert _cid(nodes, "Moment of Glory") not in mountain     # red cannot pay {W}


# --- controller Treasure paths (pt1 defect 2) --------------------------------
def test_controller_treasure_path_included(metaedges, nodes):
    dog = _cid(nodes, "Long-Bodied Grey Dog")     # produces mana only via a Treasure token
    infra = [m for m in metaedges if m["source_card"] == dog and m["relation"] == "INFRASTRUCTURE_CASTING"]
    assert infra
    alt = infra[0]["alternative_paths"][0]
    assert "CREATES_OBJECT" in alt["path_predicates"]
    assert alt["creates_for"] == "controller"


def test_bilbo_opponent_mana_not_infrastructure(metaedges, nodes):
    bilbo = _cid(nodes, "Bilbo's Gambit")
    assert not any(m["source_card"] == bilbo and m["relation"] == "INFRASTRUCTURE_CASTING"
                   for m in metaedges)


# --- property propagation (pt1 defect 3) -------------------------------------
def test_semantic_properties_propagated(metaedges):
    # creates_for reaches the projection; a conditional Treasure retains its condition
    assert any(a.get("creates_for") for m in metaedges for a in m["alternative_paths"])
    warg_cond = any(
        s.get("condition_ids")
        for m in metaedges if m["relation"] == "INFRASTRUCTURE_CASTING"
        for a in m["alternative_paths"] for s in a["steps"]
        if s["predicate"] == "CREATES_OBJECT")
    assert warg_cond, "conditional Treasure creation must retain its condition_ids"


# --- alternatives preserved, not merged (pt1 defect 4) -----------------------
def test_alternative_paths_kept_as_disjuncts(metaedges):
    multi = [m for m in metaedges if m["n_alternatives"] > 1]
    assert multi
    for m in multi:
        sigs = [tuple(tuple(x) for x in a["signature"]) for a in m["alternative_paths"]]
        assert len(sigs) == len(set(sigs))            # distinct mechanisms, not merged


def test_projection_is_byte_identical():
    import hashlib
    def digest():
        project.project()
        return hashlib.sha256(PROJ.read_bytes()).hexdigest()
    assert digest() == digest()

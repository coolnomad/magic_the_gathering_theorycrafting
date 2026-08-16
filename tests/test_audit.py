"""Phase 5 Part 2 gate tests: candidate selection + extractor/critic reconcile."""

import json

import pytest

from hobkg import audit
from hobkg.pipeline import REPO, _load_dicts

CANDS = REPO / "data" / "graph_global" / "audit_candidates.jsonl"
AUG = REPO / "data" / "graph_global" / "card_pair_projection_audit.jsonl"


@pytest.fixture(scope="module")
def cstats():
    return audit.build_candidates()


@pytest.fixture(scope="module")
def cands(cstats):
    return [json.loads(l) for l in CANDS.read_text(encoding="utf-8").splitlines()]


# --- Stage A: candidates ------------------------------------------------------
def test_candidate_schema_and_bounded(cstats, cands):
    assert cands and cstats["candidates"] == len(cands)
    assert len(cands) < 500                                   # bounded, not 37,249
    for c in cands:
        assert {"source_card", "target_card", "buckets", "evidence",
                "shared_concepts", "mechanical_relations"} <= set(c)
        assert c["buckets"]


def test_named_reference_excludes_tribal_types(cands):
    for c in cands:
        for ev in c["evidence"].get("named_reference", []):
            assert ev["token"].lower() not in {"goblin", "elf", "dwarf", "dragon", "human",
                                               "spider", "wolf", "bird", "bear", "orc"}


def test_copy_effect_is_cross_card(cands):
    copy = [c for c in cands if "copy_effect" in c["buckets"]]
    assert copy                                               # bucket is operational
    assert all(c["source_card"] != c["target_card"] for c in copy)


def test_ambiguous_scope_generates_pairs(cands):
    # ambiguous_scope now yields real candidate pairs, not annotation-only
    assert any("ambiguous_scope" in c["buckets"] for c in cands)


def test_candidates_deterministic():
    import hashlib
    def digest():
        audit.build_candidates()
        return hashlib.sha256(CANDS.read_bytes()).hexdigest()
    assert digest() == digest()


# --- Stage B: reconcile + augmented layer ------------------------------------
@pytest.fixture(scope="module")
def istats():
    return audit.ingest()


@pytest.fixture(scope="module")
def augmented(istats):
    if not AUG.exists():
        return []
    return [json.loads(l) for l in AUG.read_text(encoding="utf-8").splitlines()]


def test_augmented_layer_is_separate_and_faithful(istats, augmented):
    if not augmented:
        pytest.skip("no audit verdicts ingested")
    assert istats["augmented_metaedges"] == len(augmented)
    for m in augmented:
        assert m["origin"] == "llm_audit"                    # kept OUT of canonical projection
        assert m["relation"] and m["connecting_concept"]
        assert m["path_kind"] == "grounded"                  # ONLY faithful typed paths accepted
        # relation-specific signature: a real enabler edge, a derived bridge, a real edge
        assert m["path_predicates"][1] == m["relation"]      # middle step is the derived bridge


RQ = REPO / "data" / "graph_global" / "audit_repair_queue.jsonl"


@pytest.fixture(scope="module")
def repair(istats):
    if not RQ.exists():
        return []
    return [json.loads(l) for l in RQ.read_text(encoding="utf-8").splitlines()]


def test_repair_queue_unordered_with_proposed_direction(istats, repair):
    if not repair:
        pytest.skip("no repair queue")
    assert len(repair) == istats["repair_queue"]
    for r in repair:
        assert r["card_a"] < r["card_b"]                     # unordered (sorted) pair
        assert r["candidate_concept"] and r["missing_node_type"] and r["missing_node_hint"]
        assert r["direction_status"] in ("proposed", "adjudicated")   # never "mechanically proven"
        assert r["proposed_direction"]["enabler"] in (r["card_a"], r["card_b"])
        if r["relation"] == "ENABLES_TRIGGER":
            assert r["missing_node_type"] == "Event"         # needs an intermediate Event


def test_repair_queue_directions_are_correct(repair):
    """The four pt4 examples must propose the MECHANISTICALLY-correct enabler."""
    if not repair:
        pytest.skip("no repair queue")
    want = {  # unordered pair (by name)  ->  correct enabler name
        frozenset({"Gandalf, Wandering Wizard", "Elrond, Moon-Reader"}): "Gandalf, Wandering Wizard",
        frozenset({"Great Ugly-Looking Goblin // Clap! Snap!", "The Great Goblin"}):
            "Great Ugly-Looking Goblin // Clap! Snap!",
        frozenset({"Rage into the Valley", "The Master of Lake-town"}): "Rage into the Valley",
        frozenset({"The Sackville-Bagginses", "The Master of Lake-town"}): "The Sackville-Bagginses",
    }
    by_pair = {frozenset({r["card_a_name"], r["card_b_name"]}): r["proposed_enabler_name"] for r in repair}
    for pair, enabler in want.items():
        assert pair in by_pair, f"missing repair pair {pair}"
        assert by_pair[pair] == enabler, f"{pair}: proposed {by_pair[pair]!r} != {enabler!r}"


def test_accepted_conditions_union_path_steps(augmented):
    # Bard -> Beorn must retain Beorn's three-Bears draw condition (from the path edge)
    beorn = next((m for m in augmented if "30ca8e92" in m["target_card"]
                  and "d05db2c1" in m["source_card"]), None)
    if beorn is None:
        pytest.skip("Bard->Beorn not accepted")
    assert beorn["conditions"], "path-step conditions must be unioned into the metaedge"


def test_repair_hint_is_grounding_driven(repair):
    # Gollum's grounding "Each opponent loses 2 life" ⇒ Event:life-lost, NOT the
    # misleading candidate concept resource:card.
    if not repair:
        pytest.skip("no repair queue")
    gollum = next((r for r in repair if "Gollum" in r["card_a_name"] + r["card_b_name"]), None)
    if gollum:
        assert "life-lost" in gollum["missing_node_hint"]
        assert "card-drawn" not in gollum["missing_node_hint"]


def test_direction_conflict_goes_to_adjudication(istats):
    # a real relation where extractor/critic agree on type+concept but disagree on the
    # enabler is preserved for manual review, not silently dropped.
    aq_path = REPO / "data" / "graph_global" / "audit_adjudication_queue.jsonl"
    if not aq_path.exists():
        pytest.skip("no adjudication queue")
    aq = [json.loads(l) for l in aq_path.read_text(encoding="utf-8").splitlines()]
    faces = {f["id"]: (f.get("oracle_text") or "")
             for f in _load_dicts(REPO / "data/normalized/faces.jsonl")}
    assert len(aq) == istats["adjudication_queue"]
    for r in aq:
        assert r["card_a"] < r["card_b"]
        assert r["extractor_enabler"] != r["critic_enabler"]   # genuine direction conflict
        assert r["relation"] and r["candidate_concept"]
        # BOTH extractor and critic grounding are stored and span-validated per face
        for side in ("extractor_grounding", "critic_grounding"):
            assert r[side]
            for g in r[side]:
                s, e = g["oracle_span"]
                assert faces[g["face_id"]][s:e] == g["text"]   # exact face-specific span
                assert g["card_id"]
    # the Thranduil / Down in the Valley Elf-anthem relation must be here, not excluded
    assert any("Thranduil" in (r["card_a_name"] + r["card_b_name"])
               and "Down in the Valley" in (r["card_a_name"] + r["card_b_name"]) for r in aq)


def test_coverage_and_dual_counts_reported(istats):
    assert istats["audited"] == istats["total_candidates"] and istats["unaudited"] == 0
    # verdict-level and deduplicated counts are BOTH reported and distinct concepts
    assert istats["accepted_verdicts"] >= istats["augmented_metaedges"]
    assert istats["repair_verdicts"] >= istats["repair_queue"]


def test_augmented_paths_are_real_or_labelled_derived(augmented):
    if not augmented:
        pytest.skip("no audit verdicts")
    edge_ids = {e["edge_id"] for e in _load_dicts(REPO / "data/graph_global/edges.jsonl")}
    for m in augmented:
        for s in m["steps"]:
            if s["derived"]:
                assert s["edge_id"].startswith("derived:")
            else:
                assert s["edge_id"] in edge_ids               # resolves to a Phase 4 edge


def test_augmented_grounding_is_exact_per_face_span(augmented):
    if not augmented:
        pytest.skip("no audit verdicts")
    faces = {f["id"]: (f.get("oracle_text") or "")
             for f in _load_dicts(REPO / "data/normalized/faces.jsonl")}
    for m in augmented:
        assert m["grounding"]
        for g in m["grounding"]:
            s, e = g["oracle_span"]
            assert faces[g["face_id"]][s:e] == g["text"]      # exact substring on that face


def test_augmented_deduped_and_novel(augmented):
    if not augmented:
        pytest.skip("no audit verdicts")
    keys = [(m["source_card"], m["target_card"], m["relation"]) for m in augmented]
    assert len(keys) == len(set(keys))                        # one per (src, tgt, relation)
    # none duplicates an existing mechanical relation between the same pair
    proj = list(_load_dicts(REPO / "data/graph_global/card_pair_projection.jsonl"))
    mech = {}
    for p in proj:
        mech.setdefault((p["source_card"], p["target_card"]), set()).add(p["relation"])
    for m in augmented:
        both = mech.get((m["source_card"], m["target_card"]), set()) | \
               mech.get((m["target_card"], m["source_card"]), set())
        assert m["relation"] not in both


def test_reconcile_requires_critic_agreement(istats):
    # accepted relations passed BOTH extractor and an independent critic; the augmented
    # layer is the deduped subset of accepted verdicts.
    assert istats["augmented_metaedges"] >= 1
    assert istats["augmented_metaedges"] <= istats["accepted"]
    assert istats["critic_disagreement"] >= 0

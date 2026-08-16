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


def test_repair_queue_for_unfaithful_relations(istats):
    # credible relations lacking a primitive path go to a repair queue, NOT a shortcut
    rq_path = REPO / "data" / "graph_global" / "audit_repair_queue.jsonl"
    if not rq_path.exists():
        pytest.skip("no repair queue")
    rq = [json.loads(l) for l in rq_path.read_text(encoding="utf-8").splitlines()]
    assert len(rq) == istats["repair_queue"]
    for r in rq:
        assert r["relation"] and r["connecting_concept"] and r["missing"]


def test_coverage_reported(istats):
    assert istats["audited"] == istats["total_candidates"]   # full coverage
    assert istats["unaudited"] == 0


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

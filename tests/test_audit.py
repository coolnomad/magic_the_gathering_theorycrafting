"""Phase 5 Part 2 Stage A: audit candidate-selection gate tests."""

import json

import pytest

from hobkg import audit
from hobkg.pipeline import REPO

CANDS = REPO / "data" / "graph_global" / "audit_candidates.jsonl"


@pytest.fixture(scope="module")
def stats():
    return audit.build_candidates()


@pytest.fixture(scope="module")
def cands():
    return [json.loads(l) for l in CANDS.read_text(encoding="utf-8").splitlines()]


def test_schema_and_bounded(stats, cands):
    assert cands
    assert stats["candidates"] == len(cands)
    # bounded: far below the 37,249 brute-force scan
    assert len(cands) < 500
    for c in cands:
        assert {"source_card", "target_card", "source_name", "target_name",
                "buckets", "evidence", "mechanical_relations"} <= set(c)
        assert c["buckets"]                              # every candidate has a reason


def test_named_reference_is_directed(cands):
    named = [c for c in cands if "named_reference" in c["buckets"]]
    assert named
    for c in named:
        assert c["evidence"]["named_reference"]         # carries the matched token


def test_participant_unresolved_included(cands):
    pu = [c for c in cands if "participant_unresolved" in c["buckets"]]
    assert len(pu) == 1                                 # the Gandalf -> Confusticate supply


def test_no_asserted_pairs_in_shared_vocabulary(cands):
    from hobkg.pipeline import _load_dicts
    proj = list(_load_dicts(REPO / "data/graph_global/card_pair_projection.jsonl"))
    asserted = {(m["source_card"], m["target_card"]) for m in proj if m["asserted"]}
    for c in cands:
        if c["buckets"] == ["shared_vocabulary"]:
            assert (c["source_card"], c["target_card"]) not in asserted


def test_candidates_deterministic():
    import hashlib
    def digest():
        audit.build_candidates()
        return hashlib.sha256(CANDS.read_bytes()).hexdigest()
    assert digest() == digest()


def test_named_reference_excludes_tribal_types(cands):
    # a bare creature-type word (Goblin/Elf/Dwarf/Dragon) must not be a named_reference
    for c in cands:
        for ev in c["evidence"].get("named_reference", []):
            assert ev["token"].lower() not in {"goblin", "elf", "dwarf", "dragon", "human",
                                               "spider", "wolf", "bird", "bear", "orc"}


# --- Stage B: ingest of sub-agent verdicts -----------------------------------
RESULTS = REPO / "data" / "graph_global" / "audit_results.jsonl"


@pytest.fixture(scope="module")
def ingest_stats():
    return audit.ingest()


def test_ingest_accepts_only_grounded_relations(ingest_stats):
    if not RESULTS.exists():
        pytest.skip("no audit verdicts ingested yet")
    results = [json.loads(l) for l in RESULTS.read_text(encoding="utf-8").splitlines()]
    assert ingest_stats["verdicts"] == len(results)
    for r in results:
        assert r["verdict"] in ("RELATION", "NO_RELATION")
        if r.get("accepted"):
            assert r["verdict"] == "RELATION"
            assert r["relation_type"] and r["mechanism"] and r["grounding"]
    # accepted count is internally consistent and no ungrounded relation slips through
    assert ingest_stats["accepted_relations"] == sum(1 for r in results if r["accepted"])
    assert ingest_stats["rejected_ungrounded"] >= 0


def test_audited_pairs_were_real_candidates(cands, ingest_stats):
    if not RESULTS.exists():
        pytest.skip("no audit verdicts ingested yet")
    cand_pairs = {(c["source_card"], c["target_card"]) for c in cands}
    results = [json.loads(l) for l in RESULTS.read_text(encoding="utf-8").splitlines()]
    for r in results:
        assert (r["source_card"], r["target_card"]) in cand_pairs

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

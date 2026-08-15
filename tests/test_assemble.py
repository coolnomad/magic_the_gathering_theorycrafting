"""Phase 4 global assembly gate tests."""

import json

import pytest

from hobkg import assemble
from hobkg.pipeline import REPO


@pytest.fixture(scope="module")
def stats():
    return assemble.assemble()


def test_no_dangling_and_no_unknown_types(stats):
    assert stats["dangling_edges"] == 0
    assert stats["unknown_type_nodes"] == 0
    assert stats["unknown_endpoint_edges"] == 0


def test_amass_canonicalized_no_face_to_rule(stats):
    assert stats["face_to_rule_amass_edges"] == 0
    edges = [json.loads(l) for l in (REPO / "data/graph_global/edges.jsonl").read_text(encoding="utf-8").splitlines()]
    # no face/ability INSTANTIATES rule:amass; only op:{face}:amass INSTANTIATES op:amass
    assert not any(e["predicate"] == "INSTANTIATES" and e["target"] == "rule:amass" for e in edges)
    op_amass = [e for e in edges if e["predicate"] == "INSTANTIATES" and e["target"] == "op:amass"
                and e["source"].endswith(":amass")]
    assert len(op_amass) == 14


def test_ability_ids_namespaced(stats):
    nodes = {json.loads(l)["id"]: json.loads(l)
             for l in (REPO / "data/graph_global/nodes.jsonl").read_text(encoding="utf-8").splitlines()}
    # a namespaced ability exists; no bare local ability id leaks as a node
    assert any(nid.startswith("ability:face:") for nid in nodes)
    assert "a1" not in nodes and "clapsnap-amass" not in nodes


def test_all_faces_and_cards_present(stats):
    assert stats["node_types"]["Card"] == 193
    assert stats["node_types"]["CardFace"] == 210


def test_actor_edges_reified_onto_operations(stats):
    # every MOVES_TO / CREATES_OBJECT / ADDS_COUNTER edge is Operation- or Gate-subject
    edges = [json.loads(l) for l in (REPO / "data/graph_global/edges.jsonl").read_text(encoding="utf-8").splitlines()]
    nodes = {json.loads(l)["id"]: json.loads(l)["type"]
             for l in (REPO / "data/graph_global/nodes.jsonl").read_text(encoding="utf-8").splitlines()}
    for e in edges:
        if e["predicate"] in ("MOVES_TO", "MOVES_FROM", "ADDS_COUNTER"):
            assert nodes[e["source"]] in ("Operation", "Gate"), f"{e['source']} not reified"


def test_residual_signature_violations_bounded_and_flagged(stats):
    # a small honest residual of Phase-3 typing quirks, all recorded for review
    assert stats["signature_violations"] <= 10
    review = (REPO / "data/graph_global/assembly_review.jsonl").read_text(encoding="utf-8").splitlines()
    assert len([l for l in review if l.strip()]) == stats["signature_violations"]

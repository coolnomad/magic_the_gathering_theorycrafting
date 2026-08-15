"""Phase 5 mechanical card-pair projection gate tests."""

import json

import pytest

from hobkg import project
from hobkg.pipeline import REPO

PROJ = REPO / "data" / "graph_global" / "card_pair_projection.jsonl"
_REQUIRED = {"source_card", "target_card", "relation", "primitive_path", "path_predicates",
             "edge_ids", "combined_conditions", "infrastructure_only", "min_path_length",
             "involves_gate", "involves_state", "self_pair", "provenance"}


@pytest.fixture(scope="module")
def stats():
    return project.project()


@pytest.fixture(scope="module")
def metaedges():
    return [json.loads(l) for l in PROJ.read_text(encoding="utf-8").splitlines()]


def test_every_metaedge_has_full_schema(metaedges):
    assert metaedges
    for m in metaedges:
        assert _REQUIRED <= set(m)
        assert m["min_path_length"] == len(m["path_predicates"]) >= 1
        assert m["provenance"]                       # provenance closure is non-empty


def test_derived_not_bruteforced(stats):
    # the vast majority of the 37,249 ordered pairs have NO relation and emit nothing
    assert stats["distinct_ordered_pairs"] < stats["possible_ordered_pairs"] * 0.3
    assert stats["possible_ordered_pairs"] == 193 * 193


def test_no_ontology_only_joins(metaedges):
    # sharing a creature type/supertype/subtype must never be a join point
    for m in metaedges:
        assert not any(n.startswith(("obj:type:", "obj:subtype:", "obj:supertype:"))
                       for n in m["primitive_path"])


def test_dedup_one_per_pair_relation(metaedges):
    from collections import Counter
    c = Counter((m["source_card"], m["target_card"], m["relation"]) for m in metaedges)
    assert all(v == 1 for v in c.values())


def test_infrastructure_casting_flagged(metaedges):
    infra = [m for m in metaedges if m["relation"] == "INFRASTRUCTURE_CASTING"]
    assert infra and all(m["infrastructure_only"] for m in infra)
    # mana -> casting-cost shape
    assert all(m["path_predicates"][0] == "PRODUCES" for m in infra)


def test_contributes_to_gate_involves_gate_and_state(metaedges):
    gate = [m for m in metaedges if m["relation"] == "CONTRIBUTES_TO_GATE"]
    assert gate and all(m["involves_gate"] for m in gate)
    # storied: A qualifies for the gate, the gate's state enables B's payoff
    assert all(m["path_predicates"][0] in ("QUALIFIES_FOR", "CONTRIBUTES_TO") for m in gate)


def test_bilbo_opponent_mana_not_projected_as_infrastructure(metaedges):
    # Bilbo's Gambit makes an OPPONENT's Treasure — it must not project as supplying
    # the controller's casting mana to any card.
    bilbo = "card:ef71ef07-8a35-41ec-a851-d95e9e3a221b"
    assert not any(m["source_card"] == bilbo and m["relation"] == "INFRASTRUCTURE_CASTING"
                   for m in metaedges)


def test_projection_is_byte_identical():
    import hashlib
    def digest():
        project.project()
        return hashlib.sha256(PROJ.read_bytes()).hexdigest()
    assert digest() == digest()

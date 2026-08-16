"""Phase 6 completion: coverage report + gold-set gate tests."""

import json

import pytest

from hobkg import coverage
from hobkg.pipeline import REPO

G = REPO / "data" / "graph_global"


@pytest.fixture(scope="module")
def cov():
    return coverage.coverage()


@pytest.fixture(scope="module")
def gold():
    return coverage.gold_set()


def test_coverage_core_numbers(cov):
    assert cov["cards_parsed"] == 193 and cov["faces_parsed"] == 210
    assert cov["edges_without_provenance"] == 0             # every edge has provenance
    assert cov["pair_relations_total"] > 0
    # required coverage dimensions are all present
    for k in ("abilities_by_kind", "edges_by_predicate", "pair_relations_by_type",
              "pairs_with_multiple_relation_types", "gate_mediated_relations",
              "infrastructure_only_pairs", "cards_no_noninfra_outgoing",
              "cards_no_noninfra_incoming"):
        assert k in cov


def test_coverage_written(cov):
    assert (G / "coverage.json").exists()
    disk = json.loads((G / "coverage.json").read_text(encoding="utf-8"))
    assert disk["pair_relations_total"] == cov["pair_relations_total"]


def test_gold_set_strata_match_spec(gold):
    s = gold["strata"]
    assert s["recruit"] == 10 and s["storied"] == 9 and s["adventures"] == 17 and s["sagas"] == 8
    assert s["null_pairs"] >= 20 and s["self_pairs"] >= 10 and s["multi_edge_pairs"] >= 20
    assert s["replacement_effects"] >= 1


def test_gold_set_written():
    coverage.gold_set()
    lines = (G / "gold_set.jsonl").read_text(encoding="utf-8").splitlines()
    strata = {json.loads(l)["stratum"] for l in lines}
    assert {"recruit", "storied", "adventures", "sagas", "replacement_effects",
            "null_pairs", "self_pairs", "multi_edge_pairs"} <= strata

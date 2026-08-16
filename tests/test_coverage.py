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
    for k in ("abilities_by_kind", "edges_by_predicate", "pair_relations_by_type",
              "pairs_with_multiple_relation_types", "gate_mediated_relations",
              "infrastructure_only_pairs", "cards_no_noninfra_outgoing",
              "cards_no_noninfra_incoming"):
        assert k in cov


def test_coverage_reports_all_layers_and_union(cov):
    # frozen + repair layers reported SEPARATELY and as a deduplicated union (not just Phase 4)
    assert cov["edges_frozen"] == 2728 and cov["edges_repair"] == 9
    assert cov["edges_union"] == cov["edges_frozen"] + cov["edges_repair"]
    assert cov["edges_by_origin"].get("graph_repair") == 9
    assert cov["relations_union"] == (cov["relations_mechanical"] + cov["relations_audited"]
                                      + cov["relations_repaired"])
    assert cov["relations_repaired"] == 8 and cov["relations_audited"] == 3


def test_pair_index_is_complete_37249():
    s = coverage.pair_index()
    assert s["pair_records"] == 37249 == s["possible_ordered_pairs"]   # 193^2, empties included
    assert s["nonempty_pairs"] + s["empty_pairs"] == 37249
    lines = (G / "pair_index.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 37249
    rec = json.loads(lines[0])
    assert {"source_card", "target_card", "mechanical", "audited", "repaired", "total_relations"} <= set(rec)


def test_coverage_written(cov):
    assert (G / "coverage.json").exists()
    disk = json.loads((G / "coverage.json").read_text(encoding="utf-8"))
    assert disk["pair_relations_total"] == cov["pair_relations_total"]


def test_gold_set_strata_match_spec(gold):
    s = gold["strata"]
    assert s["recruit"] == 10 and s["storied"] == 9 and s["adventures"] == 17 and s["sagas"] == 8
    assert s["null_pairs"] >= 20 and s["self_pairs"] >= 10 and s["multi_edge_pairs"] >= 20
    assert s["replacement_effects"] >= 1


def test_gold_set_is_adjudicated_and_diversified(gold):
    # verdicts present (not an open queue) and every deterministic check passes
    assert gold["passed"] == gold["total_items"] and gold["failed"] == 0
    # null pairs use 20 DISTINCT source cards, not one repeated source
    assert gold["distinct_null_sources"] == 20
    lines = (G / "gold_set.jsonl").read_text(encoding="utf-8").splitlines()
    for l in lines:
        rec = json.loads(l)
        for it in rec["items"]:
            assert it["disposition"] in ("pass", "fail") and it["expected"]
    # multi-edge pairs cover DISTINCT relation combinations (diversified)
    me = next(json.loads(l) for l in lines if json.loads(l)["stratum"] == "multi_edge_pairs")
    combos = {tuple(sorted(it["ids"])) for it in me["items"]}
    assert len(combos) == len(me["items"])

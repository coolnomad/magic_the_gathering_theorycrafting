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
def sv():
    return coverage.structural_validation_set()


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
    # frozen + repair + legend layers reported SEPARATELY and as a deduplicated union
    # (the completed graph, not just Phase 4). The legend layer (Phase 6 v3.2 SBA transition)
    # must be counted — the pt3 review flagged its omission.
    assert cov["edges_frozen"] == 2728 and cov["edges_repair"] == 9 and cov["edges_legend"] == 113
    assert cov["nodes_legend"] == 58
    assert cov["edges_union"] == cov["edges_frozen"] + cov["edges_repair"] + cov["edges_legend"] == 2850
    assert cov["edges_by_origin"].get("graph_repair") == 9
    assert cov["edges_by_origin"].get("legend_rule") == 113   # legend layer in the origin counts
    assert cov["edges_without_provenance"] == 0               # incl. every legend edge
    # abilities counted over the UNIFIED node set — the legend SBA ability must be included
    assert cov["abilities_by_kind"].get("state_based_action") == 1
    assert cov["relations_union"] == (cov["relations_mechanical"] + cov["relations_audited"]
                                      + cov["relations_repaired"])
    assert cov["relations_repaired"] == 8 and cov["relations_audited"] == 3


def test_coverage_labels_invariant2_deferred(cov):
    # the pt3 review: invariant #2 (Recruit<->Councillors second-draw ordering) is an unresolved
    # representational gap, not a completed invariant — it must be LABELED deferred/unmodeled.
    deferred = {d["id"]: d for d in cov["deferred_invariants"]}
    assert 2 in deferred and deferred[2]["status"] == "deferred_unmodeled"
    assert "second" in deferred[2]["reason"].lower() and "cards-drawn" in deferred[2]["reason"].lower()


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


def test_structural_validation_strata_match_spec(sv):
    s = sv["strata"]
    assert s["recruit"] == 10 and s["storied"] == 9 and s["adventures"] == 17 and s["sagas"] == 8
    assert s["null_pairs"] >= 20 and s["self_pairs"] >= 10
    assert s["replacement_effects"] >= 1


def test_structural_validation_is_adjudicated_and_diversified(sv):
    # verdicts present (not an open queue) and every deterministic check passes
    assert sv["passed"] == sv["total_items"] and sv["failed"] == 0
    # null pairs use 20 DISTINCT source cards, not one repeated source
    assert sv["distinct_null_sources"] == 20
    lines = (G / "structural_validation_set.jsonl").read_text(encoding="utf-8").splitlines()
    for l in lines:
        rec = json.loads(l)
        for it in rec["items"]:
            assert it["disposition"] in ("pass", "fail") and it["expected"]


def test_multi_edge_stratum_covers_distinct_relation_COMBINATIONS(sv):
    # the reviewer's finding: the old sampler drew 20 rows that were all ONE combination and
    # the test only checked distinct pair-IDs. Now each item must be a distinct COMBINATION of
    # relation types, drawn from the UNION of all three projection layers.
    lines = (G / "structural_validation_set.jsonl").read_text(encoding="utf-8").splitlines()
    me = next(json.loads(l) for l in lines if json.loads(l)["stratum"] == "multi_edge_pairs")
    combos = {tuple(it["relation_combination"]) for it in me["items"]}
    assert len(combos) == len(me["items"])            # every row is a *distinct* combination
    assert sv["distinct_multi_edge_combos"] == len(combos)
    # the union of layers must surface MORE than the single mechanical-only combo
    assert len(combos) >= 2
    assert ("CONTRIBUTES_TO_GATE", "INFRASTRUCTURE_CASTING") in combos
    assert ("ENABLES_TRIGGER", "INFRASTRUCTURE_CASTING") in combos  # only visible via audit/repair layers


def test_saga_stratum_is_not_a_tautology(sv):
    # Saga adjudication must assert real chapter/lore structure, not "subtype is Saga" (which is
    # trivially true for the very cards selected BY subtype Saga).
    lines = (G / "structural_validation_set.jsonl").read_text(encoding="utf-8").splitlines()
    sagas = next(json.loads(l) for l in lines if json.loads(l)["stratum"] == "sagas")
    for it in sagas["items"]:
        assert "lore" in it["expected"].lower() or "saga" in it["expected"].lower()
        assert "type-confirmed" not in it["expected"]     # the old tautological phrasing is gone


def test_self_pair_stratum_checks_reflexive_resolution(sv):
    # self-pair adjudication must assert the reflexive effect is not routed through an
    # "another/other" object class (which would be a DIFFERENT copy), not "source == target".
    lines = (G / "structural_validation_set.jsonl").read_text(encoding="utf-8").splitlines()
    sp = next(json.loads(l) for l in lines if json.loads(l)["stratum"] == "self_pairs")
    for it in sp["items"]:
        assert "another/other" in it["expected"] and "reflexive" in it["expected"]

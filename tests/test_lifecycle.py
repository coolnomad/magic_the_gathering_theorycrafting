"""Executability layer (pt7): permanent-lifecycle transitions + explicit OR cost gates."""

import hashlib

import pytest

from hobkg import lifecycle as lc
from hobkg.pipeline import REPO, _load_dicts

G = REPO / "data" / "graph_global"


@pytest.fixture(scope="module")
def mat():
    return lc.materialize()


@pytest.fixture(scope="module")
def lnodes(mat):
    return {n["id"]: n for n in _load_dicts(G / "lifecycle_nodes.jsonl")}


@pytest.fixture(scope="module")
def ledges(mat):
    return list(_load_dicts(G / "lifecycle_edges.jsonl"))


def test_additive_and_signature_valid(mat):
    assert mat["signature_violations"] == 0
    frozen = list(_load_dicts(G / "edges.jsonl"))
    assert not any(e.get("origin") == "lifecycle" for e in frozen)   # frozen graph untouched
    for e in _load_dicts(G / "lifecycle_edges.jsonl"):
        assert e["origin"] == "lifecycle" and e.get("provenance")


def test_schema_extension_predicates_registered():
    # TERMINATES and HAS_ALTERNATIVE are registered in the global signature table (recorded ext.)
    from hobkg.assemble import GLOBAL_SIGNATURES
    assert "TERMINATES" in GLOBAL_SIGNATURES and "HAS_ALTERNATIVE" in GLOBAL_SIGNATURES
    assert GLOBAL_SIGNATURES["TERMINATES"][1] == {"State"}


def test_every_attachment_state_has_a_leave_battlefield_transition(mat, lnodes, ledges):
    # every equip attachment state gets an executable leave-battlefield op with the full chain
    attach_states = {n["id"] for n in _load_dicts(G / "equip_nodes.jsonl")
                     if n["id"].startswith("state:attachment:")}
    assert attach_states and mat["attachment_states_covered"] == len(attach_states)
    assert mat["complete_lifecycle_ops"] == mat["leave_battlefield_ops"] == len(attach_states)
    for state in attach_states:
        host = state[len("state:attachment:"):]
        op = f"op:leave-battlefield:{host}"
        assert op in lnodes
        preds = {(e["predicate"], e["target"]) for e in ledges if e["source"] == op}
        assert ("MOVES_FROM", "zone:battlefield") in preds
        assert ("MOVES_TO", "zone:graveyard") in preds
        assert ("TERMINATES", state) in preds
        assert ("REFERENCES_RULE", lc.RULE_LEAVE) in preds


def test_general_invariant_rule_present(lnodes):
    r = lnodes[lc.RULE_LEAVE]
    assert r["type"] == "Rule" and "leave the battlefield" in r["data"]["invariant"].lower() \
        or "leaves the battlefield" in r["data"]["invariant"].lower()


def test_terminates_targets_are_real_attachment_states(mat, ledges):
    assert mat["unresolved_terminated_states"] == []
    all_nodes = {n["id"] for n in _load_dicts(G / "nodes.jsonl")} \
        | {n["id"] for n in _load_dicts(G / "equip_nodes.jsonl")}
    for e in ledges:
        if e["predicate"] == "TERMINATES":
            assert e["target"].startswith("state:attachment:") and e["target"] in all_nodes


def test_explicit_or_cost_gate_for_stir(mat, lnodes, ledges):
    # Stir Up Trouble's "sacrifice an artifact or creature OR pay {4}" is an explicit OR gate with
    # two HAS_ALTERNATIVE branches (the sacrifice cost gate + a pay-{4} cost)
    assert mat["or_cost_gates"] == 1
    or_gate = next(nid for nid in lnodes if nid.startswith("gate:or-cost:"))
    assert lnodes[or_gate]["data"]["gate_type"] == "or" and lnodes[or_gate]["data"]["pay"] == "{4}"
    alts = [e["target"] for e in ledges if e["source"] == or_gate and e["predicate"] == "HAS_ALTERNATIVE"]
    assert any(a.startswith("gate:completeness:sac-cost:") for a in alts)   # sacrifice branch
    assert any(a.startswith("cost:pay:") for a in alts)                     # pay branch


def test_deterministic():
    def run():
        lc.materialize()
        return hashlib.sha256((G / "lifecycle_edges.jsonl").read_bytes()).hexdigest() \
            + hashlib.sha256((G / "lifecycle_nodes.jsonl").read_bytes()).hexdigest()
    assert run() == run()

"""Executability layer (pt7/pt8): CONNECTED sacrifice -> zone-transition -> attachment
termination traversal + wired OR cost gate. pt8 rejected disconnected primitives, so these
tests assert REACHABILITY from the consuming card, not just node existence."""

import hashlib
import re

import pytest

from hobkg import lifecycle as lc
from hobkg.pipeline import REPO, _load_dicts

G = REPO / "data" / "graph_global"
_U = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


@pytest.fixture(scope="module")
def mat():
    return lc.materialize()


@pytest.fixture(scope="module")
def rep(mat):
    return lc.reproject()


@pytest.fixture(scope="module")
def lnodes(mat):
    return {n["id"]: n for n in _load_dicts(G / "lifecycle_nodes.jsonl")}


@pytest.fixture(scope="module")
def ledges(mat):
    return list(_load_dicts(G / "lifecycle_edges.jsonl"))


@pytest.fixture(scope="module")
def lrel(rep):
    return list(_load_dicts(G / "card_pair_projection_lifecycle.jsonl"))


def _name_to_id():
    return {c["name"]: c["id"] for c in _load_dicts(REPO / "data/normalized/cards.jsonl")}


def test_additive_and_signature_valid(mat):
    assert mat["signature_violations"] == 0
    frozen = list(_load_dicts(G / "edges.jsonl"))
    assert not any(e.get("origin") == "lifecycle" for e in frozen)   # frozen graph untouched
    for e in _load_dicts(G / "lifecycle_edges.jsonl"):
        assert e["origin"] == "lifecycle" and e.get("provenance")


def test_schema_extension_predicates_registered():
    from hobkg.assemble import GLOBAL_SIGNATURES
    assert "TERMINATES" in GLOBAL_SIGNATURES and "HAS_ALTERNATIVE" in GLOBAL_SIGNATURES


def test_cause_specific_sacrifice_transition_with_incoming_edge(mat, lnodes, ledges):
    # pt8 #1 + #3: cause-specific SACRIFICE ops (battlefield->graveyard), each with an INCOMING
    # edge (the permanent hosts its sacrifice transition) — the prior leave op had none.
    attach_states = {n["id"] for n in _load_dicts(G / "equip_nodes.jsonl")
                     if n["id"].startswith("state:attachment:")}
    assert mat["connected_sacrifice_ops"] == mat["sacrifice_ops"] == len(attach_states)
    incoming = {e["target"] for e in ledges}
    for state in attach_states:
        host = state[len("state:attachment:"):]
        op = f"op:sacrifice:{host}"
        assert op in lnodes and lnodes[op]["data"]["cause"] == "sacrifice"
        assert op in incoming, f"{op} has no incoming edge"          # pt8 #1
        out = {(e["predicate"], e["target"]) for e in ledges if e["source"] == op}
        assert ("MOVES_FROM", "zone:battlefield") in out
        assert ("MOVES_TO", "zone:graveyard") in out
        assert ("TERMINATES", state) in out
        # pt9: the incoming edge is CAN_UNDERGO from the host (a transition, not an "ability")
        assert any(e["source"] == host and e["predicate"] == "CAN_UNDERGO" and e["target"] == op for e in ledges)
        assert not any(e["predicate"] == "HAS_ABILITY" and e["target"] == op for e in ledges)


def test_rules_provenance_corrected(lnodes, ledges):
    # pt8 #4: NOT 603.6e; use 701.3d / 400.7 / 611.3b / 301.5 / 704.5n
    provs = [p.get("rule_ref", "") for e in ledges for p in e.get("provenance", [])]
    assert provs and all("603.6e" not in r for r in provs)
    assert any("701.3d" in r for r in provs) and any("704.5n" in r for r in provs)


def test_or_gate_is_reachable_from_stir(mat, lnodes, ledges):
    # pt8 #2: the OR gate has an INCOMING REQUIRES from Stir's additional-cost ability, and
    # HAS_ALTERNATIVE its two branch operations.
    assert mat["or_cost_gates"] == 1
    or_gate = next(nid for nid in lnodes if nid.startswith("gate:or-cost:"))
    incoming = [e for e in ledges if e["target"] == or_gate]
    assert incoming and incoming[0]["predicate"] == "REQUIRES"           # gate is reachable
    assert incoming[0]["source"].startswith("ability:completeness:sac:")  # from Stir's additional-cost ability
    alts = [e["target"] for e in ledges if e["source"] == or_gate and e["predicate"] == "HAS_ALTERNATIVE"]
    assert any(a.startswith("op:completeness:sac:") for a in alts)       # sacrifice branch op
    assert any(a.startswith("op:pay:") for a in alts)                    # pay branch op


def test_or_gate_is_mutually_exclusive_pay_branch_consumes_nothing(lnodes, ledges):
    # THE pt9 decisive regression: only the CHOSEN branch executes. Executing the pay branch must
    # NOT consume a permanent or terminate an attachment; the sacrifice op executes ONLY on the
    # sacrifice branch (both its incoming CAUSES gated by the sacrifice-branch condition).
    import hobkg.completeness as cc
    or_gate = next(nid for nid in lnodes if nid.startswith("gate:or-cost:"))
    assert lnodes[or_gate]["data"]["mutually_exclusive"] is True
    fid = or_gate[len("gate:or-cost:"):]
    sac_op, pay_op = f"op:completeness:sac:{fid}", f"op:pay:{fid}"
    comp = list(_load_dicts(G / "completeness_edges.jsonl"))
    everything = ledges + comp
    # (a) every CAUSES into the sacrifice op is gated by the sacrifice-branch condition
    into_sac = [e for e in everything if e["predicate"] == "CAUSES" and e["target"] == sac_op]
    assert into_sac and all(cc.COND_OR_SACRIFICE in (e.get("condition_ids") or []) for e in into_sac)
    # (b) the pay op is gated by the pay-branch condition and consumes/terminates NOTHING
    into_pay = [e for e in ledges if e["predicate"] == "CAUSES" and e["target"] == pay_op]
    assert into_pay and all(cc.COND_OR_PAY in (e.get("condition_ids") or []) for e in into_pay)
    pay_out = {e["predicate"] for e in ledges if e["source"] == pay_op}
    assert "CONSUMES" not in pay_out and "TERMINATES" not in pay_out
    # (c) the two branch conditions are mutually exclusive
    conds = {c["condition_id"]: c for c in _load_dicts(G / "completeness_conditions.jsonl")}
    assert conds[cc.COND_OR_PAY]["expression"]["mutually_exclusive_with"] == cc.COND_OR_SACRIFICE
    assert conds[cc.COND_OR_SACRIFICE]["expression"]["mutually_exclusive_with"] == cc.COND_OR_PAY


def test_executable_traversal_is_continuous_and_reaches_termination(rep, lrel):
    # THE pt8 decisive regression: a continuous BOUND path from the consumer to the termination of
    # the sacrificed permanent's attachment state (consumer -> sac op -> P -> zone transition ->
    # TERMINATES P's attachment). Not just existence — a real traversal.
    assert rep["paths_continuous"] and rep["paths_card_grounded"] and rep["paths_reach_attachment_termination"]
    edges = {}
    for f in ("edges.jsonl", "completeness_edges.jsonl", "lifecycle_edges.jsonl"):
        for e in _load_dicts(G / f):
            edges[e["edge_id"]] = e
    assert lrel
    for m in lrel:
        st = m["steps"]
        for a, b in zip(st, st[1:]):
            assert a["target"] == b["source"]                          # continuity
        assert _U.search(st[0]["source"]) and ("card:" + _U.search(st[0]["source"]).group(0)) == m["source_card"]
        assert m["primitive_path"][-1].startswith("state:attachment:")  # ends at the termination
        assert ("card:" + _U.search(m["primitive_path"][-1]).group(0)) == m["target_card"]
        for s in st:
            assert s["edge_id"] in edges                              # every step resolves
        # the path traverses CONSUMES (sacrifice) and TERMINATES (attachment ends)
        assert "CONSUMES" in m["path_predicates"] and "TERMINATES" in m["path_predicates"]


def test_stir_and_snowslope_sacrifice_crude(lrel):
    # flagship pt8: Stir Up Trouble AND Snowslope Hunter can sacrifice Crude Bent Blade and thereby
    # terminate its attachment (executable), with the full grounded path.
    n = _name_to_id()
    crude = n["Crude Bent Blade"]
    for outlet in ("Stir Up Trouble", "Snowslope Hunter"):
        ms = [m for m in lrel if m["source_card"] == n[outlet] and m["target_card"] == crude]
        assert ms, f"{outlet} -> Crude executable traversal missing"
        m = ms[0]
        assert m["relation"] == "SACRIFICE_TERMINATES_ATTACHMENT" and m["executable"]
        assert m["path_predicates"] == ["HAS_FACE", "HAS_ABILITY", "CAUSES", "CONSUMES",
                                        "HAS_TYPE", "CAN_UNDERGO", "TERMINATES"]


def test_deterministic():
    def run():
        lc.materialize()
        lc.reproject()
        return (hashlib.sha256((G / "lifecycle_edges.jsonl").read_bytes()).hexdigest()
                + hashlib.sha256((G / "card_pair_projection_lifecycle.jsonl").read_bytes()).hexdigest())
    assert run() == run()

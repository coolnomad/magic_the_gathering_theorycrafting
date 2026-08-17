"""Executability layer (pt7): permanent-lifecycle state-transitions + explicit OR cost gates.

The analytical graph records that sacrificing an attached Equipment ends its bonus only as pair
metadata (`terminates_attachment: true`). This layer makes it an EXECUTABLE primitive so a
simulator / intervention engine can run the change, and models Stir Up Trouble's "sacrifice OR
pay {4}" as an explicit OR gate rather than gate data.

Additive (`data/graph_global/lifecycle_{nodes,edges}.jsonl`, origin `lifecycle`); the frozen
graph and all other layers are untouched. Uses the schema-extension predicates `TERMINATES` and
`HAS_ALTERNATIVE` (added to `assemble.GLOBAL_SIGNATURES`; recorded in LABNOTEBOOK).

Per attachment state `state:attachment:H` (one per Equipment host H, from the equip layer):

    op:leave-battlefield:H  MOVES_FROM -> zone:battlefield
    op:leave-battlefield:H  MOVES_TO   -> zone:graveyard
    op:leave-battlefield:H  TERMINATES -> state:attachment:H
    op:leave-battlefield:H  REFERENCES_RULE -> rule:leave-battlefield-terminates-attachment

The rule node encodes the GENERAL invariant: *when a permanent leaves the battlefield, terminate
every attachment state it hosts and every continuous effect requiring that state* (the effects
—`op:modify-equipped:H` / `op:grant-equipped:H`— REQUIRE the state, so ending it ends them).

For each OR sacrifice cost (Stir's "sacrifice an artifact or creature OR pay {4}"):

    gate:or-cost:{face}  HAS_ALTERNATIVE -> gate:completeness:sac-cost:{face}   (the sacrifice branch)
    gate:or-cost:{face}  HAS_ALTERNATIVE -> cost:pay:{mana}                     (the pay branch)
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from .pipeline import REPO, _load_dicts

RULE_LEAVE = "rule:leave-battlefield-terminates-attachment"
ZONE_BATTLEFIELD = "zone:battlefield"
ZONE_GRAVEYARD = "zone:graveyard"
_CR = "CR 603.6e / 704 (state-based actions) / 701.17 (Sacrifice)"


def _opt(path: Path):
    return list(_load_dicts(path)) if path.exists() else []


def _mid(source: str, predicate: str, target: str) -> str:
    return "lf" + hashlib.sha1(f"{source}|{predicate}|{target}".encode("utf-8")).hexdigest()[:14]


def materialize(repo: Path = REPO) -> dict:
    G = repo / "data" / "graph_global"
    frozen_nodes = {n["id"]: n for n in _load_dicts(G / "nodes.jsonl")}
    equip_nodes = {n["id"]: n for n in _opt(G / "equip_nodes.jsonl")}
    completeness_nodes = {n["id"]: n for n in _opt(G / "completeness_nodes.jsonl")}
    all_nodes = {**frozen_nodes, **equip_nodes, **completeness_nodes}

    nodes: dict = {}
    edges: list = []

    def node(nid, ntype, label, data, note):
        nodes.setdefault(nid, {"id": nid, "type": ntype, "label": label, "data": data,
                               "provenance": [{"source": "lifecycle", "rule_ref": _CR, "derivation": note}],
                               "origin": "lifecycle"})

    def edge(source, predicate, target, note, **props):
        edges.append({"edge_id": _mid(source, predicate, target), "source": source, "predicate": predicate,
                      "target": target, "provenance": [{"source": "lifecycle", "rule_ref": _CR, "derivation": note}],
                      "origin": "lifecycle", **props})

    # the general invariant (leave-battlefield -> terminate hosted attachment states + their effects)
    node(RULE_LEAVE, "Rule", "leaving the battlefield terminates attachment",
         {"invariant": ("When a permanent P leaves the battlefield, terminate every attachment state "
                        "hosted by P and every continuous effect that requires that state."),
          "cr": "603.6e / 704"}, "the general leave-battlefield termination invariant")

    # ---- per-Equipment lifecycle transition ---------------------------------------------
    attach_states = sorted(n for n in equip_nodes if n.startswith("state:attachment:"))
    for state in attach_states:
        host = state[len("state:attachment:"):]           # face:… or token:axe
        op = f"op:leave-battlefield:{host}"
        name = equip_nodes[state]["data"].get("equipment", host)
        node(op, "Operation", f"{name} leaves the battlefield",
             {"kind": "leave_battlefield", "equipment": name, "host": host,
              "terminates": state}, "a permanent leaving the battlefield (sacrifice/destroy/etc.)")
        edge(op, "MOVES_FROM", ZONE_BATTLEFIELD, "the permanent moves off the battlefield")
        edge(op, "MOVES_TO", ZONE_GRAVEYARD, "the sacrificed/destroyed permanent goes to its owner's graveyard")
        edge(op, "TERMINATES", state, "leaving the battlefield ends this Equipment's attachment state")
        edge(op, "REFERENCES_RULE", RULE_LEAVE, "instance of the general leave-battlefield invariant")

    # ---- explicit OR cost gate for OR sacrifice costs (Stir's "... OR pay {4}") ----------
    or_gates = 0
    for gid, n in sorted(completeness_nodes.items()):
        if not gid.startswith("gate:") or "sac-cost" not in gid:
            continue
        or_pay = (n.get("data") or {}).get("or_pay")
        if not or_pay:
            continue
        or_gates += 1
        or_gate = gid.replace("gate:completeness:sac-cost:", "gate:or-cost:")
        pay_cost = f"cost:pay:{or_pay}"
        node(or_gate, "Gate", f"OR cost: sacrifice or pay {or_pay}",
             {"gate_type": "or", "branches": ["sacrifice", "pay"], "pay": or_pay,
              "sacrifice_branch": gid}, "explicit OR cost gate: sacrifice OR pay")
        node(pay_cost, "Cost", f"pay {or_pay}", {"mana_cost": or_pay, "kind": "mana"},
             "the pay-mana alternative of the OR cost")
        edge(or_gate, "HAS_ALTERNATIVE", gid, "the sacrifice branch of the OR cost")
        edge(or_gate, "HAS_ALTERNATIVE", pay_cost, "the pay-mana branch of the OR cost")

    # ---- write + validate ----------------------------------------------------------------
    uniq = {}
    for e in edges:
        uniq.setdefault(e["edge_id"], e)
    edges = sorted(uniq.values(), key=lambda e: (e["source"], e["predicate"], e["target"]))
    with (G / "lifecycle_nodes.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for n in sorted(nodes.values(), key=lambda n: n["id"]):
            fh.write(json.dumps(n, ensure_ascii=False, sort_keys=True) + "\n")
    with (G / "lifecycle_edges.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for e in edges:
            fh.write(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n")

    from .graph_repair import _validate_repair_layer
    violations = _validate_repair_layer(repo, all_nodes, nodes, edges)
    # integrity: every TERMINATES target is a real attachment state; every leave op has the full chain
    terminated = {e["target"] for e in edges if e["predicate"] == "TERMINATES"}
    missing_state = sorted(s for s in terminated if s not in all_nodes and s not in nodes)
    leave_ops = {n for n in nodes if n.startswith("op:leave-battlefield:")}
    complete_ops = 0
    for op in leave_ops:
        preds = {e["predicate"] for e in edges if e["source"] == op}
        if {"MOVES_FROM", "MOVES_TO", "TERMINATES", "REFERENCES_RULE"} <= preds:
            complete_ops += 1
    _report(repo, nodes, edges, len(attach_states), or_gates)
    return {"lifecycle_nodes": len(nodes), "lifecycle_edges": len(edges),
            "leave_battlefield_ops": len(leave_ops), "complete_lifecycle_ops": complete_ops,
            "attachment_states_covered": len(attach_states), "or_cost_gates": or_gates,
            "unresolved_terminated_states": missing_state, "signature_violations": len(violations),
            "_violations": violations}


def _report(repo: Path, nodes: dict, edges: list, n_states: int, or_gates: int) -> None:
    L = ["# HOB Executability Layer — Lifecycle Transitions + OR Cost Gates (pt7)", "",
         f"- **lifecycle nodes**: {len(nodes)}  · **edges**: {len(edges)}",
         f"- **attachment states with a leave-battlefield termination**: {n_states}",
         f"- **explicit OR cost gates**: {or_gates}",
         "- new schema-extension predicates: `TERMINATES` (Op/Event/State → State), "
         "`HAS_ALTERNATIVE` (Gate → Gate/Cost/Operation)", "",
         "## General invariant", "",
         "`rule:leave-battlefield-terminates-attachment` — when a permanent leaves the battlefield, "
         "terminate every attachment state it hosts and every continuous effect requiring that state.", "",
         "## Sample transitions", ""]
    for e in edges:
        if e["predicate"] == "TERMINATES":
            L.append(f"- `{e['source']}` TERMINATES `{e['target']}`")
    (repo / "reports" / "lifecycle.md").write_text("\n".join(L[:80]) + "\n", encoding="utf-8")

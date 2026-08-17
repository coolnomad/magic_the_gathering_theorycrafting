"""Executability layer (pt7/pt8): a CONNECTED, reachable sacrifice → zone-transition →
attachment-termination traversal, plus Stir's OR cost wired into its execution path.

pt8 rejected the first cut (`21a5933`) for the pt5 failure class — the lifecycle pieces existed
but were disconnected: the per-Equipment leave op had no incoming edges, and the OR gate had none.
This layer wires them into an executable mechanism a simulator can traverse.

Additive (`data/graph_global/lifecycle_{nodes,edges}.jsonl` + `card_pair_projection_lifecycle.jsonl`,
origin `lifecycle`). Uses the schema-extension predicates `TERMINATES` and `HAS_ALTERNATIVE`.

Per Equipment host H (from the equip layer's `state:attachment:H`):

    H  HAS_ABILITY -> op:sacrifice:H                 (H can be sacrificed — the incoming edge pt8 wanted)
    op:sacrifice:H  MOVES_FROM -> zone:battlefield   (cause-specific: sacrifice, battlefield -> graveyard —
    op:sacrifice:H  MOVES_TO   -> zone:graveyard      NOT a generic "leave" hardcoded to graveyard)
    op:sacrifice:H  TERMINATES -> state:attachment:H
    op:sacrifice:H  REFERENCES_RULE -> rule:leave-battlefield-terminates-attachment

Reprojection — the executable bound traversal (source = the outlet, target = the sacrificed Equipment):

    card:O -HAS_FACE-> face:O -HAS_ABILITY-> ability:sac(O) -CAUSES-> op:sac(O)
           -CONSUMES-> obj:type:{artifact|creature} <-HAS_TYPE- face:P
           -HAS_ABILITY-> op:sacrifice:P -TERMINATES-> state:attachment:P

so a simulator can bind the sacrificed object P, run P's zone transition, and end P's attachment.

Stir's OR cost is wired: `ability:completeness:sac:{stir} REQUIRES gate:or-cost:{stir}`, and the OR
gate HAS_ALTERNATIVE the sacrifice cost gate + an explicit `cost:pay:{4}`.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from . import project
from .completeness import (SAC_OUTLETS, OBJ_TYPE_ARTIFACT, OBJ_TYPE_CREATURE,
                           COND_OR_SACRIFICE, COND_OR_PAY)
from .pipeline import REPO, _load_dicts

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
RULE_LEAVE = "rule:leave-battlefield-terminates-attachment"
ZONE_BATTLEFIELD = "zone:battlefield"
ZONE_GRAVEYARD = "zone:graveyard"
# correct rules (pt8): NOT 603.6e (that is an Aura leave-the-battlefield trigger)
_CR = ("CR 701.3d (Equipment leaving the battlefield becomes unattached) / 400.7 (zone change = new "
       "object) / 611.3b (a static continuous effect applies while its source is on the battlefield) / "
       "301.5, 704.5n (Equipment attachment legality)")


def _card_of(nid: str):
    m = _UUID.search(nid or "")
    return "card:" + m.group(0) if m else None


def _opt(path: Path):
    return list(_load_dicts(path)) if path.exists() else []


def _mid(source: str, predicate: str, target: str) -> str:
    return "lf" + hashlib.sha1(f"{source}|{predicate}|{target}".encode("utf-8")).hexdigest()[:14]


def _step(edge: dict, direction: str) -> dict:
    s = project._step(edge, direction)
    s.pop("provenance", None)
    return s


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

    node(RULE_LEAVE, "Rule", "leaving the battlefield terminates attachment",
         {"invariant": ("When a permanent P leaves the battlefield, terminate every attachment state "
                        "hosted by P and every continuous effect that requires that state."),
          "cr": "701.3d / 400.7 / 611.3b / 301.5 / 704.5n"},
         "the general leave-battlefield termination invariant")

    # ---- per-Equipment cause-specific SACRIFICE transition (connected via HAS_ABILITY) ----
    attach_states = sorted(n for n in equip_nodes if n.startswith("state:attachment:"))
    for state in attach_states:
        host = state[len("state:attachment:"):]           # face:… or token:axe
        op = f"op:sacrifice:{host}"
        name = equip_nodes[state]["data"].get("equipment", host)
        node(op, "Operation", f"sacrifice {name}",
             {"kind": "sacrifice", "cause": "sacrifice", "equipment": name, "host": host,
              "from_zone": "battlefield", "to_zone": "graveyard", "terminates": state},
             "cause-specific sacrifice transition (battlefield -> graveyard)")
        # the incoming edge pt8 required, with the pt9 semantic-clean predicate: the permanent CAN
        # UNDERGO this sacrifice transition (it is a transition the object undergoes, not an ability
        # it possesses).
        edge(host, "CAN_UNDERGO", op, "the permanent can undergo the sacrifice transition")
        edge(op, "MOVES_FROM", ZONE_BATTLEFIELD, "sacrifice moves the permanent off the battlefield")
        edge(op, "MOVES_TO", ZONE_GRAVEYARD, "the sacrificed permanent goes to its owner's graveyard")
        edge(op, "TERMINATES", state, "sacrificing the Equipment ends its attachment state (and its bonus)")
        edge(op, "REFERENCES_RULE", RULE_LEAVE, "instance of the general leave-battlefield invariant")

    # NOTE (pt10): the explicit mutually-exclusive OR cost gate (gate:or-cost + op:pay + the
    # ability→REQUIRES→gate→CAUSES→{sac,pay} wiring) now lives in the COMPLETENESS layer, so the OR
    # gate is the SOLE causal parent of the sacrifice op and both projections route through it.

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
    terminated = {e["target"] for e in edges if e["predicate"] == "TERMINATES"}
    missing_state = sorted(s for s in terminated if s not in all_nodes and s not in nodes)
    # every sacrifice op has an INCOMING edge (pt8 #1) and the full outgoing chain
    incoming = {e["target"] for e in edges}
    sac_ops = [n for n in nodes if n.startswith("op:sacrifice:")]
    connected_ops = 0
    for op in sac_ops:
        preds = {e["predicate"] for e in edges if e["source"] == op}
        if op in incoming and {"MOVES_FROM", "MOVES_TO", "TERMINATES", "REFERENCES_RULE"} <= preds:
            connected_ops += 1
    return {"lifecycle_nodes": len(nodes), "lifecycle_edges": len(edges),
            "sacrifice_ops": len(sac_ops), "connected_sacrifice_ops": connected_ops,
            "attachment_states_covered": len(attach_states),
            "unresolved_terminated_states": missing_state, "signature_violations": len(violations),
            "_violations": violations}


# --------------------------------------------------------------------------- #
#  Reprojection: the executable bound sacrifice->termination traversal          #
# --------------------------------------------------------------------------- #
def reproject(repo: Path = REPO) -> dict:
    G = repo / "data" / "graph_global"
    frozen = list(_load_dicts(G / "edges.jsonl"))
    lif = list(_load_dicts(G / "lifecycle_edges.jsonl"))
    comp = _opt(G / "completeness_edges.jsonl")
    equip_nodes = {n["id"] for n in _opt(G / "equip_nodes.jsonl")}
    all_edges = frozen + comp + lif
    real_or_layer = {e["edge_id"] for e in all_edges}
    index = {}
    for e in all_edges:
        index.setdefault((e["source"], e["predicate"], e["target"]), e)

    def Ed(source=None, predicate=None, target=None):
        for e in all_edges:
            if (source is None or e["source"] == source) and (predicate is None or e["predicate"] == predicate) \
                    and (target is None or e["target"] == target):
                return e
        return None

    hasface = {}   # card -> HAS_FACE edge
    for e in frozen:
        if e["predicate"] == "HAS_FACE":
            hasface.setdefault(_card_of(e["source"]), e)
    # HAS_TYPE edge per (face, type) for the fodder-binding step
    htype = {}     # (obj_type) -> {face_id: edge}
    for e in frozen:
        if e["predicate"] == "HAS_TYPE" and e["target"] in (OBJ_TYPE_ARTIFACT, OBJ_TYPE_CREATURE):
            htype.setdefault(e["target"], {})[e["source"]] = e
    # the Equipment fodder population: faces that host an attachment state
    equipment_hosts = sorted(n[len("state:attachment:"):] for n in equip_nodes
                             if n.startswith("state:attachment:") and n[len("state:attachment:"):].startswith("face:"))

    metaedges = []

    def emit(o_card, p_card, steps):
        if not o_card or not p_card or o_card == p_card or any(s is None for s in steps):
            return
        for x, y in zip(steps, steps[1:]):
            if x["target"] != y["source"]:
                return
        seq = [steps[0]["source"]] + [s["target"] for s in steps]
        if _card_of(seq[0]) != o_card or _card_of(seq[-1]) != p_card:
            return
        metaedges.append({
            "source_card": o_card, "target_card": p_card, "relation": "SACRIFICE_TERMINATES_ATTACHMENT",
            "origin": "lifecycle", "path_kind": "grounded", "steps": steps, "primitive_path": seq,
            "path_predicates": [s["predicate"] for s in steps], "edge_ids": [s["edge_id"] for s in steps],
            "connecting_node": seq[1], "terminated_state": seq[-1],
            "executable": True})

    for fid, spec in sorted(SAC_OUTLETS.items()):
        o_card = _card_of(fid)
        hf_o = hasface.get(o_card)
        hab_o = Ed(fid, "HAS_ABILITY", f"ability:completeness:sac:{fid}")
        op_sac = f"op:completeness:sac:{fid}"
        # pt10: the OR gate is the sole causal parent for OR-cost outlets — route the head through
        # ability -REQUIRES-> gate:or-cost -CAUSES-> op:sac; non-OR outlets keep ability -CAUSES-> op:sac.
        if spec.get("or_pay"):
            req_o = Ed(f"ability:completeness:sac:{fid}", "REQUIRES", f"gate:or-cost:{fid}")
            cau_o = Ed(f"gate:or-cost:{fid}", "CAUSES", op_sac)
            cause_steps = [req_o, cau_o] if (req_o and cau_o) else None
        else:
            cau_o = Ed(f"ability:completeness:sac:{fid}", "CAUSES", op_sac)
            cause_steps = [cau_o] if cau_o else None
        if not (hf_o and hab_o and cause_steps):
            continue
        for typ in spec.get("accepts", []):
            cls = OBJ_TYPE_ARTIFACT if typ == "artifact" else OBJ_TYPE_CREATURE
            con = Ed(op_sac, "CONSUMES", cls)
            if not con:
                continue
            head = [_step(hf_o, "forward"), _step(hab_o, "forward")] \
                + [_step(e, "forward") for e in cause_steps] + [_step(con, "forward")]
            # bind the fodder P to each Equipment host of the accepted type + run its sacrifice transition
            for host in equipment_hosts:
                ht = htype.get(cls, {}).get(host)
                sacrifice = Ed(host, "CAN_UNDERGO", f"op:sacrifice:{host}")
                terminates = Ed(f"op:sacrifice:{host}", "TERMINATES", f"state:attachment:{host}")
                if not (ht and sacrifice and terminates):
                    continue
                p_card = _card_of(host)
                steps = head + [_step(ht, "reverse"), _step(sacrifice, "forward"), _step(terminates, "forward")]
                emit(o_card, p_card, steps)

    metaedges.sort(key=lambda m: (m["source_card"], m["target_card"], m["connecting_node"]))
    with (G / "card_pair_projection_lifecycle.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for m in metaedges:
            fh.write(json.dumps(m, ensure_ascii=False, sort_keys=True) + "\n")

    continuous = all(x["target"] == y["source"] for m in metaedges for x, y in zip(m["steps"], m["steps"][1:]))
    grounded = all(_card_of(m["primitive_path"][0]) == m["source_card"]
                   and _card_of(m["primitive_path"][-1]) == m["target_card"] for m in metaedges)
    reaches_termination = all(m["primitive_path"][-1].startswith("state:attachment:") for m in metaedges)
    edges_resolve = all(s["edge_id"] in real_or_layer for m in metaedges for s in m["steps"])
    _report(repo, metaedges, continuous, grounded, reaches_termination, edges_resolve)
    return {"reprojected": len(metaedges), "paths_continuous": continuous, "paths_card_grounded": grounded,
            "paths_reach_attachment_termination": reaches_termination, "edges_resolve": edges_resolve}


def _report(repo, metaedges, continuous, grounded, reaches, ok):
    names = {c["id"]: c["name"] for c in _load_dicts(repo / "data/normalized/cards.jsonl")}
    L = ["# HOB Executability Layer — Sacrifice → Termination Traversal (pt8)", "",
         f"- **executable metaedges**: {len(metaedges)} (origin `lifecycle`, SACRIFICE_TERMINATES_ATTACHMENT)",
         f"- **paths continuous**: {continuous}  · **card-grounded**: {grounded}  · "
         f"**reach attachment termination**: {reaches}  · **edges resolve**: {ok}", "",
         "## Sample executable traversals", ""]
    for m in metaedges[:40]:
        a, b = names.get(m["source_card"], m["source_card"]), names.get(m["target_card"], m["target_card"])
        L.append(f"- **{a} sacrifices {b}** → {' → '.join(m['path_predicates'])} → `{m['terminated_state']}`")
    (repo / "reports" / "lifecycle.md").write_text("\n".join(L) + "\n", encoding="utf-8")

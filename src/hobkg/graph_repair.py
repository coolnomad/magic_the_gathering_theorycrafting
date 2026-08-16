"""Phase 5 Part 2 follow-up: graph repair + reprojection.

The audit's `audit_repair_queue.jsonl` holds credible cross-card relations that lacked
a faithful primitive path. This module materializes the missing intermediate mechanism
as a small ADDITIVE repair layer (`data/graph_global/repair_{nodes,edges}.jsonl`) — the
frozen Phase 4 graph is untouched — then REPROJECTS those pairs mechanically over
graph+repair so each becomes a faithful typed path in
`data/graph_global/card_pair_projection_repaired.jsonl` (origin: graph_repair).

Most beneficiaries already carry a canonical trigger event (e.g. `event:player-loses-life
TRIGGERS master-lifeloss-mill`); the repair usually just adds the ENABLER→event edge. A
few need a new object-level edge (Company REQUIRES token:wolf; Thranduil's anthem
MODIFIES obj:subtype:elf). Every repair edge cites the audit grounding as provenance.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from . import project
from .pipeline import REPO, _load_dicts

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_FACE = re.compile(r"face:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}:\d+")
# beneficiary trigger-event keyword per missing-node hint
_EVENT_KEYWORD = {"life": "life", "counter": "counter", "activate": "activate", "enters": "enter"}
_NUMWORD = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


def _uuid(cid: str) -> str:
    m = _UUID.search(cid)
    return m.group(0) if m else cid


def _overlap(a, b) -> int:
    return max(0, min(a[1], b[1]) - max(a[0], b[0]))


def _repair_id(source: str, predicate: str, target: str) -> str:
    return "r" + hashlib.sha1(f"{source}|{predicate}|{target}".encode("utf-8")).hexdigest()[:15]


class _G:
    def __init__(self, repo: Path):
        self.nodes = {n["id"]: n for n in _load_dicts(repo / "data/graph_global/nodes.jsonl")}
        self.edges = list(_load_dicts(repo / "data/graph_global/edges.jsonl"))

    def op_by_grounding(self, card_uuid: str, grounding: list):
        """The op node whose FACE equals the grounding's face AND whose outgoing-edge
        provenance overlaps the grounding span. Matching the complete face_id (not just
        the card UUID) is essential on multiface cards, where the same char offsets exist
        on both faces. Returns (op_id, face_id) or (None, None)."""
        by_face = defaultdict(list)
        for g in grounding:
            fid = g.get("face_id")
            if fid and card_uuid in fid and g.get("oracle_span"):
                by_face[fid].append(g["oracle_span"])
        for e in self.edges:
            if not e["source"].startswith("op:"):
                continue
            m = _FACE.search(e["source"])
            if not m or m.group(0) not in by_face:        # op must be on the SAME face
                continue
            for p in e.get("provenance", []):
                sp = p.get("oracle_span")
                if sp and any(_overlap(sp, gs) > 0 for gs in by_face[m.group(0)]):
                    return e["source"], m.group(0)
        return None, None

    def op_producing(self, card_uuid: str, predicate: str, target_prefix: str) -> str | None:
        for e in self.edges:
            if (card_uuid in e["source"] and e["source"].startswith("op:")
                    and e["predicate"] == predicate and e["target"].startswith(target_prefix)):
                return e["source"]
        return None

    def trigger_event(self, benef_uuid: str, keyword: str):
        for e in self.edges:
            if e["predicate"] == "TRIGGERS" and benef_uuid in e["target"] and keyword in e["source"]:
                return e["source"]
        return None


def repair(repo: Path = REPO) -> dict:
    g = _G(repo)
    queue = list(_load_dicts(repo / "data/graph_global/audit_repair_queue.jsonl"))
    new_edges, new_nodes, done, skipped = [], {}, [], []

    def add_edge(source, predicate, target, entry, note, **props):
        prov = {"source": "graph_repair", "derivation": "audit_repair_queue",
                "relation": entry["relation"], "candidate_concept": entry["candidate_concept"],
                "note": note, "grounding": entry.get("grounding", [])}
        new_edges.append({"edge_id": _repair_id(source, predicate, target), "source": source,
                          "predicate": predicate, "target": target, "provenance": [prov],
                          "origin": "graph_repair", **props})

    def _face_matches(op_face, card_uuid, grounding):
        return op_face is not None and any(g.get("face_id") == op_face
                                           for g in grounding if card_uuid in (g.get("face_id") or ""))

    for e in queue:
        en, be = e["proposed_direction"]["enabler"], e["proposed_direction"]["beneficiary"]
        en_u, be_u = _uuid(en), _uuid(be)
        rel, concept = e["relation"], e["candidate_concept"]
        gnd = e.get("grounding", [])

        if rel == "ENABLES_TRIGGER":
            kw = next((v for k, v in _EVENT_KEYWORD.items() if k in e["missing_node_hint"]), None)
            event = g.trigger_event(be_u, kw) if kw else None
            en_op, op_face = g.op_by_grounding(en_u, gnd)
            # INVARIANT: the repaired operation must be on the SAME face as the enabler grounding.
            if event and en_op and _face_matches(op_face, en_u, gnd):
                add_edge(en_op, "CAUSES", event, e,
                         f"enabler operation on {op_face} produces the {event} that already triggers the beneficiary")
                done.append((en, be, rel, event))
            else:
                skipped.append({**e, "reason": f"event={event} en_op={en_op} face={op_face}"})

        elif rel == "SUPPLIES_RESOURCE" and concept.startswith("token:"):
            # producer already CREATES_OBJECT the token; add the beneficiary's REQUIRES edge,
            # PRESERVING the multiplicity threshold ("two or more Wolves" -> quantity 2).
            be_op, be_face = g.op_by_grounding(be_u, gnd)
            if not be_op or not _face_matches(be_face, be_u, gnd):
                skipped.append({**e, "reason": f"no face-matched beneficiary op ({be_op}/{be_face})"})
                continue
            btxt = " ".join((x.get("text") or "") for x in gnd if be_u in (x.get("face_id") or "")).lower()
            m = re.search(r"(one|two|three|four|five|\d+)\s+or more", btxt)
            qty = (_NUMWORD.get(m.group(1)) or int(m.group(1))) if m else None
            props = {"quantity": qty} if qty else {}
            add_edge(be_op, "REQUIRES", concept, e,
                     "beneficiary requires the object the enabler creates" + (f" (>= {qty})" if qty else ""),
                     **props)
            done.append((en, be, rel, concept))

        elif rel == "AMPLIFIES_EFFECT" and e["missing_node_type"] == "ObjectModifier":
            sub = "obj:subtype:" + concept.split(":")[-1]
            en_face = next((gg["face_id"] for gg in gnd if en_u in (gg.get("face_id") or "")), None)
            if not en_face:
                skipped.append({**e, "reason": "no enabler grounding face"})
                continue
            en_op, op_face = g.op_by_grounding(en_u, gnd)
            if not en_op or not _face_matches(op_face, en_u, gnd):
                # the static anthem is not modelled as an operation at all (that IS the gap) —
                # materialize the anthem operation on the enabler's OWN face and link it.
                en_op = f"op:{en_face}:anthem"
                new_nodes[en_op] = {"id": en_op, "type": "Operation", "label": "static anthem",
                                    "data": {"kind": "static_modifier"}, "provenance": [{"source": "graph_repair"}]}
                add_edge(en_face, "HAS_ABILITY", en_op, e, "materialize the static anthem operation on its face")
                op_face = en_face
            if sub not in g.nodes:
                new_nodes[sub] = {"id": sub, "type": "ObjectClass", "label": concept.split(":")[-1],
                                  "data": {"type_kind": "subtype"}, "provenance": [{"source": "graph_repair"}]}
            # carry the modification (e.g. "get +1/+1") so the higher-order effect is preserved
            etxt = " ".join((x.get("text") or "") for x in gnd if en_u in (x.get("face_id") or ""))
            pm = re.search(r"\+(\d+)/\+(\d+)", etxt)
            props = {"modification": {"power": f"+{pm.group(1)}", "toughness": f"+{pm.group(2)}"}} if pm else {}
            add_edge(en_op, "MODIFIES", sub, e,
                     f"enabler static ability on {op_face} modifies subtype '{sub.split(':')[-1]}' objects the beneficiary creates",
                     **props)
            done.append((en, be, rel, sub))
        else:
            skipped.append({**e, "reason": "no repair handler"})

    outdir = repo / "data" / "graph_global"
    # dedup edges by edge_id
    uniq = {}
    for e in new_edges:
        uniq.setdefault(e["edge_id"], e)
    new_edges = sorted(uniq.values(), key=lambda e: (e["source"], e["predicate"], e["target"]))
    with (outdir / "repair_edges.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for e in new_edges:
            fh.write(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n")
    with (outdir / "repair_nodes.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for n in sorted(new_nodes.values(), key=lambda n: n["id"]):
            fh.write(json.dumps(n, ensure_ascii=False, sort_keys=True) + "\n")
    return {"queue": len(queue), "repaired": len(done), "skipped": len(skipped),
            "repair_edges": len(new_edges), "repair_nodes": len(new_nodes),
            "_skipped": skipped}


# --------------------------------------------------------------------------- #
#  Reprojection: build the now-faithful typed path over graph + repair layer   #
# --------------------------------------------------------------------------- #
def reproject(repo: Path = REPO) -> dict:
    edges = list(_load_dicts(repo / "data/graph_global/edges.jsonl"))
    repair_edges = list(_load_dicts(repo / "data/graph_global/repair_edges.jsonl"))
    all_edges = edges + repair_edges
    repair_ids = {e["edge_id"] for e in repair_edges}
    real_ids = {e["edge_id"] for e in edges}
    names = {c["id"]: c["name"] for c in _load_dicts(repo / "data/normalized/cards.jsonl")}
    queue = list(_load_dicts(repo / "data/graph_global/audit_repair_queue.jsonl"))

    metaedges, unrepaired = [], []
    for q in queue:
        en, be = q["proposed_direction"]["enabler"], q["proposed_direction"]["beneficiary"]
        en_u, be_u = _uuid(en), _uuid(be)
        rel, concept = q["relation"], q["candidate_concept"]
        steps = None
        if rel == "ENABLES_TRIGGER":
            cause = next((e for e in repair_edges if en_u in e["source"] and e["predicate"] == "CAUSES"
                          and e["target"].startswith("event:")), None)
            trig = None
            if cause:
                trig = next((e for e in all_edges if e["predicate"] == "TRIGGERS"
                             and e["source"] == cause["target"] and be_u in e["target"]), None)
            if cause and trig:
                steps = [project._step(cause, "forward"), project._step(trig, "forward")]
        elif rel == "SUPPLIES_RESOURCE" and concept.startswith("token:"):
            create = next((e for e in all_edges if en_u in e["source"]
                           and e["predicate"] == "CREATES_OBJECT" and e["target"] == concept), None)
            require = next((e for e in repair_edges if be_u in e["source"]
                            and e["predicate"] == "REQUIRES" and e["target"] == concept), None)
            if create and require:
                steps = [project._step(create, "forward"), project._step(require, "reverse")]
        elif rel == "AMPLIFIES_EFFECT":
            sub = "obj:subtype:" + concept.split(":")[-1]
            modifies = next((e for e in repair_edges if en_u in e["source"]
                             and e["predicate"] == "MODIFIES" and e["target"] == sub), None)
            hastype = next((e for e in all_edges if e["predicate"] == "HAS_TYPE"
                            and e["source"] == concept and e["target"] == sub), None)
            create = next((e for e in all_edges if be_u in e["source"]
                           and e["predicate"] == "CREATES_OBJECT" and e["target"] == concept), None)
            if modifies and hastype and create:
                steps = [project._step(modifies, "forward"), project._step(hastype, "reverse"),
                         project._step(create, "reverse")]
        if not steps:
            unrepaired.append(q)
            continue
        nodes_seq = [steps[0]["source"]] + [s["target"] for s in steps]
        metaedges.append({
            "source_card": en, "target_card": be, "relation": rel, "origin": "graph_repair",
            "path_kind": "grounded", "steps": steps, "primitive_path": nodes_seq,
            "path_predicates": [s["predicate"] for s in steps],
            "edge_ids": [s["edge_id"] for s in steps],
            "uses_repair_edges": [s["edge_id"] for s in steps if s["edge_id"] in repair_ids],
            "connecting_node": nodes_seq[1],                   # the ACTUAL intermediate used
            "candidate_concept": q["candidate_concept"],       # the LLM's (possibly misleading) concept
            "grounding": q.get("grounding", []), "confidence": q.get("confidence")})

    metaedges.sort(key=lambda m: (m["source_card"], m["target_card"], m["relation"]))
    with (repo / "data/graph_global/card_pair_projection_repaired.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for m in metaedges:
            fh.write(json.dumps(m, ensure_ascii=False, sort_keys=True) + "\n")
    # integrity: every step edge_id resolves to a real Phase 4 edge or a repair edge
    ok = all(s["edge_id"] in real_ids or s["edge_id"] in repair_ids
             for m in metaedges for s in m["steps"])
    _report(repo, metaedges, names, {"reprojected": len(metaedges), "unrepaired": len(unrepaired),
                                     "edges_resolve": ok})
    return {"reprojected": len(metaedges), "unrepaired": len(unrepaired), "edges_resolve": ok}


def _report(repo: Path, metaedges: list, names: dict, stats: dict) -> None:
    L = ["# HOB Phase 5 — Graph Repair + Reprojection", "",
         f"- **reprojected as faithful typed paths**: {stats['reprojected']}",
         f"- **still unrepaired**: {stats['unrepaired']}",
         f"- **all path edges resolve (real Phase 4 or repair layer)**: {stats['edges_resolve']}", "",
         "## Reprojected relations (origin: graph_repair)", ""]
    for m in metaedges:
        L.append(f"- **{names.get(m['source_card'], m['source_card'])} → "
                 f"{names.get(m['target_card'], m['target_card'])}** [{m['relation']}] "
                 f"via `{m['connecting_node']}` — {' → '.join(m['path_predicates'])} "
                 f"(repair edges: {len(m['uses_repair_edges'])})")
    (repo / "reports" / "graph_repair.md").write_text("\n".join(L) + "\n", encoding="utf-8")


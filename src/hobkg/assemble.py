"""Phase 4: global graph assembly.

Merge the Phase 2 template graph (canonical, typed) + the Phase 1 normalized
entities + the Phase 3 accepted per-face extractions into ONE global typed
multigraph, then validate every edge against full predicate domain/range
signatures with no `Unknown` endpoint types.

Transformations applied to the Phase 3 card-local layer:
  - namespace ability ids: local `a1` -> `ability:{face}:a1`;
  - reify actor-subject edges onto explicit Operation nodes (the reviewer's gate:
    a CardFace/Ability may not be the subject of an actor predicate);
  - collapse template/LLM duplicates (drop `face -INSTANTIATES-> rule:amass` etc.;
    the canonical `op:{face}:amass -INSTANTIATES-> op:amass` from Phase 2 stands);
  - dedup edges by (source, predicate, target), merging provenance.

Schema decisions (reuse of existing predicates, no new predicate TYPES):
  - actor predicates admit an Operation subject;
  - CAUSES range includes Operation, so `Ability CAUSES op:{ability}` (the reified
    ability->operation link) is valid.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from .phase3 import resolve_node_type
from .pipeline import REPO, _load_dicts

# --- full predicate domain/range signatures (global) ------------------------
# Actor predicates are Operation-subject after reification. Relational predicates
# keep the strict Phase-3 forms.
_ACTOR_SUBJ = {"Operation"}
GLOBAL_SIGNATURES = {
    # structural
    "HAS_FACE": ({"Card"}, {"CardFace"}),
    "HAS_ABILITY": ({"CardFace", "ObjectClass"}, {"Ability", "Operation"}),
    "HAS_TYPE": ({"CardFace", "ObjectClass", "TokenSpec"}, {"ObjectClass"}),
    "HAS_KEYWORD": ({"CardFace", "Ability", "Operation"}, {"Rule", "Operation", "ObjectClass", "Ability"}),
    "HAS_COST": ({"CardFace", "Ability", "Operation"}, {"Cost"}),
    "HAS_COUNTER_TYPE": ({"State"}, {"CounterType"}),
    "HAS_STATE": ({"ObjectClass", "CardFace", "TokenSpec"}, {"State"}),
    "REFERENCES_RULE": ({"CardFace", "Card", "Ability", "Operation", "Effect", "Gate", "ObjectClass"},
                        {"Rule", "Gate", "Ability", "ObjectClass"}),
    # relational (direction load-bearing)
    "TRIGGERS": ({"Event"}, {"Ability"}),
    "ENABLES": ({"State", "Resource", "Event", "Gate"}, {"Ability", "Operation"}),
    "PERSISTS_AS": ({"State"}, {"State"}),
    "COUNTS": ({"Gate"}, {"ObjectClass"}),
    "CONTRIBUTES_TO": ({"CardFace", "ObjectClass", "TokenSpec"}, {"Gate"}),
    "QUALIFIES_FOR": ({"CardFace", "ObjectClass", "TokenSpec"}, {"Gate"}),
    "SATISFIES": ({"Resource", "State", "Event"}, {"Cost", "Gate"}),
    "ATTACHED_TO": ({"ObjectClass", "CardFace", "TokenSpec"}, {"ObjectClass", "CardFace", "TokenSpec"}),
    "INSTANTIATES": ({"Operation"}, {"Operation"}),
    # actor (Operation subject after reification); target ranges admit the card-def
    # patterns the LLM+templates use (an op causes a gate; modifies another ability or
    # a cost; requires/scales-with a token or object count).
    # CAUSES is used at the card-def layer as a coarse "this operation brings about an
    # effect on X" — target admits Effect/Operation/Event plus the affected
    # object/resource/state (to be refined into explicit Effect nodes in a later pass).
    "CAUSES": ({"Event", "Operation", "Ability", "Gate", "Effect"},
               {"Event", "Effect", "Operation", "Gate", "State", "Resource", "ObjectClass",
                "CardFace", "TokenSpec"}),
    "CAN_LEAD_TO": ({"Operation", "Event"}, {"Operation", "Event", "Ability", "CardFace", "TokenSpec"}),
    "PRODUCES": (_ACTOR_SUBJ | {"Gate"}, {"Resource", "Event", "ObjectClass", "State", "TokenSpec"}),
    "CONSUMES": (_ACTOR_SUBJ, {"Resource", "ObjectClass", "CardFace", "TokenSpec", "Cost", "CounterType"}),
    "MOVES_FROM": (_ACTOR_SUBJ, {"Zone"}),
    "MOVES_TO": (_ACTOR_SUBJ, {"Zone"}),
    "CREATES_OBJECT": (_ACTOR_SUBJ | {"Gate"}, {"ObjectClass", "TokenSpec"}),
    "ADDS_COUNTER": (_ACTOR_SUBJ, {"CounterType", "CardFace", "ObjectClass"}),
    "REMOVES_COUNTER": (_ACTOR_SUBJ, {"CounterType", "CardFace", "ObjectClass"}),
    "MODIFIES": (_ACTOR_SUBJ | {"Effect", "State"},
                 {"Operation", "State", "ObjectClass", "CardFace", "CounterType", "Ability", "Cost", "Event", "Resource"}),
    "PREVENTS": (_ACTOR_SUBJ | {"Effect", "State"}, {"Event", "Operation", "ObjectClass", "CardFace"}),
    "REPLACES": (_ACTOR_SUBJ | {"Ability", "Effect"}, {"Event", "Effect", "Operation", "Zone", "ObjectClass"}),
    "SCALES_WITH": (_ACTOR_SUBJ | {"Ability", "Effect"},
                    {"Resource", "State", "CounterType", "ObjectClass", "TokenSpec", "Event",
                     "Operation", "Cost", "Zone", "CardFace", "Ability"}),
    "REQUIRES": (_ACTOR_SUBJ | {"Ability", "Gate", "Effect"},
                 {"Resource", "State", "ObjectClass", "Gate", "CounterType", "TokenSpec", "Event", "Zone"}),
    "DERIVED_FROM": (None, None),  # not signature-checked
}

# actor predicates whose CardFace/Ability subject must be reified onto an Operation.
# NOTE: the structural predicates HAS_KEYWORD/HAS_COST/REFERENCES_RULE are NOT here —
# they describe the face/ability itself and keep a CardFace/Ability subject.
_ACTOR_PREDICATES = {
    "PRODUCES", "CONSUMES", "MOVES_FROM", "MOVES_TO", "CREATES_OBJECT", "ADDS_COUNTER",
    "REMOVES_COUNTER", "MODIFIES", "PREVENTS", "REPLACES", "SCALES_WITH", "REQUIRES",
    "CAUSES", "CAN_LEAD_TO",
}
# rule ids whose card-local `* INSTANTIATES rule:X` edge is superseded by the Phase 2
# canonical `op:{face}:X INSTANTIATES op:X` and should be dropped on assembly.
_TEMPLATED_RULES = {"rule:amass", "rule:typecycling"}


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "x"


def _canon(g: "Graph", nid: str) -> str:
    """Canonicalize a free-text endpoint (no recognized id prefix) into a typed
    ObjectClass node `obj:{slug}`, preserving the original text as the label."""
    if resolve_node_type(nid, set()) != "Unknown":
        return nid
    cid = "obj:" + _slug(nid)
    g.add_node(cid, "ObjectClass", nid)
    return cid


class Graph:
    def __init__(self):
        self.nodes: dict[str, dict] = {}
        self.edges: dict[tuple, dict] = {}

    def add_node(self, nid, ntype, label="", data=None, provenance=None):
        n = self.nodes.get(nid)
        if n is None:
            self.nodes[nid] = {"id": nid, "type": ntype, "label": label or nid,
                               "data": data or {}, "provenance": list(provenance or [])}
        elif provenance:
            n["provenance"].extend(provenance)
        return nid

    def add_edge(self, source, predicate, target, provenance=None, **props):
        key = (source, predicate, target)
        e = self.edges.get(key)
        if e is None:
            self.edges[key] = {"source": source, "predicate": predicate, "target": target,
                               "provenance": list(provenance or []), **props}
        elif provenance:
            e["provenance"].extend(provenance)
        return key


def assemble(repo: Path = REPO) -> dict:
    g = Graph()

    # 1. seed with the Phase 2 template graph (canonical + typed)
    for n in _load_dicts(repo / "data" / "graph" / "nodes.jsonl"):
        g.add_node(n["id"], n["type"], n.get("label", ""), n.get("data"), n.get("provenance"))
    for e in _load_dicts(repo / "data" / "graph" / "edges.jsonl"):
        g.add_edge(e["source"], e["predicate"], e["target"], e.get("provenance"),
                   **{k: e[k] for k in ("timing", "quantity", "optional", "condition_ids") if e.get(k)})

    # 2. Phase 1 entities
    cards = {c["id"]: c for c in _load_dicts(repo / "data" / "normalized" / "cards.jsonl")}
    faces = {f["id"]: f for f in _load_dicts(repo / "data" / "normalized" / "faces.jsonl")}
    for c in cards.values():
        g.add_node(c["id"], "Card", c["name"])
    for f in faces.values():
        g.add_node(f["id"], "CardFace", f["name"])
        g.add_edge(f["card_id"], "HAS_FACE", f["id"])
    for t in _load_dicts(repo / "data" / "normalized" / "tokens.jsonl"):
        g.add_node(t["id"], "TokenSpec", t["name"])

    # 3. merge the Phase 3 accepted layer, per face
    reified = 0
    for a in _load_dicts(repo / "data" / "review" / "llm_accepted.jsonl"):
        face_id = a["face_id"]
        g.add_node(face_id, "CardFace", faces.get(face_id, {}).get("name", face_id))
        local_to_global = {}
        for ab in a.get("abilities", []):
            gid = f"ability:{face_id}:{ab['ability_id']}"
            local_to_global[ab["ability_id"]] = gid
            g.add_node(gid, "Ability", ab.get("ability_id", ""),
                       {"kind": ab.get("kind"), "oracle_spans": ab.get("oracle_spans")})
            g.add_edge(face_id, "HAS_ABILITY", gid)

        eff_seq = 0
        for e in a.get("proposed_edges", []):
            src = local_to_global.get(e["source"], e["source"])
            tgt = local_to_global.get(e["target"], e["target"])
            pred = e["predicate"]
            prov = [e.get("provenance", {})]

            # collapse templated-rule instantiations (Phase 2 op-level edge stands)
            if pred == "INSTANTIATES" and tgt in _TEMPLATED_RULES:
                continue

            # canonicalize free-text endpoints into typed ObjectClass nodes
            src = _canon(g, src)
            tgt = _canon(g, tgt)
            s_type = resolve_node_type(src, set())
            # reify actor edges whose subject is a CardFace or Ability
            if pred in _ACTOR_PREDICATES and s_type in ("CardFace", "Ability"):
                if s_type == "Ability":
                    op = "op:" + src.split("ability:", 1)[1] if src.startswith("ability:") else f"op:{src}"
                    g.add_node(op, "Operation", "effect of " + src)
                    g.add_edge(src, "CAUSES", op)          # ability -> its operation
                else:  # CardFace-level action
                    eff_seq += 1
                    op = f"op:{face_id}:eff{eff_seq}"
                    g.add_node(op, "Operation", "card-level effect")
                    g.add_edge(face_id, "HAS_ABILITY", op)
                src = op
            g.add_edge(src, pred, tgt, prov,
                       **{k: e[k] for k in ("timing", "quantity", "optional", "condition_ids") if e.get(k)})
            if src.startswith("op:") and pred in _ACTOR_PREDICATES:
                reified += 0  # counted below
    # materialize every referenced endpoint as a typed node (Phase 3 invents concept
    # nodes — event:/state:/obj:/kw:/cost:/resource: — by id; type them by convention).
    for (s, _p, t) in list(g.edges):
        for nid in (s, t):
            if nid not in g.nodes:
                g.add_node(nid, resolve_node_type(nid, set()), nid)

    return _finalize(g, repo)


def validate_global(g: Graph) -> dict:
    node_ids = set(g.nodes)
    dangling, sig_viol, unknown = [], [], []
    for e in g.edges.values():
        if e["source"] not in node_ids or e["target"] not in node_ids:
            dangling.append((e["source"], e["predicate"], e["target"]))
            continue
        s = g.nodes[e["source"]]["type"]
        t = g.nodes[e["target"]]["type"]
        if s == "Unknown" or t == "Unknown":
            unknown.append((e["source"], e["predicate"], e["target"]))
        sig = GLOBAL_SIGNATURES.get(e["predicate"])
        if sig and sig[0] is not None and (s not in sig[0] or t not in sig[1]):
            sig_viol.append(f"{e['source']}({s}) -{e['predicate']}-> {e['target']}({t})")
    return {"dangling": dangling, "signature_violations": sig_viol, "unknown_endpoint_types": unknown}


def _finalize(g: Graph, repo: Path) -> dict:
    v = validate_global(g)
    out = repo / "data" / "graph_global"
    out.mkdir(parents=True, exist_ok=True)
    with (out / "nodes.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for n in g.nodes.values():
            fh.write(json.dumps(n, ensure_ascii=False) + "\n")
    with (out / "edges.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for e in g.edges.values():
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    # honest residual: edges that assembled + typed but whose predicate domain/range is
    # still questionable (Phase-3 mis-typings surfaced by assembly) — flagged, not hidden.
    with (out / "assembly_review.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for s in v["signature_violations"]:
            fh.write(json.dumps({"issue": "predicate_signature", "edge": s}) + "\n")

    ntypes = Counter(n["type"] for n in g.nodes.values())
    preds = Counter(e["predicate"] for e in g.edges.values())
    unresolved_type_nodes = [nid for nid, n in g.nodes.items() if n["type"] == "Unknown"]
    stats = {
        "nodes": len(g.nodes), "edges": len(g.edges),
        "node_types": dict(ntypes), "edge_predicates": dict(preds),
        "dangling_edges": len(v["dangling"]),
        "signature_violations": len(v["signature_violations"]),
        "unknown_endpoint_edges": len(v["unknown_endpoint_types"]),
        "unknown_type_nodes": len(unresolved_type_nodes),
        "face_to_rule_amass_edges": sum(1 for e in g.edges.values()
                                        if e["predicate"] == "INSTANTIATES" and e["target"] == "rule:amass"),
    }
    _report(repo, stats, v)
    stats["_violations"] = v
    return stats


def _report(repo: Path, stats: dict, v: dict) -> None:
    L = ["# HOB Phase 4 — Global Assembly", "",
         f"- **nodes**: {stats['nodes']}", f"- **edges**: {stats['edges']}",
         f"- **dangling edges**: {stats['dangling_edges']}",
         f"- **signature violations**: {stats['signature_violations']}",
         f"- **edges with Unknown endpoint type**: {stats['unknown_endpoint_edges']}",
         f"- **nodes with Unknown type**: {stats['unknown_type_nodes']}",
         f"- **face-to-rule amass edges (must be 0)**: {stats['face_to_rule_amass_edges']}", "",
         "## Node types", ""]
    for k, val in sorted(stats["node_types"].items(), key=lambda x: -x[1]):
        L.append(f"- {k}: {val}")
    L += ["", "## Edge predicates", ""]
    for k, val in sorted(stats["edge_predicates"].items(), key=lambda x: -x[1]):
        L.append(f"- {k}: {val}")
    if v["signature_violations"]:
        L += ["", "## Signature violations (sample)", ""] + [f"- {s}" for s in v["signature_violations"][:40]]
    if v["unknown_endpoint_types"]:
        L += ["", "## Unknown-endpoint edges (sample)", ""] + [f"- {a} -{b}-> {c}" for a, b, c in v["unknown_endpoint_types"][:40]]
    (repo / "reports" / "assembly.md").write_text("\n".join(L) + "\n", encoding="utf-8")

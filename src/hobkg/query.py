"""Query interface (spec §CLI + completion criterion): let a human inspect any card, any
ordered pair, or any higher-order mechanism, and see — for pairs — the relation type,
direction, conditions, intermediate nodes, exact provenance, and whether the relation is
mechanically derived, LLM-inferred, graph-repaired, or mechanism-repaired.

CLI:  query-card "<name>"  ·  query-pair "<A>" "<B>"  ·  query-mechanism "<label|id>"
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .pipeline import REPO, _load_dicts

# (layer key, projection file, human inference-origin label)
_LAYERS = [
    ("mechanical", "card_pair_projection.jsonl", "mechanically derived (primitive path)"),
    ("llm_audit", "card_pair_projection_audit.jsonl", "LLM-inferred (audit, critic-confirmed)"),
    ("graph_repair", "card_pair_projection_repaired.jsonl", "graph-repair (materialized intermediate)"),
    ("mechanism_repair", "card_pair_projection_mechanism.jsonl", "mechanism-repair (stateful / targeted)"),
]


def _opt(path):
    return list(_load_dicts(path)) if path.exists() else []


class _DB:
    def __init__(self, repo: Path):
        self.G = repo / "data" / "graph_global"
        self.cards = list(_load_dicts(repo / "data/normalized/cards.jsonl"))
        self.name_by_id = {c["id"]: c["name"] for c in self.cards}
        self.faces = list(_load_dicts(repo / "data/normalized/faces.jsonl"))
        self.faces_by_card = defaultdict(list)
        for f in self.faces:
            self.faces_by_card[f["card_id"]].append(f)
        # metaedges grouped by ordered pair, each tagged with layer + inference origin
        self.by_pair = defaultdict(list)
        for key, fname, origin in _LAYERS:
            for m in _opt(self.G / fname):
                m = {**m, "_layer": key, "_origin_label": origin}
                self.by_pair[(m["source_card"], m["target_card"])].append(m)

    def resolve(self, text: str):
        """A card id from a name: exact (case-insensitive) else unique substring match."""
        t = text.strip().lower()
        exact = [c["id"] for c in self.cards if c["name"].lower() == t]
        if exact:
            return exact[0], None
        subs = [c["id"] for c in self.cards if t in c["name"].lower()]
        if len(subs) == 1:
            return subs[0], None
        if not subs:
            return None, f"no card matches '{text}'"
        return None, "ambiguous '{}': {}".format(text, ", ".join(sorted(self.name_by_id[i] for i in subs))[:400])


def _paths(m: dict):
    """Unified (primitive_path, path_predicates, conditions, provenance) view over both metaedge
    schemas: the mechanical layer carries `alternative_paths`; the derived layers are flat."""
    if "alternative_paths" in m:
        for a in m["alternative_paths"]:
            yield (a.get("primitive_path") or [], a.get("path_predicates") or [],
                   a.get("conditions") or a.get("condition_ids") or [], a.get("provenance") or [])
    else:
        yield (m.get("primitive_path") or [], m.get("path_predicates") or [],
               m.get("condition_ids") or m.get("conditions") or [], m.get("grounding") or m.get("provenance") or [])


def _render_path(nodes, preds):
    if not nodes:
        return "    (no expandable primitive path)"
    parts = [nodes[0]]
    for i, p in enumerate(preds):
        nxt = nodes[i + 1] if i + 1 < len(nodes) else "?"
        parts.append(f"  --{p}-->  {nxt}")
    return "    " + "".join(parts)


def _prov_summary(prov):
    out = []
    for p in prov[:4]:
        if not isinstance(p, dict):
            continue
        bits = [p.get("source"), p.get("rule_ref") or p.get("rule"), p.get("derivation"),
                (p.get("text") or "")[:60] or None]
        out.append(" / ".join(b for b in bits if b))
    return out


def query_pair(a: str, b: str, repo: Path = REPO) -> str:
    db = _DB(repo)
    ca, ea = db.resolve(a)
    cb, eb = db.resolve(b)
    if ea or eb:
        return "\n".join(x for x in (ea, eb) if x)
    L = [f"# Pair: {db.name_by_id[ca]}  <->  {db.name_by_id[cb]}", ""]
    for src, tgt in ((ca, cb), (cb, ca)):
        rels = db.by_pair.get((src, tgt), [])
        L.append(f"## {db.name_by_id[src]}  ->  {db.name_by_id[tgt]}  — {len(rels)} relation(s)")
        if not rels:
            L.append("  (no mechanistic relation in any projection layer — most ordered pairs are empty)")
        for m in sorted(rels, key=lambda x: (x["_layer"], x["relation"])):
            L.append(f"  - {m['relation']}  [{m['_origin_label']}]")
            for nodes, preds, conds, prov in _paths(m):
                if conds:
                    L.append(f"    conditions: {', '.join(conds)}")
                L.append(_render_path(nodes, preds))
                for ps in _prov_summary(prov):
                    L.append(f"    provenance: {ps}")
                break  # show the first (shortest) path per relation; full set in the projection files
        L.append("")
    return "\n".join(L)


def query_card(name: str, repo: Path = REPO) -> str:
    db = _DB(repo)
    c, err = db.resolve(name)
    if err:
        return err
    L = [f"# Card: {db.name_by_id[c]}   ({c})", ""]
    for f in db.faces_by_card[c]:
        tl = (f.get("type_line") or {}).get("raw") or ""
        L.append(f"- face `{f['id']}` [{f.get('role')}] — {f.get('name')} — {tl}")
    L.append("")
    out_rel = defaultdict(list)   # (relation, layer) -> [target names]
    in_rel = defaultdict(list)
    for (s, t), ms in db.by_pair.items():
        if s == c:
            for m in ms:
                out_rel[(m["relation"], m["_layer"])].append(db.name_by_id.get(t, t))
        if t == c:
            for m in ms:
                in_rel[(m["relation"], m["_layer"])].append(db.name_by_id.get(s, s))
    for title, rel in (("Outgoing relations (this card -> others)", out_rel),
                       ("Incoming relations (others -> this card)", in_rel)):
        L.append(f"## {title}")
        if not rel:
            L.append("  (none)")
        for (r, layer), names in sorted(rel.items()):
            uniq = sorted(set(names))
            L.append(f"  - {r} [{layer}] × {len(uniq)}: " + ", ".join(uniq[:12])
                     + (" ..." if len(uniq) > 12 else ""))
        L.append("")
    L.append("Use `query-pair` for the full path, conditions, and provenance of any specific pair.")
    return "\n".join(L)


def query_mechanism(label: str, repo: Path = REPO) -> str:
    mods = list(_load_dicts(repo / "data/graph_global/mechanism_modules.jsonl"))
    names = {c["id"]: c["name"] for c in _load_dicts(repo / "data/normalized/cards.jsonl")}
    t = label.strip().lower()
    hits = [m for m in mods if t == m["module_id"].lower() or t == m["label"].lower()]
    if not hits:
        hits = [m for m in mods if t in m["module_id"].lower() or t in m["label"].lower()]
    if not hits:
        alllabels = ", ".join(sorted(m["label"] for m in mods))
        return f"no mechanism module matches '{label}'.\nAvailable: {alllabels}"
    L = []
    for m in hits:
        s = m["stats"]
        L.append(f"# Mechanism module: {m['label']}  (`{m['module_id']}`, kind {m['kind']})")
        L.append(f"- anchors: {', '.join(m['anchors'])}")
        L.append(f"- members ({s['members']}): "
                 + ", ".join(sorted(names.get(x, x) for x in m['members'])[:20])
                 + (" ..." if s['members'] > 20 else ""))
        L.append(f"- contributors: {s['contributors']}  · consumers: {s['consumers']}  · "
                 f"conditions: {s['conditions']}  · feedback cycles: {s['feedback_cycles']}")
        if m["conditions"]:
            L.append(f"- conditions: {', '.join(m['conditions'])}")
        if m["feedback_cycles"]:
            L.append(f"- feedback cycle: {' -> '.join(m['feedback_cycles'][0])}")
        L.append(f"- subgraph edges: {len(m['subgraph_edge_ids'])} (expandable to primitive edges)")
        L.append("")
    return "\n".join(L)

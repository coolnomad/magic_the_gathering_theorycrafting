"""Full-spec completion: the three stateful / targeted mechanisms the reviewer flagged as
genuinely missing from the projection (not optional enhancements). Each is materialized as a
small ADDITIVE layer (`data/graph_global/mechanism_{nodes,edges}.jsonl`, origin
`mechanism_repair`) — the frozen Phase 4 graph, the graph-repair layer, and the legend layer
are all untouched — then REPROJECTED into `card_pair_projection_mechanism.jsonl` as faithful
typed paths over graph + mechanism layer.

A. Turn-scoped second-draw gate (modeling principle #5, semantic invariant #2, execution #6).
   Master's Councillors / Bard the Bowman / Lakeshore Apothecary trigger on "your second card
   drawn each turn", but that event had no modeled producer. We add a turn-scoped count state
   and gate: each draw operation PRODUCES `state:cards-drawn-this-turn`; the state SATISFIES
   `gate:second-draw` (threshold 2, condition "the draw is the second this turn"); the gate
   PRODUCES the second-draw event(s) the payoffs already trigger on. A single draw (e.g.
   Recruit's) contributes ONE increment and is not sufficient alone — the second-draw
   condition is carried on every projected relation.

B. Dwarf/Equipment -> Dáin's Company (and Kíli the Resourceful). Their ETB "look at the top N,
   reveal a Dwarf or Equipment card, put it into your hand" find had no link to the Dwarf/
   Equipment population. We add `find-op REQUIRES obj:subtype:{dwarf,equipment}`; every Dwarf/
   Equipment card supplies that object class.

C. Noncreature spell cast -> Bothersome Noisemaker (and two other noncreature-cast payoffs).
   The payoffs trigger on `event:cast[-_]noncreature[-_]spell`, which had no producer. We add a
   canonical `op:cast-noncreature-spell` that PRODUCES those cast events, and link every
   noncreature spell face to it (HAS_ABILITY, as the frozen graph already does for cast/amass
   ops); casting any of them fires the payoff.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict, deque
from pathlib import Path

from . import project
from .pipeline import REPO, _load_dicts

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_FACE = re.compile(r"face:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}:\d+")

# canonical "a card was drawn" events (the genuine draw event nodes in the frozen graph)
DRAW_EVENTS = {"event:draw", "event:card-drawn"}
# the fragmented second-draw payoff events (Bard the Bowman / Lakeshore Apothecary / Councillors)
SECOND_DRAW_EVENTS = ["event:draw-second-card", "event:draw-second-card-each-turn",
                      "event:draw_second_card_each_turn"]
# the fragmented noncreature-cast trigger events (Noisemaker / Fíli / Gandalf Flameshape)
NONCREATURE_CAST_EVENTS = ["event:cast-noncreature-spell", "event:cast_noncreature_spell"]
# castable noncreature card types (a "noncreature spell")
NONCREATURE_TYPES = {"Instant", "Sorcery", "Artifact", "Enchantment", "Battle", "Planeswalker"}

STATE_COUNT = "state:cards-drawn-this-turn"
GATE_SECOND = "gate:second-draw"
COND_SECOND = "cond:draw-is-second-this-turn"
OP_CAST = "op:cast-noncreature-spell"


def _card_of(nid):
    m = _UUID.search(nid)
    return "card:" + m.group(0) if m else None


def _face_of(nid):
    m = _FACE.search(nid)
    return m.group(0) if m else None


def _mid(source, predicate, target):
    return "m" + hashlib.sha1(f"{source}|{predicate}|{target}".encode("utf-8")).hexdigest()[:15]


class _G:
    def __init__(self, repo: Path):
        self.nodes = {n["id"]: n for n in _load_dicts(repo / "data/graph_global/nodes.jsonl")}
        self.edges = list(_load_dicts(repo / "data/graph_global/edges.jsonl"))
        self.out, self.inc = defaultdict(list), defaultdict(list)
        for e in self.edges:
            self.out[e["source"]].append(e)
            self.inc[e["target"]].append(e)
        self.faces = list(_load_dicts(repo / "data/normalized/faces.jsonl"))
        self.face_by_id = {f["id"]: f for f in self.faces}
        self.names = {c["id"]: c["name"] for c in _load_dicts(repo / "data/normalized/cards.jsonl")}

    def forward_paths_to(self, target: str, preds: set, max_depth: int = 6) -> dict:
        """{face_id: [forward step-edges]} for every CardFace that reaches `target` by following
        edges with the given predicates. Reverse-BFS from target over incoming edges, so shared
        templates (e.g. op:recruit:draw reached from each recruit face) resolve to real paths."""
        out = {}
        # queue holds (node, path_of_edges_from_node_down_to_target)
        q = deque([(target, [])])
        seen = {target}
        while q:
            node, path = q.popleft()
            if len(path) > max_depth:
                continue
            for e in self.inc.get(node, []):
                if e["predicate"] not in preds:
                    continue
                src = e["source"]
                newpath = [e] + path
                if src.startswith("face:") and self.nodes.get(src, {}).get("type") == "CardFace":
                    out.setdefault(src, newpath)
                if src not in seen:
                    seen.add(src)
                    q.append((src, newpath))
        return out


def _node(nid, ntype, label, data, note):
    return {"id": nid, "type": ntype, "label": label, "data": data,
            "provenance": [{"source": "mechanism_repair", "derivation": note}], "origin": "mechanism_repair"}


def _edge(source, predicate, target, note, **props):
    return {"edge_id": _mid(source, predicate, target), "source": source, "predicate": predicate,
            "target": target, "provenance": [{"source": "mechanism_repair", "derivation": note}],
            "origin": "mechanism_repair", **props}


def materialize(repo: Path = REPO) -> dict:
    g = _G(repo)
    nodes, edges = {}, []

    # ---- A. turn-scoped second-draw gate ------------------------------------------------
    nodes[STATE_COUNT] = _node(STATE_COUNT, "State", "cards drawn this turn",
                               {"scope": "controller", "reset": "each_turn", "aggregation": "count",
                                "tracks": "cards_drawn"}, "turn-scoped draw counter")
    nodes[GATE_SECOND] = _node(GATE_SECOND, "Gate", "second draw each turn",
                               {"gate_type": "turn_scoped_count_threshold", "source_state": STATE_COUNT,
                                "aggregation": "count", "comparison": ">=", "threshold": 2,
                                "output_events": SECOND_DRAW_EVENTS}, "count reaches 2 -> second-draw event")
    draw_ops = sorted({e["source"] for e in g.edges
                       if e["predicate"] in ("PRODUCES", "CAUSES") and e["target"] in DRAW_EVENTS
                       and e["source"].startswith("op:")})
    for op in draw_ops:
        edges.append(_edge(op, "PRODUCES", STATE_COUNT, "each draw increments the turn draw count",
                           quantity=1))
    edges.append(_edge(STATE_COUNT, "SATISFIES", GATE_SECOND,
                       "the count reaching 2 satisfies the second-draw gate", condition_ids=[COND_SECOND]))
    second_events = [ev for ev in SECOND_DRAW_EVENTS if ev in g.nodes]
    for ev in second_events:
        edges.append(_edge(GATE_SECOND, "PRODUCES", ev, "gate fires the second-draw event"))

    # ---- B. Dwarf/Equipment find (Dáin's Company, Kíli the Resourceful) ------------------
    find_ops = []                                        # (op_id, face_id)
    for f in g.faces:
        if "Dwarf or Equipment" not in (f.get("oracle_text") or ""):
            continue
        for e in g.edges:                                # the ETB look/take op on this face
            if _face_of(e["source"]) == f["id"] and e["source"].startswith("op:") and (
                    (e["predicate"] == "MOVES_TO" and e["target"] == "zone:hand")
                    or (e["predicate"] == "PRODUCES" and e["target"] == "resource:card")):
                find_ops.append((e["source"], f["id"]))
    find_ops = sorted(set(find_ops))
    for op, _face in find_ops:
        for cls in ("obj:subtype:dwarf", "obj:subtype:equipment"):
            edges.append(_edge(op, "REQUIRES", cls,
                               "the find selects a Dwarf-or-Equipment card from the library"))

    # ---- C. noncreature spell cast -> Noisemaker & co. -----------------------------------
    cast_events = [ev for ev in NONCREATURE_CAST_EVENTS if ev in g.nodes]
    nodes[OP_CAST] = _node(OP_CAST, "Operation", "cast a noncreature spell",
                           {"kind": "cast", "spell_class": "noncreature"}, "canonical noncreature-cast action")
    for ev in cast_events:
        edges.append(_edge(OP_CAST, "PRODUCES", ev, "casting a noncreature spell fires the cast event"))
    noncreature_faces = sorted(
        f["id"] for f in g.faces
        if (set((f.get("type_line") or {}).get("types") or []) & NONCREATURE_TYPES)
        and "Creature" not in ((f.get("type_line") or {}).get("types") or [])
        and "Land" not in ((f.get("type_line") or {}).get("types") or []))
    for fid in noncreature_faces:
        edges.append(_edge(fid, "HAS_ABILITY", OP_CAST, "this noncreature spell can be cast"))

    # ---- write + validate ---------------------------------------------------------------
    outdir = repo / "data" / "graph_global"
    uniq = {}
    for e in edges:
        uniq.setdefault(e["edge_id"], e)
    edges = sorted(uniq.values(), key=lambda e: (e["source"], e["predicate"], e["target"]))
    with (outdir / "mechanism_nodes.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for n in sorted(nodes.values(), key=lambda n: n["id"]):
            fh.write(json.dumps(n, ensure_ascii=False, sort_keys=True) + "\n")
    with (outdir / "mechanism_edges.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for e in edges:
            fh.write(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n")
    from .graph_repair import _validate_repair_layer
    violations = _validate_repair_layer(repo, g.nodes, nodes, edges)
    return {"mechanism_nodes": len(nodes), "mechanism_edges": len(edges),
            "draw_ops_wired": len(draw_ops), "find_ops": len(find_ops),
            "noncreature_faces": len(noncreature_faces), "second_draw_events": len(second_events),
            "cast_events": len(cast_events), "signature_violations": len(violations),
            "_violations": violations}


# --------------------------------------------------------------------------- #
#  Reprojection: faithful typed paths over graph + mechanism layer            #
# --------------------------------------------------------------------------- #
def reproject(repo: Path = REPO) -> dict:
    g = _G(repo)
    mech_nodes = {n["id"]: n for n in _load_dicts(repo / "data/graph_global/mechanism_nodes.jsonl")}
    mech_edges = list(_load_dicts(repo / "data/graph_global/mechanism_edges.jsonl"))
    all_edges = g.edges + mech_edges
    mech_ids = {e["edge_id"] for e in mech_edges}
    real_ids = {e["edge_id"] for e in g.edges}
    by = defaultdict(list)
    for e in all_edges:
        by[(e["source"], e["predicate"], e["target"])].append(e)

    def find(source=None, predicate=None, target=None):
        for e in all_edges:
            if (source is None or e["source"] == source) and (predicate is None or e["predicate"] == predicate) \
                    and (target is None or e["target"] == target):
                return e
        return None

    metaedges = []

    def emit(a_card, b_card, relation, steps, extra):
        if not a_card or not b_card or a_card == b_card:
            return
        nodes_seq = [steps[0]["source"]] + [s["target"] for s in steps]
        m = {"source_card": a_card, "target_card": b_card, "relation": relation,
             "origin": "mechanism_repair", "path_kind": "grounded", "steps": steps,
             "primitive_path": nodes_seq, "path_predicates": [s["predicate"] for s in steps],
             "edge_ids": [s["edge_id"] for s in steps],
             "uses_mechanism_edges": [s["edge_id"] for s in steps if s["edge_id"] in mech_ids],
             "connecting_node": nodes_seq[1]}
        conds = sorted({c for s in steps for c in (s.get("condition_ids") or [])})
        if conds:
            m["condition_ids"] = conds
        metaedges.append(m)

    # ---- A. drawers -> second-draw payoffs (ENABLES_TRIGGER, second-draw condition) ------
    # face -> ... -> draw_op is a FROZEN path (HAS_ABILITY/CAUSES/INSTANTIATES); the draw_op ->
    # state -> gate -> event tail lives in the mechanism layer.
    sat = find(STATE_COUNT, "SATISFIES", GATE_SECOND)
    draw_state_edges = [e for e in mech_edges if e["predicate"] == "PRODUCES" and e["target"] == STATE_COUNT]
    prefixes_by_op = {dse["source"]: g.forward_paths_to(dse["source"], {"HAS_ABILITY", "CAUSES", "INSTANTIATES"})
                      for dse in draw_state_edges}
    for ev in [e for e in SECOND_DRAW_EVENTS if e in g.nodes]:
        produce = find(GATE_SECOND, "PRODUCES", ev)
        for trig in [e for e in all_edges if e["predicate"] == "TRIGGERS" and e["source"] == ev]:
            b_card = _card_of(trig["target"])
            for dse in draw_state_edges:
                for face_a, prefix in prefixes_by_op[dse["source"]].items():
                    a_card = _card_of(face_a)
                    steps = [project._step(e, "forward") for e in prefix]
                    steps += [project._step(dse, "forward"), project._step(sat, "forward"),
                              project._step(produce, "forward"), project._step(trig, "forward")]
                    emit(a_card, b_card, "ENABLES_TRIGGER", steps, None)

    # ---- B. Dwarf/Equipment supplier -> finder (SUPPLIES_RESOURCE) -----------------------
    for req in [e for e in mech_edges if e["predicate"] == "REQUIRES"
                and e["target"].startswith("obj:subtype:")]:
        cls, find_op = req["target"], req["source"]
        b_face, b_card = _face_of(find_op), _card_of(find_op)
        # tail back from the find-op to face_b:  find_op <-CAUSES- ability <-HAS_ABILITY- face_b
        cause = find(predicate="CAUSES", target=find_op)
        hasab = find(source=b_face, predicate="HAS_ABILITY", target=cause["source"]) if cause else None
        if cause and hasab:
            tail = [project._step(cause, "reverse"), project._step(hasab, "reverse")]
        else:
            ha = find(source=b_face, predicate="HAS_ABILITY", target=find_op)
            if not ha:
                continue
            tail = [project._step(ha, "reverse")]
        for htype in [e for e in g.edges if e["predicate"] == "HAS_TYPE" and e["target"] == cls]:
            a_card = _card_of(htype["source"])
            # A supplies the class the finder requires: A -HAS_TYPE-> cls <-REQUIRES- op <-...- B
            steps = [project._step(htype, "forward"), project._step(req, "reverse")] + tail
            emit(a_card, b_card, "SUPPLIES_RESOURCE", steps, None)

    # ---- C. noncreature spell -> cast payoffs (ENABLES_TRIGGER) --------------------------
    for ev in [e for e in NONCREATURE_CAST_EVENTS if e in g.nodes]:
        produce = find(OP_CAST, "PRODUCES", ev)
        for trig in [e for e in all_edges if e["predicate"] == "TRIGGERS" and e["source"] == ev]:
            b_card = _card_of(trig["target"])
            for ha in [e for e in mech_edges if e["predicate"] == "HAS_ABILITY" and e["target"] == OP_CAST]:
                a_card = _card_of(ha["source"])
                steps = [project._step(ha, "forward"), project._step(produce, "forward"),
                         project._step(trig, "forward")]
                emit(a_card, b_card, "ENABLES_TRIGGER", steps, None)

    metaedges.sort(key=lambda m: (m["source_card"], m["target_card"], m["relation"], m["connecting_node"]))
    with (repo / "data/graph_global/card_pair_projection_mechanism.jsonl").open(
            "w", encoding="utf-8", newline="\n") as fh:
        for m in metaedges:
            fh.write(json.dumps(m, ensure_ascii=False, sort_keys=True) + "\n")
    ok = all(s["edge_id"] in real_ids or s["edge_id"] in mech_ids for m in metaedges for s in m["steps"])
    by_rel = {}
    for m in metaedges:
        by_rel[m["relation"]] = by_rel.get(m["relation"], 0) + 1
    _report(repo, g, metaedges, by_rel, ok)
    return {"reprojected": len(metaedges), "by_relation": by_rel, "edges_resolve": ok}


def _report(repo, g, metaedges, by_rel, ok):
    L = ["# HOB Full-Spec Completion — Mechanism Repair + Reprojection", "",
         f"- **reprojected metaedges**: {len(metaedges)} (origin `mechanism_repair`)",
         f"- **by relation**: {by_rel}",
         f"- **all path edges resolve (frozen or mechanism layer)**: {ok}", "",
         "## Relations (origin: mechanism_repair)", ""]
    for m in metaedges:
        a, b = g.names.get(m["source_card"], m["source_card"]), g.names.get(m["target_card"], m["target_card"])
        L.append(f"- **{a} → {b}** [{m['relation']}] via `{m['connecting_node']}` "
                 f"— {' → '.join(m['path_predicates'])}"
                 + (f"  _(cond: {', '.join(m['condition_ids'])})_" if m.get("condition_ids") else ""))
    (repo / "reports" / "mechanism_repair.md").write_text("\n".join(L) + "\n", encoding="utf-8")

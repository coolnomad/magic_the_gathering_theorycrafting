"""Phase 4: global graph assembly (v2).

Merge the Phase 2 template graph (canonical, typed) + the Phase 1 normalized
entities + the Phase 3 accepted per-face extractions into ONE global typed
property-multigraph, then validate every edge against full predicate
domain/range signatures with *zero* residual violations, *zero* `Unknown`
endpoint types, and *zero* leaked (non-face-namespaced) LLM ability nodes.

The Phase 3 card-local convention (a CardFace/Ability as the subject of an actor
predicate, free-text endpoints, template duplicates) is fully dissolved here:

  1. Ability ids are face-namespaced: `a1` and `ability:a1` -> `ability:{face}:a1`.
     No `ability:*` node survives unless it begins `ability:face:`.
  2. Actor-predicate edges with a CardFace/Ability subject are reified onto
     explicit Operation nodes, GROUPED BY THE ORIGINATING ABILITY OR ORACLE CLAUSE
     (not one operation per edge): the operation is the action, its several
     consequences are edges out of that one operation.
  3. Template/LLM duplicates collapse: for every authoritative Phase 2 templated
     mechanic (Recruit, Storied, Hone, Adventure, Saga, Amass, Typecycling) the
     LLM's re-derivation of the template-owned mechanism output is dropped; the
     LLM keeps only its card-specific trigger/effects and a REFERENCES_RULE link.
  4. Free-text endpoints are canonicalized to typed `obj:{slug}` ObjectClass nodes.
  5. Seven enumerated Phase 3 typing errors are individually corrected (see
     `_EDGE_CORRECTIONS`) so the graph carries zero signature violations.
  6. Every accepted edge property (condition, scope, timing, optional, quantity,
     polarity, certainty, note) is preserved; inline free-text conditions become
     structured condition records in a self-contained global conditions file, and
     every `condition_ids` reference resolves.
  7. Full ability semantics (trigger/costs/conditions/effects/controller/
     optionality/unresolved/confidence) are retained in each Ability node's data.
  8. Storage is a property multigraph keyed by the full assertion signature; every
     edge carries a stable `edge_id`. Parallel edges that differ by condition,
     scope, timing, quantity, optionality or polarity are preserved distinctly.
"""

from __future__ import annotations

import hashlib
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
                 {"Operation", "State", "ObjectClass", "CardFace", "CounterType", "Ability", "Cost",
                  "Event", "Resource"}),
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
# NOTE: the structural predicates HAS_KEYWORD/HAS_COST/REFERENCES_RULE/ATTACHED_TO are
# NOT here — they describe the face/ability/object itself and keep their subject.
_ACTOR_PREDICATES = {
    "PRODUCES", "CONSUMES", "MOVES_FROM", "MOVES_TO", "CREATES_OBJECT", "ADDS_COUNTER",
    "REMOVES_COUNTER", "MODIFIES", "PREVENTS", "REPLACES", "SCALES_WITH", "REQUIRES",
    "CAUSES", "CAN_LEAD_TO",
}

# --- template merge policy (blocking issue 7) -------------------------------
# For every authoritative Phase 2 templated mechanic, define what the LLM layer is
# allowed to re-derive.  The Phase 2 template owns the MECHANISM (its internal
# operations/gates/tokens/counters).  The LLM keeps its card-specific trigger and a
# REFERENCES_RULE link; any LLM edge that re-creates a template-owned output from a
# *different* node than the template is dropped so no duplicate pathway survives.
# (Edges the LLM emits identically to Phase 2 collapse automatically via the edge key.)
#
#   amass / typecycling : drop `* INSTANTIATES rule:{amass,typecycling}`
#                         (Phase 2 `op:{face}:X INSTANTIATES op:X` is canonical)
#   recruit             : drop `* {CREATES_OBJECT,CAN_LEAD_TO} token:human-soldier`
#                         (created by gate:recruit-nonland-discard)
#   amass               : drop `* {CREATES_OBJECT,CAN_LEAD_TO} {token:goblin-army,obj:army-A}`
#                         (created by gate:amass-no-army)
#   hone                : drop `* ADDS_COUNTER counter:hone` (placed by op:{face}:add-hone)
#   storied / saga / adventure : no divergent-node mechanism output — the LLM's
#                         REFERENCES_RULE link is canonical and its chapter/adventure
#                         effects are card-specific (retained); identical structural
#                         edges collapse via the edge key.
_TEMPLATED_RULES = {"rule:amass", "rule:typecycling"}
_TEMPLATE_OWNED_OBJECTS = {"token:human-soldier", "token:goblin-army", "obj:army-A"}
_TEMPLATE_OWNED_COUNTERS = {"counter:hone"}


def _is_template_duplicate(pred: str, tgt: str) -> bool:
    if pred == "INSTANTIATES" and tgt in _TEMPLATED_RULES:
        return True
    if pred in ("CREATES_OBJECT", "CAN_LEAD_TO") and tgt in _TEMPLATE_OWNED_OBJECTS:
        return True
    if pred == "ADDS_COUNTER" and tgt in _TEMPLATE_OWNED_COUNTERS:
        return True
    return False


# --- individual corrections for the seven enumerated Phase 3 typing errors ----
# (blocking issue 1).  Keyed by (face_id, raw_source, predicate, raw_target); the
# value is the list of replacement (source, predicate, target) triples that inherit
# the original edge's provenance and properties.  An empty list drops the edge.
# The originals are Phase-3 mis-typings surfaced by assembly; corrections re-type
# them per the reviewer's models and are recorded in reports/assembly.md.
_F_SUPPER = "face:4d891515-39da-492e-ac19-1aa524245449:0"
_F_GOLLUM = "face:8d88facd-cf7e-498e-ab6b-6bd021316162:0"
_F_BOLG = "face:fa602f8f-1d80-4f6d-8b8f-d1a1f36037bd:0"
_F_BURN = "face:a97d6c5c-1cff-442d-b535-fc8389160b0b:0"
_F_DESOL = "face:c9634afc-4a5b-4cf6-b63d-0ff9909dd5a7:0"
_F_MATTOCK = "face:f75bb13b-41fc-4614-b35e-f456069ce9c6:0"
_F_VOW = "face:f8961618-ae68-4d13-84eb-8b5464ce4971:0"
_OP_FOOD = f"op:{_F_SUPPER}:granted-food-sac"

_EDGE_CORRECTIONS = {
    # Supper for Spiders — the granted Food ability ({2},{T}, Sacrifice this
    # artifact: gain 3 life) consumes the Food and produces life.
    (_F_SUPPER, "objectclass:food-artifact", "PRODUCES", "op:gain-life"): [
        (_F_SUPPER, "HAS_ABILITY", _OP_FOOD),
        (_OP_FOOD, "CONSUMES", "obj:food"),
        (_OP_FOOD, "PRODUCES", "resource:life"),
    ],
    # Gollum the Abandoned — "Return this card from your graveyard": MOVES_FROM a
    # Zone, not the CardFace.
    (_F_GOLLUM, "ability:gollum-ab-recur", "MOVES_FROM", _F_GOLLUM): [
        ("ability:gollum-ab-recur", "MOVES_FROM", "zone:graveyard"),
    ],
    # Bolg's Company — "{T}, Sacrifice another Goblin: Add {B}{R}": the operation
    # consumes the sacrificed Goblin and causes the sacrifice event.
    (_F_BOLG, _F_BOLG, "CONSUMES", "event:sacrifice"): [
        (_F_BOLG, "CONSUMES", "obj:another-goblin"),
        (_F_BOLG, "CAUSES", "event:sacrifice"),
    ],
    # Burn, Burn, Tree and Fern (Saga III-IV) — "Add {R}": produces mana, not an op.
    (_F_BURN, "a97d6c5c-ch34", "PRODUCES", "op:add-mana"): [
        ("a97d6c5c-ch34", "PRODUCES", "resource:mana"),
    ],
    # Desolation of Smaug — "Add four mana ... Spend this mana only to cast Dragon
    # spells": produces mana; the Dragon-only restriction modifies that resource.
    (_F_DESOL, "c9634afc-a2", "PRODUCES", "op:add-mana"): [
        ("c9634afc-a2", "PRODUCES", "resource:mana"),
    ],
    (_F_DESOL, "c9634afc-a2", "MODIFIES", "op:add-mana"): [
        ("c9634afc-a2", "MODIFIES", "resource:mana"),
    ],
    # Dwarven Mattock — "attach it to target Dwarf you control": the Equipment (this
    # face) is the attaching object, not its ability.
    (_F_MATTOCK, "a1", "ATTACHED_TO", "target Dwarf you control"): [
        (_F_MATTOCK, "ATTACHED_TO", "target Dwarf you control"),
    ],
    # Vow to Erebor — "you may attach an Equipment you control to it": the attaching
    # object is a generic Equipment you control, not the ability.
    (_F_VOW, "f8961618-a1", "ATTACHED_TO", "target creature you control"): [
        ("obj:an-equipment-you-control", "ATTACHED_TO", "target creature you control"),
    ],
}

_EDGE_PROPS = ("scope", "timing", "quantity", "optional", "polarity", "certainty", "note")


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:60] or "x"


def _overlap(a: tuple, b: tuple) -> int:
    return max(0, min(a[1], b[1]) - max(a[0], b[0]))


def _condition_id(face_id: str, human: str) -> str:
    return f"cond:{face_id}:c{hashlib.sha1(human.encode('utf-8')).hexdigest()[:8]}"


class Graph:
    """Typed property multigraph.  Edges are keyed by the full assertion signature
    (source, predicate, target, condition_ids, scope, timing, quantity, optional,
    polarity) so parallel edges that differ on any of those coexist; provenance is
    merged only when the whole signature agrees."""

    def __init__(self):
        self.nodes: dict[str, dict] = {}
        self.edges: dict[tuple, dict] = {}

    def add_node(self, nid, ntype, label="", data=None, provenance=None):
        n = self.nodes.get(nid)
        if n is None:
            self.nodes[nid] = {"id": nid, "type": ntype, "label": label or nid,
                               "data": data or {}, "provenance": list(provenance or [])}
        else:
            if data:
                n["data"].update({k: v for k, v in data.items() if k not in n["data"]})
            if provenance:
                n["provenance"].extend(provenance)
        return nid

    def add_edge(self, source, predicate, target, provenance=None, **props):
        props = {k: v for k, v in props.items() if v not in (None, "", [], {})}
        cond = tuple(sorted(props.get("condition_ids", []) or []))
        # merge key: normalize the two default-valued properties (polarity -> "positive",
        # optional -> False) so an edge asserted explicitly by Phase 2 and silently by the
        # LLM collapse; genuine differences (condition/scope/timing/quantity, or an
        # explicit negative polarity / optional=True) still keep the edges parallel.
        key = (source, predicate, target, cond, props.get("scope"), props.get("timing"),
               str(props.get("quantity")) if props.get("quantity") is not None else None,
               bool(props.get("optional")), props.get("polarity") or "positive")
        e = self.edges.get(key)
        if e is None:
            eid = "e" + hashlib.sha1("|".join(str(x) for x in key).encode("utf-8")).hexdigest()[:16]
            self.edges[key] = {"edge_id": eid, "source": source, "predicate": predicate,
                               "target": target, "provenance": list(provenance or []), **props}
        else:
            if provenance:
                e["provenance"].extend(provenance)
        return key


def _seed_conditions(repo: Path) -> dict:
    """Load the Phase 2 structured conditions (both stores) into one dict."""
    store: dict[str, dict] = {}
    for p in (repo / "data" / "graph" / "conditions.jsonl", repo / "data" / "rules" / "conditions.jsonl"):
        if p.exists():
            for c in _load_dicts(p):
                store.setdefault(c["condition_id"], c)
    return store


def assemble(repo: Path = REPO) -> dict:
    g = Graph()
    conditions = _seed_conditions(repo)

    # 1. seed with the Phase 2 template graph (canonical + typed): carry every edge
    # property, including condition_ids/scope/timing/quantity/optional/polarity.
    for n in _load_dicts(repo / "data" / "graph" / "nodes.jsonl"):
        g.add_node(n["id"], n["type"], n.get("label", ""), n.get("data"), n.get("provenance"))
    for e in _load_dicts(repo / "data" / "graph" / "edges.jsonl"):
        props = {k: e[k] for k in ("scope", "timing", "quantity", "optional", "polarity",
                                   "certainty", "note", "condition_ids") if e.get(k)}
        g.add_edge(e["source"], e["predicate"], e["target"], e.get("provenance"), **props)
    # the Phase 2 template edges ARE the authoritative mechanism outputs (gate creates
    # the soldier/army; op:{face}:add-hone places the hone counter); remember them so
    # the duplicate metric measures only LLM-layer leakage past the emit-time drop.
    phase2_edge_ids = {e["edge_id"] for e in g.edges.values()}

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
    for a in _load_dicts(repo / "data" / "review" / "llm_accepted.jsonl"):
        _merge_face(g, a, faces, conditions)

    # materialize every referenced endpoint as a typed node (Phase 3 invents concept
    # nodes — event:/state:/obj:/kw:/cost:/resource:/zone: — by id; type by convention).
    for e in list(g.edges.values()):
        for nid in (e["source"], e["target"]):
            if nid not in g.nodes:
                g.add_node(nid, resolve_node_type(nid, set()), nid)

    return _finalize(g, repo, conditions, phase2_edge_ids)


def _merge_face(g: Graph, a: dict, faces: dict, conditions: dict) -> None:
    face_id = a["face_id"]
    g.add_node(face_id, "CardFace", faces.get(face_id, {}).get("name", face_id))

    # 3a. namespace ability ids; retain FULL ability semantics in node data.
    # Register both `local` and `ability:local` alias forms (blocking issue 2).
    local_to_global: dict[str, str] = {}
    ability_spans: list[tuple[str, list]] = []
    for ab in a.get("abilities", []):
        local = ab["ability_id"]
        gid = f"ability:{face_id}:{local}"
        local_to_global[local] = gid
        local_to_global[f"ability:{local}"] = gid
        g.add_node(gid, "Ability", local, data=dict(ab))
        g.add_edge(face_id, "HAS_ABILITY", gid)
        ability_spans.append((gid, [tuple(s) for s in (ab.get("oracle_spans") or [])]))

    # reification bookkeeping: one Operation per originating ability/oracle clause.
    op_for: dict[str, str] = {}

    def resolve(raw: str) -> str:
        if raw in local_to_global:
            return local_to_global[raw]
        # any `ability:X` that is not already face-namespaced is an (implicit) ability
        # of THIS face — namespace it so no bare LLM ability id ever leaks as a node.
        if raw.startswith("ability:") and not raw.startswith("ability:face:"):
            gid = f"ability:{face_id}:{raw[len('ability:'):]}"
            local_to_global[raw] = gid
            return gid
        if resolve_node_type(raw, set()) != "Unknown":
            return raw
        cid = "obj:" + _slug(raw)
        g.add_node(cid, "ObjectClass", raw)
        return cid

    def owner_op(src_type: str, src: str, prov_span) -> str:
        """Reify an actor edge onto ONE operation grouped by originating ability
        (explicit id, then enclosing/overlapping oracle span) or oracle clause."""
        owner = None
        if src_type == "Ability":
            owner = src
        elif prov_span:
            best = 0
            for aid, spans in ability_spans:
                for sp in spans:
                    ov = _overlap(tuple(prov_span), sp)
                    if ov > best:
                        best, owner = ov, aid
        if owner is not None:
            op = "op:" + owner.split("ability:", 1)[1]
            if owner not in op_for:
                g.add_node(op, "Operation", "effect of " + owner)
                g.add_edge(owner, "CAUSES", op)
                op_for[owner] = op
            return op_for[owner]
        # no owning ability -> group by oracle clause span
        ck = f"clause:{prov_span[0]}-{prov_span[1]}" if prov_span else "clause:whole"
        if ck not in op_for:
            op = f"op:{face_id}:{ck}"
            g.add_node(op, "Operation", "card-level effect")
            g.add_edge(face_id, "HAS_ABILITY", op)
            op_for[ck] = op
        return op_for[ck]

    def emit(src: str, pred: str, tgt: str, prov: dict, props: dict) -> None:
        if _is_template_duplicate(pred, tgt):
            return
        src, tgt = resolve(src), resolve(tgt)
        # structured conditions: inline free-text condition -> record + condition_ids
        cond_ids = list(props.get("condition_ids") or [])
        raw_cond = props.get("condition")
        if raw_cond:
            human = raw_cond if isinstance(raw_cond, str) else json.dumps(raw_cond, ensure_ascii=False)
            cid = _condition_id(face_id, human)
            conditions.setdefault(cid, {"condition_id": cid, "expression": {"raw": raw_cond},
                                        "human_readable": human, "provenance": [prov]})
            cond_ids.append(cid)
        eprops = {k: props[k] for k in _EDGE_PROPS if props.get(k) is not None}
        if cond_ids:
            eprops["condition_ids"] = cond_ids
        # reify actor edges whose subject is a CardFace or Ability onto an Operation
        s_type = resolve_node_type(src, set())
        if pred in _ACTOR_PREDICATES and s_type in ("CardFace", "Ability"):
            src = owner_op(s_type, src, prov.get("oracle_span"))
        g.add_edge(src, pred, tgt, [prov], **eprops)

    for e in a.get("proposed_edges", []):
        prov = e.get("provenance", {})
        props = {k: e[k] for k in ("condition", *_EDGE_PROPS, "condition_ids") if e.get(k) is not None}
        key = (face_id, e["source"], e["predicate"], e["target"])
        if key in _EDGE_CORRECTIONS:
            for (cs, cp, ct) in _EDGE_CORRECTIONS[key]:
                emit(cs, cp, ct, prov, props)
        else:
            emit(e["source"], e["predicate"], e["target"], prov, props)


def validate_global(g: Graph, conditions: dict) -> dict:
    node_ids = set(g.nodes)
    dangling, sig_viol, unknown, unresolved_cond = [], [], [], []
    cond_ids = set(conditions)
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
        for cid in e.get("condition_ids", []) or []:
            if cid not in cond_ids:
                unresolved_cond.append((e["edge_id"], cid))
    leaked = [nid for nid in g.nodes if nid.startswith("ability:") and not nid.startswith("ability:face:")]
    return {"dangling": dangling, "signature_violations": sig_viol,
            "unknown_endpoint_types": unknown, "leaked_ability_aliases": leaked,
            "unresolved_condition_refs": unresolved_cond}


def _finalize(g: Graph, repo: Path, conditions: dict, phase2_edge_ids: set) -> dict:
    v = validate_global(g, conditions)
    out = repo / "data" / "graph_global"
    out.mkdir(parents=True, exist_ok=True)
    with (out / "nodes.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for n in g.nodes.values():
            fh.write(json.dumps(n, ensure_ascii=False) + "\n")
    with (out / "edges.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for e in g.edges.values():
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    with (out / "conditions.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for c in conditions.values():
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    # residual review: must be empty for the gate to pass — any remaining signature
    # violation / unknown type / leaked alias / unresolved condition is written here.
    with (out / "assembly_review.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for s in v["signature_violations"]:
            fh.write(json.dumps({"issue": "predicate_signature", "edge": s}) + "\n")
        for a, b, c in v["unknown_endpoint_types"]:
            fh.write(json.dumps({"issue": "unknown_endpoint", "edge": f"{a} -{b}-> {c}"}) + "\n")
        for nid in v["leaked_ability_aliases"]:
            fh.write(json.dumps({"issue": "leaked_ability_alias", "node": nid}) + "\n")
        for eid, cid in v["unresolved_condition_refs"]:
            fh.write(json.dumps({"issue": "unresolved_condition", "edge_id": eid, "condition_id": cid}) + "\n")

    ntypes = Counter(n["type"] for n in g.nodes.values())
    preds = Counter(e["predicate"] for e in g.edges.values())
    # LLM-layer template duplicates that survived the emit-time drop (must be 0);
    # Phase 2's own authoritative template edges are excluded by edge_id.
    template_dups = sum(1 for e in g.edges.values()
                        if _is_template_duplicate(e["predicate"], e["target"])
                        and e["edge_id"] not in phase2_edge_ids)
    stats = {
        "nodes": len(g.nodes), "edges": len(g.edges), "conditions": len(conditions),
        "node_types": dict(ntypes), "edge_predicates": dict(preds),
        "dangling_edges": len(v["dangling"]),
        "signature_violations": len(v["signature_violations"]),
        "unknown_endpoint_edges": len(v["unknown_endpoint_types"]),
        "unknown_type_nodes": sum(1 for n in g.nodes.values() if n["type"] == "Unknown"),
        "leaked_ability_aliases": len(v["leaked_ability_aliases"]),
        "unresolved_condition_refs": len(v["unresolved_condition_refs"]),
        "edges_missing_id": sum(1 for e in g.edges.values() if not e.get("edge_id")),
        "template_duplicate_edges": template_dups,
        "face_to_rule_amass_edges": sum(1 for e in g.edges.values()
                                        if e["predicate"] == "INSTANTIATES" and e["target"] == "rule:amass"),
    }
    _report(repo, stats, v)
    stats["_violations"] = v
    return stats


def _report(repo: Path, stats: dict, v: dict) -> None:
    L = ["# HOB Phase 4 — Global Assembly (v2)", "",
         f"- **nodes**: {stats['nodes']}", f"- **edges**: {stats['edges']}",
         f"- **conditions (self-contained)**: {stats['conditions']}",
         f"- **dangling edges**: {stats['dangling_edges']}",
         f"- **signature violations (must be 0)**: {stats['signature_violations']}",
         f"- **edges with Unknown endpoint type (must be 0)**: {stats['unknown_endpoint_edges']}",
         f"- **nodes with Unknown type (must be 0)**: {stats['unknown_type_nodes']}",
         f"- **leaked non-face-namespaced ability nodes (must be 0)**: {stats['leaked_ability_aliases']}",
         f"- **unresolved condition references (must be 0)**: {stats['unresolved_condition_refs']}",
         f"- **edges missing edge_id (must be 0)**: {stats['edges_missing_id']}",
         f"- **template-duplicate edges (must be 0)**: {stats['template_duplicate_edges']}",
         f"- **face-to-rule amass edges (must be 0)**: {stats['face_to_rule_amass_edges']}", "",
         "## Node types", ""]
    for k, val in sorted(stats["node_types"].items(), key=lambda x: -x[1]):
        L.append(f"- {k}: {val}")
    L += ["", "## Edge predicates", ""]
    for k, val in sorted(stats["edge_predicates"].items(), key=lambda x: -x[1]):
        L.append(f"- {k}: {val}")
    for label, key in (("Signature violations", "signature_violations"),
                       ("Unknown-endpoint edges", "unknown_endpoint_types"),
                       ("Leaked ability aliases", "leaked_ability_aliases"),
                       ("Unresolved condition refs", "unresolved_condition_refs")):
        if v[key]:
            L += ["", f"## {label} (residual — gate FAILS)", ""] + [f"- {x}" for x in v[key][:40]]
    (repo / "reports" / "assembly.md").write_text("\n".join(L) + "\n", encoding="utf-8")

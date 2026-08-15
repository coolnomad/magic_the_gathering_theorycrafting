"""Phase 5: derive card-pair projections by bounded traversal of the primitive graph.

We do NOT brute-force the 193x193 = 37,249 ordered pairs. For each named relation we
traverse the frozen Phase 4 primitive graph (`data/graph_global/{nodes,edges}.jsonl`)
along an allowed path grammar that joins two cards through a *functional* concept node
(a produced resource, a fired event, a count-gate, a prevented operation) — never a
mere shared ontology class (`obj:type:*`, `obj:supertype:*`), which is meaningless.

Faithfulness rules (Phase 5 review pt1):
  - every path STEP is either a real Phase 4 edge (with an explicit `direction` of
    forward/reverse) or a clearly-labelled `derived` bridge with a stable unique id;
  - every step carries the semantic edge properties it had in Phase 4
    (`condition_ids`, `optional`, `polarity`, `scope`, `creates_for`);
  - INFRASTRUCTURE_CASTING respects mana colour compatibility (a source contributes
    to a cost only via a matching pip or a generic/variable component) and includes
    controller-owned Treasure paths (but never opponent-only mana, e.g. Bilbo);
  - alternative mechanisms are kept as separate `alternative_paths` (disjuncts), not
    merged — only identical path signatures collapse.

Output: `data/graph_global/card_pair_projection.jsonl`, `reports/pair_projection.md`.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from .pipeline import REPO, _load_dicts

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_FACE = re.compile(r"face:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}:\d+")
_ONTOLOGY_PREFIXES = ("obj:type:", "obj:subtype:", "obj:supertype:")
_SEM_PROPS = ("condition_ids", "optional", "polarity", "scope", "creates_for")


def _card_of(nid: str) -> str | None:
    m = _UUID.search(nid)
    return "card:" + m.group(0) if m else None


def _face_of(nid: str) -> str | None:
    m = _FACE.search(nid)
    return m.group(0) if m else None


def _concept(nid: str) -> bool:
    return nid.startswith(("resource:", "event:", "state:", "counter:", "token:", "gate:", "zone:"))


class Graph:
    def __init__(self, repo: Path):
        self.nodes = {n["id"]: n for n in _load_dicts(repo / "data/graph_global/nodes.jsonl")}
        self.edges = list(_load_dicts(repo / "data/graph_global/edges.jsonl"))
        self.edge_ids = {e["edge_id"] for e in self.edges}
        self.out = defaultdict(list)
        self.inc = defaultdict(list)
        for e in self.edges:
            self.out[e["source"]].append(e)
            self.inc[e["target"]].append(e)
        self.cards = [nid for nid, n in self.nodes.items() if n["type"] == "Card"]
        # colours a face can produce (from normalized data carried onto the node)
        self.face_colors = {nid: set(n["data"].get("produced_mana") or [])
                            for nid, n in self.nodes.items() if n["type"] == "CardFace"}


# --------------------------------------------------------------------------- #
#  Path steps: real (forward/reverse) vs derived bridge                        #
# --------------------------------------------------------------------------- #
def _step(edge: dict, direction: str) -> dict:
    src, tgt = (edge["source"], edge["target"]) if direction == "forward" else (edge["target"], edge["source"])
    st = {"edge_id": edge["edge_id"], "predicate": edge["predicate"], "source": src, "target": tgt,
          "direction": direction, "derived": False}
    for k in _SEM_PROPS:
        v = edge.get(k)
        if v not in (None, "", [], {}):
            st[k] = v
    st["provenance"] = list(edge.get("provenance") or [])
    return st


def _derived(did: str, predicate: str, source: str, target: str, note: str, **props) -> dict:
    st = {"edge_id": did, "predicate": predicate, "source": source, "target": target,
          "direction": "forward", "derived": True,
          "provenance": [{"source": "phase5_projection", "derivation": note}]}
    st.update({k: v for k, v in props.items() if v not in (None, "", [], {})})
    return st


# --------------------------------------------------------------------------- #
#  Mana colour compatibility                                                   #
# --------------------------------------------------------------------------- #
def _contributes_to_cost(colors: set, mana_cost: dict) -> bool:
    """A mana of the given colour set can contribute to this casting cost if it pays a
    generic/variable component, or matches one of the coloured/colourless pips."""
    if mana_cost.get("has_variable") or mana_cost.get("generic"):
        return True                                   # any mana pays generic / {X}
    pips = set((mana_cost.get("pips") or {}).keys())
    return bool(colors & pips)                         # matching coloured or {C} pip


# --------------------------------------------------------------------------- #
#  Relation derivations — each yields (relation, src_card, tgt_card, steps)    #
# --------------------------------------------------------------------------- #
def _mana_sources(g: Graph):
    """Yield (card, colours, prefix_steps, mana_resource_node) for every CONTROLLER
    mana source: a face's own direct mana op, or a controller-owned Treasure-style
    token the card creates that itself produces mana. Opponent-only mana is excluded."""
    for e in g.edges:                                 # direct: op PRODUCES resource:mana*
        if e["predicate"] == "PRODUCES" and e["target"].startswith("resource:mana") \
                and not e["source"].startswith("op:token:"):
            face = _face_of(e["source"])
            colors = g.face_colors.get(face, set())
            yield _card_of(e["source"]), colors, [_step(e, "forward")], e["target"]
    for ce in g.edges:                                # indirect: card creates a mana token
        if ce["predicate"] != "CREATES_OBJECT" or not ce["target"].startswith("token:"):
            continue
        if (ce.get("creates_for") or "controller") != "controller":
            continue                                  # skip opponent-owned tokens (Bilbo)
        tok = ce["target"]
        ha = next((e for e in g.out[tok] if e["predicate"] == "HAS_ABILITY"
                   and e["target"].startswith(f"op:{tok}")), None)
        if not ha:
            continue
        prod = next((e for e in g.out[ha["target"]] if e["predicate"] == "PRODUCES"
                     and e["target"].startswith("resource:mana")), None)
        if not prod:
            continue
        colors = set(g.nodes[tok]["data"].get("produced_mana") or [])
        yield (_card_of(ce["source"]), colors,
               [_step(ce, "forward"), _step(ha, "forward"), _step(prod, "forward")], prod["target"])


def rel_infrastructure_casting(g: Graph):
    # castable cards: a casting-cost node that requires mana
    castable = []
    for e in g.edges:
        if e["predicate"] == "HAS_COST" and e["target"].endswith(":cast"):
            mc = g.nodes.get(e["target"], {}).get("data", {}).get("mana_cost") or {}
            if mc.get("generic") or mc.get("pips") or mc.get("has_variable"):
                castable.append((_card_of(e["source"]), e, mc))
    sources = list(_mana_sources(g))
    for (a, colors, prefix, mana_node) in sources:
        if not a:
            continue
        for (b, ce, mc) in castable:
            if not b or not _contributes_to_cost(colors, mc):
                continue
            bridge = _derived(f"derived:CONTRIBUTES_TO_COST:{mana_node}->{ce['target']}",
                              "CONTRIBUTES_TO_COST", mana_node, ce["target"],
                              "mana_colour_compatible_with_casting_cost")
            steps = prefix + [bridge, _step(ce, "reverse")]
            yield ("INFRASTRUCTURE_CASTING", a, b, steps)


def rel_contributes_to_gate(g: Graph):
    """A QUALIFIES_FOR a count-gate; the gate's state ENABLES B's payoff ability."""
    beneficiaries = defaultdict(list)                 # gate -> [(card_b, tail_steps)]
    for e in g.edges:
        if not e["source"].startswith("gate:"):
            continue
        if e["predicate"] == "ENABLES":
            b = _card_of(e["target"])
            if b:
                beneficiaries[e["source"]].append((b, [_step(e, "forward")]))
        elif e["predicate"] == "PRODUCES" and e["target"].startswith("state:"):
            for e2 in g.out[e["target"]]:
                if e2["predicate"] == "ENABLES":
                    b = _card_of(e2["target"])
                    if b:
                        beneficiaries[e["source"]].append((b, [_step(e, "forward"), _step(e2, "forward")]))
    for e in g.edges:
        if e["predicate"] in ("QUALIFIES_FOR", "CONTRIBUTES_TO") and e["target"].startswith("gate:"):
            a = _card_of(e["source"])
            if not a:
                continue
            for (b, tail) in beneficiaries.get(e["target"], []):
                yield ("CONTRIBUTES_TO_GATE", a, b, [_step(e, "forward")] + tail)


def _participant_role(edge: dict) -> tuple[str, str]:
    """Infer (resource_for, resource_role) for a resource PRODUCES/CONSUMES/REQUIRES
    edge from its scope + Oracle provenance. PRODUCES=gain; REQUIRES=requirement;
    CONSUMES is a `loss` when someone LOSES the resource (not a spendable supply) or a
    `spend` when it is paid/discarded/sacrificed. Participant defaults to the
    controller (the MTG default actor) unless the text names another player/owner."""
    txt = ((edge.get("scope") or "") + " "
           + " ".join((p.get("text") or "") for p in edge.get("provenance", []))).lower()
    if "opponent" in txt:
        who = "opponent"
    elif "each player" in txt:
        who = "each_player"
    elif "target player" in txt:
        who = "target_player"
    elif "owner" in txt:
        who = "object_owner"
    else:
        who = "controller"
    pred = edge["predicate"]
    if pred == "PRODUCES":
        role = "gain"
    elif pred == "REQUIRES":
        role = "requirement"
    elif "lose" in txt or "loses" in txt:
        role = "loss"
    else:
        role = "spend"
    return who, role


def rel_supplies_resource(g: Graph):
    """A produces a resource that B spends/requires. Participant-aware: a controller's
    gained life does NOT enable an opponent's life LOSS; a resource that someone merely
    loses is not a spendable supply. Same-participant gain->spend/requirement is
    asserted; cross-participant (resolved) is retained as participant_unresolved for the
    Part 2 audit; a `loss` consumer is dropped as a false supply."""
    producers = defaultdict(list)
    consumers = defaultdict(list)
    for e in g.edges:
        t = e["target"]
        if t.startswith(_ONTOLOGY_PREFIXES) or not _concept(t):
            continue
        if e["predicate"] == "PRODUCES":
            producers[t].append(e)
        elif e["predicate"] in ("CONSUMES", "REQUIRES"):
            consumers[t].append(e)
    for concept, prod in producers.items():
        for pe in prod:
            a = _card_of(pe["source"])
            p_for, p_role = _participant_role(pe)
            for ce in consumers.get(concept, []):
                b = _card_of(ce["source"])
                c_for, c_role = _participant_role(ce)
                if not a or not b or c_role == "loss":
                    continue                          # loss is not a spendable supply -> drop
                resolved = p_for == c_for
                ps = _step(pe, "forward"); ps["resource_for"], ps["resource_role"] = p_for, p_role
                cs = _step(ce, "reverse"); cs["resource_for"], cs["resource_role"] = c_for, c_role
                extra = {"participant_status": "resolved" if resolved else "participant_unresolved",
                         "asserted": resolved,
                         "resource_for_producer": p_for, "resource_role_producer": p_role,
                         "resource_for_consumer": c_for, "resource_role_consumer": c_role}
                yield ("SUPPLIES_RESOURCE", a, b, [ps, cs], extra)


def rel_enables_trigger(g: Graph):
    produced = defaultdict(list)
    for e in g.edges:
        if e["predicate"] in ("PRODUCES", "CAUSES", "CREATES_OBJECT", "MOVES_TO") and e["target"].startswith("event:"):
            produced[e["target"]].append(e)
    for e in g.edges:
        if e["predicate"] == "TRIGGERS":
            b = _card_of(e["target"])
            for pe in produced.get(e["source"], []):
                a = _card_of(pe["source"])
                if a and b:
                    yield ("ENABLES_TRIGGER", a, b, [_step(pe, "forward"), _step(e, "forward")])


def rel_prevents_operation(g: Graph):
    produced = defaultdict(list)
    for e in g.edges:
        if e["predicate"] in ("PRODUCES", "CAUSES", "CREATES_OBJECT") and _concept(e["target"]):
            produced[e["target"]].append(e)
    for e in g.edges:
        if e["predicate"] == "PREVENTS" and _concept(e["target"]):
            a = _card_of(e["source"])
            for pe in produced.get(e["target"], []):
                b = _card_of(pe["source"])
                if a and b and a != b:
                    yield ("PREVENTS_OPERATION", a, b, [_step(e, "forward"), _step(pe, "reverse")])


RELATIONS = [rel_infrastructure_casting, rel_contributes_to_gate, rel_supplies_resource,
             rel_enables_trigger, rel_prevents_operation]
_INFRASTRUCTURE = {"INFRASTRUCTURE_CASTING"}


# --------------------------------------------------------------------------- #
#  Assembly: group into metaedges keeping ALTERNATIVE paths as disjuncts       #
# --------------------------------------------------------------------------- #
def _dedup_prov(provs):
    seen, out = set(), []
    for p in provs:
        k = json.dumps(p, sort_keys=True, ensure_ascii=False)
        if k not in seen:
            seen.add(k)
            out.append(p)
    return sorted(out, key=lambda p: json.dumps(p, sort_keys=True, ensure_ascii=False))


def _alt_from_steps(steps: list, extra: dict) -> dict:
    nodes_seq = [steps[0]["source"]] + [s["target"] for s in steps]
    conds = sorted({c for s in steps for c in (s.get("condition_ids") or [])})
    optional = any(bool(s.get("optional")) for s in steps)
    polarity = "negative" if any(s.get("polarity") == "negative" for s in steps) else "positive"
    creates_for = next((s["creates_for"] for s in steps if s.get("creates_for")), None)
    scopes = [s["scope"] for s in steps if s.get("scope")]
    alt = {
        "signature": [[s["edge_id"], s["direction"]] for s in steps],
        "steps": steps,
        "primitive_path": nodes_seq,
        "path_predicates": [s["predicate"] for s in steps],
        "edge_ids": [s["edge_id"] for s in steps],
        "conditions": conds,
        "optional": optional,
        "polarity": polarity,
        "creates_for": creates_for,
        "scope": scopes or None,
        "min_path_length": len(steps),
        "involves_gate": any(n.startswith("gate:") for n in nodes_seq),
        "involves_state": any(n.startswith("state:") for n in nodes_seq),
        "provenance": _dedup_prov([p for s in steps for p in s.get("provenance", [])]),
    }
    alt.update(extra)                                 # participant/role annotations, if any
    return alt


def _assemble(instances) -> list[dict]:
    grouped = defaultdict(list)
    for inst in instances:
        relation, a, b, steps = inst[:4]
        extra = inst[4] if len(inst) > 4 else {}
        grouped[(a, b, relation)].append(_alt_from_steps(steps, extra))
    out = []
    for (a, b, relation), alts in grouped.items():
        uniq = {}
        for alt in alts:                              # collapse only IDENTICAL signatures
            uniq.setdefault(json.dumps(alt["signature"], sort_keys=True), alt)
        alts = sorted(uniq.values(), key=lambda x: (x["min_path_length"], x["edge_ids"]))
        # a metaedge is asserted if at least one alternative is asserted (relations
        # other than SUPPLIES_RESOURCE assert unconditionally).
        asserted = any(x.get("asserted", True) for x in alts)
        out.append({
            "source_card": a, "target_card": b, "relation": relation,
            "self_pair": a == b,
            "n_alternatives": len(alts),
            "min_path_length": min(x["min_path_length"] for x in alts),
            "infrastructure_only": relation in _INFRASTRUCTURE,
            "asserted": asserted,
            "participant_status": "resolved" if asserted else "participant_unresolved",
            "any_optional": any(x["optional"] for x in alts),
            "involves_gate": any(x["involves_gate"] for x in alts),
            "involves_state": any(x["involves_state"] for x in alts),
            "alternative_paths": alts,
            "provenance": _dedup_prov([p for x in alts for p in x["provenance"]]),
        })
    return out


def project(repo: Path = REPO) -> dict:
    g = Graph(repo)
    metaedges = _assemble(inst for fn in RELATIONS for inst in fn(g))
    metaedges.sort(key=lambda m: (m["source_card"], m["target_card"], m["relation"]))

    out = repo / "data" / "graph_global"
    with (out / "card_pair_projection.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for m in metaedges:
            fh.write(json.dumps(m, ensure_ascii=False, sort_keys=True) + "\n")

    by_rel = Counter(m["relation"] for m in metaedges)
    stats = {
        "metaedges": len(metaedges),
        "distinct_ordered_pairs": len({(m["source_card"], m["target_card"]) for m in metaedges}),
        "total_alternative_paths": sum(m["n_alternatives"] for m in metaedges),
        "self_pairs": sum(1 for m in metaedges if m["self_pair"]),
        "by_relation": dict(by_rel),
        "infrastructure_metaedges": sum(1 for m in metaedges if m["infrastructure_only"]),
        "involves_gate": sum(1 for m in metaedges if m["involves_gate"]),
        "cards": len(g.cards),
        "possible_ordered_pairs": len(g.cards) ** 2,
    }
    _report(repo, stats)
    return stats


def _report(repo: Path, stats: dict) -> None:
    L = ["# HOB Phase 5 — Card-Pair Projection (v2, mechanical)", "",
         f"- **cards**: {stats['cards']}  (possible ordered pairs: {stats['possible_ordered_pairs']})",
         f"- **projected metaedges**: {stats['metaedges']} "
         f"(over {stats['distinct_ordered_pairs']} ordered pairs; {stats['total_alternative_paths']} alternative paths)",
         f"- **infrastructure metaedges**: {stats['infrastructure_metaedges']}",
         f"- **metaedges involving a gate**: {stats['involves_gate']}",
         f"- **self-pairs**: {stats['self_pairs']}", "",
         "## By relation", ""]
    for k, v in sorted(stats["by_relation"].items(), key=lambda x: -x[1]):
        L.append(f"- {k}: {v}")
    L += ["", "Derived by bounded traversal of the frozen primitive graph. Mana contribution is",
          "colour-compatible; alternative mechanisms are kept as disjuncts; every step is a real",
          "Phase 4 edge (forward/reverse) or a labelled derived bridge. Pairs with no allowed",
          "functional path emit nothing (ontology-only sharing is excluded).", ""]
    (repo / "reports" / "pair_projection.md").write_text("\n".join(L) + "\n", encoding="utf-8")

"""Phase 5: derive card-pair projections by bounded traversal of the primitive graph.

We do NOT brute-force the 193x193 = 37,249 ordered pairs. Instead, for each named
relation we traverse the frozen Phase 4 primitive graph
(`data/graph_global/{nodes,edges}.jsonl`) along an allowed path grammar that joins
two cards through a *functional* concept node (a produced resource, a fired event,
a count-gate, a prevented operation) — never through a mere shared ontology class
(`obj:type:*`, `obj:supertype:*`), which the spec excludes as meaningless.

Each emitted metaedge records: ordered source/target cards, the derived relation,
the complete primitive path (node ids + predicates + edge ids), combined
conditions, whether it is infrastructure-only, the minimum path length, whether it
involves a gate or persistent state, and its provenance closure. Pairs with no
allowed path simply produce nothing (no relation is manufactured).

Output: `data/graph_global/card_pair_projection.jsonl`, `reports/pair_projection.md`.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from .pipeline import REPO, _load_dicts

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

# concept-node id prefixes that are pure ontology/type membership — excluded as
# cross-card join points (sharing a creature type does not relate two cards).
_ONTOLOGY_PREFIXES = ("obj:type:", "obj:supertype:", "obj:subtype:")


def _card_of(nid: str) -> str | None:
    """The card that owns a face/ability/operation/cost node (by embedded uuid)."""
    m = _UUID.search(nid)
    return "card:" + m.group(0) if m else None


class Graph:
    def __init__(self, repo: Path):
        self.nodes = {n["id"]: n for n in _load_dicts(repo / "data/graph_global/nodes.jsonl")}
        self.edges = [e for e in _load_dicts(repo / "data/graph_global/edges.jsonl")]
        self.out = defaultdict(list)   # source -> list[edge]
        self.inc = defaultdict(list)   # target -> list[edge]
        for e in self.edges:
            self.out[e["source"]].append(e)
            self.inc[e["target"]].append(e)
        self.cards = [nid for nid, n in self.nodes.items() if n["type"] == "Card"]
        self.faces_of = defaultdict(list)
        for e in self.edges:
            if e["predicate"] == "HAS_FACE":
                self.faces_of[e["source"]].append(e["target"])

    def ntype(self, nid: str) -> str:
        return self.nodes.get(nid, {}).get("type", "Unknown")


class PathStep:
    __slots__ = ("edge", "forward")

    def __init__(self, edge, forward=True):
        self.edge, self.forward = edge, forward


def _metaedge(relation, src_card, tgt_card, chain: list[dict], *, infrastructure=False):
    """Build a projected metaedge record from an ordered list of primitive edges."""
    nodes_seq, preds, eids, conds, provs = [], [], [], [], []
    for e in chain:
        if not nodes_seq:
            nodes_seq.append(e["source"])
        nodes_seq.append(e["target"])
        preds.append(e["predicate"])
        eids.append(e["edge_id"])
        conds.extend(e.get("condition_ids") or [])
        provs.extend(e.get("provenance") or [])
    involves_gate = any(n.startswith("gate:") for n in nodes_seq)
    involves_state = any(n.startswith("state:") for n in nodes_seq)
    # deterministic provenance closure
    seen, prov_closure = set(), []
    for p in provs:
        key = json.dumps(p, sort_keys=True, ensure_ascii=False)
        if key not in seen:
            seen.add(key)
            prov_closure.append(p)
    return {
        "source_card": src_card, "target_card": tgt_card, "relation": relation,
        "primitive_path": nodes_seq, "path_predicates": preds, "edge_ids": eids,
        "combined_conditions": sorted(set(conds)),
        "infrastructure_only": infrastructure,
        "min_path_length": len(preds),
        "involves_gate": involves_gate, "involves_state": involves_state,
        "self_pair": src_card == tgt_card,
        "provenance": sorted(prov_closure, key=lambda p: json.dumps(p, sort_keys=True, ensure_ascii=False)),
    }


# --------------------------------------------------------------------------- #
#  Relation derivations                                                        #
# --------------------------------------------------------------------------- #
def rel_infrastructure_casting(g: Graph) -> list[dict]:
    """A produces controller mana; B has a casting cost that needs mana.
    Card -> ... -> PRODUCES resource:mana  ⋈  HAS_COST cost:B:cast(needs mana) <- B."""
    out = []
    # controller mana producers: card -> a representative mana chain
    producers = {}
    for e in g.edges:
        if e["predicate"] == "PRODUCES" and e["target"].startswith("resource:mana"):
            # only controller-available mana (a face's own op); skip opponent-token mana
            if e["source"].startswith("op:token:"):
                continue
            card = _card_of(e["source"])
            if card and card not in producers:
                producers[card] = e
    # castable cards: a casting cost node that requires mana
    castable = {}
    for e in g.edges:
        if e["predicate"] == "HAS_COST" and e["target"].endswith(":cast"):
            cost = g.nodes.get(e["target"], {})
            mc = cost.get("data", {}).get("mana_cost") or {}
            if mc.get("generic") or mc.get("pips") or mc.get("has_variable"):
                card = _card_of(e["source"])
                if card:
                    castable[card] = e
    for a, pe in producers.items():
        for b, ce in castable.items():
            # bridge: the produced mana resource satisfies the casting cost
            bridge = {"source": pe["target"], "predicate": "SATISFIES", "target": ce["target"],
                      "edge_id": "derived", "provenance": [{"source": "phase5_projection",
                      "derivation": "mana_satisfies_casting_cost"}]}
            chain = [pe, bridge, {"source": ce["target"], "predicate": "HAS_COST_OF",
                                  "target": ce["source"], "edge_id": ce["edge_id"],
                                  "provenance": ce.get("provenance", [])}]
            out.append(_metaedge("INFRASTRUCTURE_CASTING", a, b, chain, infrastructure=True))
    return out


def rel_contributes_to_gate(g: Graph) -> list[dict]:
    """A is a permanent a count-gate counts (it QUALIFIES_FOR the gate); the gate's
    output (a persistent state) ENABLES B's payoff ability.  So A helps switch on B.
    A -QUALIFIES_FOR-> gate -PRODUCES-> state -ENABLES-> abilityB -> B
    (or the shorter A -QUALIFIES_FOR-> gate -ENABLES-> abilityB -> B)."""
    out = []
    # gate -> [(beneficiary card, tail edges from gate to the enabled ability)]
    beneficiaries = defaultdict(list)
    for e in g.edges:
        if not e["source"].startswith("gate:"):
            continue
        if e["predicate"] == "ENABLES":
            b = _card_of(e["target"])
            if b:
                beneficiaries[e["source"]].append((b, [e]))
        elif e["predicate"] == "PRODUCES" and e["target"].startswith("state:"):
            for e2 in g.out[e["target"]]:
                if e2["predicate"] == "ENABLES":
                    b = _card_of(e2["target"])
                    if b:
                        beneficiaries[e["source"]].append((b, [e, e2]))
    for e in g.edges:
        if e["predicate"] in ("QUALIFIES_FOR", "CONTRIBUTES_TO") and e["target"].startswith("gate:"):
            a = _card_of(e["source"])
            if not a:
                continue
            for (b, tail) in beneficiaries.get(e["target"], []):
                out.append(_metaedge("CONTRIBUTES_TO_GATE", a, b, [e] + tail))
    return out


def _resource_flow(g: Graph, relation: str, produce_preds: set, consume_preds: set,
                   target_pred_filter=None) -> list[dict]:
    """Generic A-produces-X / B-consumes-X join over a shared functional concept node."""
    out = []
    producers = defaultdict(list)  # concept -> [(card, edge)]
    consumers = defaultdict(list)
    for e in g.edges:
        t = e["target"]
        if t.startswith(_ONTOLOGY_PREFIXES):
            continue
        if e["predicate"] in produce_preds and _concept(t):
            c = _card_of(e["source"])
            if c:
                producers[t].append((c, e))
        if e["predicate"] in consume_preds and _concept(t):
            c = _card_of(e["source"])
            if c:
                consumers[t].append((c, e))
    for concept, prod in producers.items():
        cons = consumers.get(concept, [])
        for (a, pe) in prod:
            for (b, ce) in cons:
                back = {"source": concept, "predicate": "USED_BY", "target": ce["source"],
                        "edge_id": ce["edge_id"], "provenance": ce.get("provenance", [])}
                out.append(_metaedge(relation, a, b, [pe, back]))
    return out


def _concept(nid: str) -> bool:
    return nid.startswith(("resource:", "event:", "state:", "counter:", "token:", "gate:", "zone:"))


def rel_enables_trigger(g: Graph) -> list[dict]:
    """A produces/causes event E; E triggers B's ability.  A -> op -> E -TRIGGERS-> abilityB."""
    out = []
    produced = defaultdict(list)
    for e in g.edges:
        if e["predicate"] in ("PRODUCES", "CAUSES", "CREATES_OBJECT", "MOVES_TO") and e["target"].startswith("event:"):
            c = _card_of(e["source"])
            if c:
                produced[e["target"]].append((c, e))
    for e in g.edges:
        if e["predicate"] == "TRIGGERS":
            b = _card_of(e["target"])
            for (a, pe) in produced.get(e["source"], []):
                if b:
                    out.append(_metaedge("ENABLES_TRIGGER", a, b, [pe, e]))
    return out


def rel_prevents_operation(g: Graph) -> list[dict]:
    """A prevents an event/operation that B produces/causes.  A -> op -PREVENTS-> E <- B."""
    out = []
    produced = defaultdict(list)
    for e in g.edges:
        if e["predicate"] in ("PRODUCES", "CAUSES", "CREATES_OBJECT") and _concept(e["target"]):
            c = _card_of(e["source"])
            if c:
                produced[e["target"]].append((c, e))
    for e in g.edges:
        if e["predicate"] == "PREVENTS" and _concept(e["target"]):
            a = _card_of(e["source"])
            for (b, be) in produced.get(e["target"], []):
                if a and a != b:
                    back = {"source": e["target"], "predicate": "PRODUCED_BY", "target": be["source"],
                            "edge_id": be["edge_id"], "provenance": be.get("provenance", [])}
                    out.append(_metaedge("PREVENTS_OPERATION", a, b, [e, back]))
    return out


RELATIONS = [
    rel_infrastructure_casting,
    rel_contributes_to_gate,
    rel_enables_trigger,
    rel_prevents_operation,
    lambda g: _resource_flow(g, "SUPPLIES_RESOURCE", {"PRODUCES"}, {"CONSUMES", "REQUIRES"}),
]


def _dedup(metaedges: list[dict]) -> list[dict]:
    """One record per (source, target, relation): keep the shortest path, union the
    conditions/provenance/edge_ids so no citation is lost."""
    best: dict[tuple, dict] = {}
    for m in metaedges:
        k = (m["source_card"], m["target_card"], m["relation"])
        cur = best.get(k)
        if cur is None or m["min_path_length"] < cur["min_path_length"]:
            if cur:
                m["combined_conditions"] = sorted(set(m["combined_conditions"]) | set(cur["combined_conditions"]))
            best[k] = m
        else:
            cur["combined_conditions"] = sorted(set(cur["combined_conditions"]) | set(m["combined_conditions"]))
    return list(best.values())


def project(repo: Path = REPO) -> dict:
    g = Graph(repo)
    raw = []
    for fn in RELATIONS:
        raw.extend(fn(g))
    metaedges = _dedup(raw)
    metaedges.sort(key=lambda m: (m["source_card"], m["target_card"], m["relation"]))

    out = repo / "data" / "graph_global"
    with (out / "card_pair_projection.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for m in metaedges:
            fh.write(json.dumps(m, ensure_ascii=False, sort_keys=True) + "\n")

    by_rel = Counter(m["relation"] for m in metaedges)
    pairs = {(m["source_card"], m["target_card"]) for m in metaedges}
    stats = {
        "metaedges": len(metaedges),
        "distinct_ordered_pairs": len(pairs),
        "self_pairs": sum(1 for m in metaedges if m["self_pair"]),
        "by_relation": dict(by_rel),
        "infrastructure_only": sum(1 for m in metaedges if m["infrastructure_only"]),
        "involves_gate": sum(1 for m in metaedges if m["involves_gate"]),
        "cards": len(g.cards),
        "possible_ordered_pairs": len(g.cards) ** 2,
    }
    _report(repo, stats)
    return stats


def _report(repo: Path, stats: dict) -> None:
    L = ["# HOB Phase 5 — Card-Pair Projection (v1, mechanical)", "",
         f"- **cards**: {stats['cards']}  (possible ordered pairs: {stats['possible_ordered_pairs']})",
         f"- **projected metaedges**: {stats['metaedges']}",
         f"- **distinct ordered pairs with >=1 relation**: {stats['distinct_ordered_pairs']}",
         f"- **infrastructure-only metaedges**: {stats['infrastructure_only']}",
         f"- **metaedges involving a gate**: {stats['involves_gate']}",
         f"- **self-pairs**: {stats['self_pairs']}", "",
         "## By relation", ""]
    for k, v in sorted(stats["by_relation"].items(), key=lambda x: -x[1]):
        L.append(f"- {k}: {v}")
    L += ["", "Derived by bounded traversal of the frozen primitive graph; pairs with no",
          "allowed functional path emit nothing (ontology-only sharing is excluded).", ""]
    (repo / "reports" / "pair_projection.md").write_text("\n".join(L) + "\n", encoding="utf-8")

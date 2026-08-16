"""Phase 6: higher-order mechanism assembly.

Discover higher-order structures by grouping primitive edges around shared structural
ANCHORS (gates, rules, resources, states, tokens) — not by enumerating triples. Each
module is a formal, labelled SUBGRAPH of the frozen graph, with:

  - anchors        : the node(s) the module is organized around;
  - members        : the cards that participate;
  - contributors   : upstream edges feeding the anchor (who supplies it);
  - consumers      : downstream edges the anchor feeds (who benefits);
  - conditions     : condition_ids carried by the module's edges;
  - feedback_cycles: directed cycles passing through an anchor.

Labels (Recruit, Storied, Hone/Equipment, Amass, Ferocious, Landfall, graveyard reuse,
token production, second-draw triggers, and per-gate modules) INDEX formal subgraphs;
they are not subjective archetypes. Output: `data/graph_global/mechanism_modules.jsonl`.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path

from .pipeline import REPO, _load_dicts

_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _card_of(nid: str) -> str | None:
    m = _UUID.search(nid)
    return "card:" + m.group(0) if m else None


def _load_optional(path: Path):
    return list(_load_dicts(path)) if path.exists() else []


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:50] or "x"


def _ledge(src: str, pred: str, tgt: str, derivation: str) -> dict:
    """A deterministic, unique-id legend-layer edge with provenance."""
    eid = "legend:" + hashlib.sha1(f"{src}|{pred}|{tgt}".encode()).hexdigest()[:12]
    return {"edge_id": eid, "source": src, "predicate": pred, "target": tgt,
            "provenance": [{"source": "comprehensive_rules", "rule": "704.5j", "derivation": derivation}],
            "origin": "legend_rule"}


def materialize_legend(repo: Path) -> dict:
    """Model the legend rule (CR 704.5j) as its actual STATE-BASED ACTION — not a subjective
    negative-synergy edge, and not the coarse "a second copy cannot exist" approximation. Per
    the rule, a second same-name legendary permanent DOES enter; then a state-based action makes
    the controller choose one and put the rest into their owners' graveyards:

        legendary face --HAS_STATE--> state:legend-conflict:{name}
            (controller-scoped: one player controls >=2 legendary permanents with this name)
        state:legend-conflict:{name} --ENABLES--> ability:legend-sba
            (ENABLES, not TRIGGERS: an SBA is checked continuously, it is not an event-fired
             triggered ability, so the Event->Ability TRIGGERS signature would misrepresent it)
        ability:legend-sba --CAUSES--> op:legend-sba-put-in-graveyard
            (controller keeps one; the rest are put into their OWNERS' graveyards)
        op:legend-sba-put-in-graveyard --MOVES_TO--> zone:graveyard

    Same-name legends share the per-name conflict state (that shared node IS the conflict). The
    SBA ability, move operation, and rule node are canonical (one legend rule for the whole set).
    Additive layer; the frozen Phase 4 graph is untouched. All edges are predicate-signature
    valid against `assemble.GLOBAL_SIGNATURES`."""
    # name the conflict by the PERMANENT FACE's name (what the legend rule compares on the
    # battlefield), not the combined Adventure card name — 12 legendary Adventures otherwise get
    # a wrong "Front // Adventure" conflict name (e.g. "Beorn, Reluctant Host // Till and Tend").
    face_names = {f["id"]: f["name"] for f in _load_dicts(repo / "data/normalized/faces.jsonl")}
    edges = list(_load_dicts(repo / "data/graph_global/edges.jsonl"))
    legendary_faces = sorted({e["source"] for e in edges
                              if e["predicate"] == "HAS_TYPE" and e["target"] == "obj:supertype:legendary"})
    lnodes, ledges = {}, []

    # canonical, shared SBA machinery (one legend rule, CR 704.5j, for the whole set)
    rule, sba, move = "rule:legend", "ability:legend-sba", "op:legend-sba-put-in-graveyard"
    _CR_TEXT = ("If two or more legendary permanents with the same name are controlled by the "
                "same player, that player chooses one of them, and the rest are put into their "
                "owners' graveyards.")
    lnodes[rule] = {"id": rule, "type": "Rule", "label": "legend rule (CR 704.5j)",
                    "data": {"rule": "legend", "cr": "704.5j", "text": _CR_TEXT},
                    "provenance": [{"source": "comprehensive_rules", "rule": "704.5j"}],
                    "origin": "legend_rule"}
    lnodes[sba] = {"id": sba, "type": "Ability", "label": "legend-rule state-based action",
                   "data": {"kind": "state_based_action", "rule": "legend", "cr": "704.5j",
                            "scope": "controller",
                            "effect": "controller keeps one; the rest go to their owners' graveyards"},
                   "provenance": [{"source": "comprehensive_rules", "rule": "704.5j"}],
                   "origin": "legend_rule"}
    lnodes[move] = {"id": move, "type": "Operation",
                    "label": "put excess same-name legendary permanents into graveyard",
                    "data": {"operation": "put_into_graveyard", "chooser": "controller",
                             "destination_scope": "owner", "quantity": "all but one"},
                    "provenance": [{"source": "comprehensive_rules", "rule": "704.5j"}],
                    "origin": "legend_rule"}
    ledges.append(_ledge(sba, "REFERENCES_RULE", rule, "SBA implements the legend rule"))
    ledges.append(_ledge(sba, "CAUSES", move, "SBA puts the excess permanents into graveyards"))
    ledges.append(_ledge(move, "MOVES_TO", "zone:graveyard", "excess legends go to owners' graveyards"))

    for face in legendary_faces:
        name = face_names.get(face) or _card_of(face) or face
        state = f"state:legend-conflict:{_slug(name)}"
        if state not in lnodes:                          # same-name legends share the conflict state
            lnodes[state] = {"id": state, "type": "State", "label": f"legend-rule conflict: {name}",
                             "data": {"rule": "legend", "cr": "704.5j", "by_name": name,
                                      "scope": "controller", "conflict_threshold": 2,
                                      "resolution": "state_based_action",
                                      "transition": (f"one player controls >=2 legendary permanents named "
                                                     f"'{name}'; controller keeps one, the rest are put "
                                                     "into their owners' graveyards")},
                             "provenance": [{"source": "legend_rule", "derivation": "supertype:legendary"}],
                             "origin": "legend_rule"}
            ledges.append(_ledge(state, "ENABLES", sba, "the name-conflict condition triggers the SBA"))
        ledges.append(_ledge(face, "HAS_STATE", state, "legendary permanent is subject to the legend rule"))
    G = repo / "data" / "graph_global"
    with (G / "legend_nodes.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for n in sorted(lnodes.values(), key=lambda n: n["id"]):
            fh.write(json.dumps(n, ensure_ascii=False, sort_keys=True) + "\n")
    with (G / "legend_edges.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for e in sorted(ledges, key=lambda e: (e["source"], e["predicate"], e["target"])):
            fh.write(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n")
    return {"legend_nodes": len(lnodes), "legend_edges": len(ledges),
            "legend_conflict_states": sum(1 for n in lnodes.values() if n["id"].startswith("state:legend-conflict:"))}


class _Graph:
    def __init__(self, repo: Path):
        # union the frozen Phase 4 graph with the (additive) graph-repair layer, keeping
        # each node/edge's origin so repaired structures participate in modules too.
        self.nodes = {n["id"]: n for n in _load_dicts(repo / "data/graph_global/nodes.jsonl")}
        for layer in ("repair_nodes.jsonl", "legend_nodes.jsonl"):
            for n in _load_optional(repo / "data/graph_global" / layer):
                self.nodes.setdefault(n["id"], n)
        self.edges = []
        for e in _load_dicts(repo / "data/graph_global/edges.jsonl"):
            e.setdefault("origin", "phase4")
            self.edges.append(e)
        for layer, origin in (("repair_edges.jsonl", "graph_repair"), ("legend_edges.jsonl", "legend_rule")):
            for e in _load_optional(repo / "data/graph_global" / layer):
                e.setdefault("origin", origin)
                self.edges.append(e)
        self.out = defaultdict(list)
        self.inc = defaultdict(list)
        for e in self.edges:
            self.out[e["source"]].append(e)
            self.inc[e["target"]].append(e)
        self.mech = defaultdict(set)     # mechanic -> {face_id}
        self.mech_card = defaultdict(set)
        for m in _load_dicts(repo / "data/rules/mechanics.jsonl"):
            self.mech[m["mechanic"]].add(m["face_id"])
            self.mech_card[m["mechanic"]].add(m["card_id"])
        self.names = {c["id"]: c["name"] for c in _load_dicts(repo / "data/normalized/cards.jsonl")}

    def upstream_cards(self, anchor: str, max_depth: int = 5) -> set:
        """Cards reachable UPSTREAM of an anchor by walking reverse edges through
        structural nodes (gates/rules/ops/states), recovering participants even when the
        immediate producer is a card-less gate (e.g. gate:recruit-nonland-discard → soldier)."""
        cards, seen, frontier = set(), {anchor}, [(anchor, 0)]
        while frontier:
            node, d = frontier.pop()
            if d > max_depth:
                continue
            for e in self.inc.get(node, []):
                src = e["source"]
                c = _card_of(src)
                if c:
                    cards.add(c)
                if src not in seen:
                    seen.add(src)
                    frontier.append((src, d + 1))
            # gates/rules are also reached FROM cards via forward refs (card -> rule/gate)
            if node.startswith(("rule:", "gate:")):
                for e in self.out.get(node, []):
                    c = _card_of(e["target"])
                    if c:
                        cards.add(c)
        return cards

    def cards_with_mechanic(self, *mechanics) -> set:
        out = set()
        for m in mechanics:
            out |= self.mech_card.get(m, set())
        return out

    def cycles_through(self, anchor: str, max_depth: int = 6) -> list:
        """Directed cycles anchor -> … -> anchor over functional edges (bounded)."""
        cycles, seen = [], set()

        def dfs(node, path):
            if len(path) > max_depth:
                return
            for e in self.out.get(node, []):
                t = e["target"]
                if t == anchor:                            # cycle back (incl. length-1 self-loop)
                    key = tuple(sorted(set(path + [t])))
                    if key not in seen:
                        seen.add(key)
                        cycles.append(path + [t])
                elif t not in path and t.startswith(("state:", "op:", "gate:", "resource:",
                                                     "token:", "counter:", "event:", "obj:army")):
                    dfs(t, path + [t])

        dfs(anchor, [anchor])
        return cycles[:8]


def _provenance_edges(g: _Graph, op_node: str, depth: int = 3):
    """The causal path from an operation up to its card/ability: op <-CAUSES- ability
    <-HAS_ABILITY- face (and reified op <-HAS_ABILITY- face). Yields edge_ids so a module
    subgraph is expandable back to the printed ability, not just anchor-local."""
    ids, frontier, seen = set(), [(op_node, 0)], {op_node}
    while frontier:
        node, d = frontier.pop()
        if d >= depth:
            continue
        for e in g.inc.get(node, []):
            if e["predicate"] in ("CAUSES", "HAS_ABILITY"):
                ids.add(e["edge_id"])
                if e["source"] not in seen:
                    seen.add(e["source"])
                    frontier.append((e["source"], d + 1))
    return ids


def _resolution_edges(g: _Graph, starts: set, depth: int = 4):
    """Downstream RESOLUTION chain from the module's machinery: starting at any reached
    Ability/Operation node, follow its outgoing edges, continuing THROUGH Ability/Operation
    nodes. This makes a module expandable through the mechanism it represents — e.g. the legend
    SBA `state ENABLES ability CAUSES op MOVES_TO graveyard` includes the CAUSES/MOVES_TO/
    REFERENCES_RULE edges, not just HAS_STATE/ENABLES. Added to subgraph edges only (members,
    contributors, consumers are unchanged, so no card is pulled in as a member)."""
    ids, seen, frontier = set(), set(), []
    for s in starts:
        if g.nodes.get(s, {}).get("type") in ("Ability", "Operation"):
            seen.add(s)
            frontier.append((s, 0))
    while frontier:
        node, d = frontier.pop()
        if d >= depth:
            continue
        for e in g.out.get(node, []):
            ids.add(e["edge_id"])
            t = e["target"]
            if t not in seen and g.nodes.get(t, {}).get("type") in ("Ability", "Operation"):
                seen.add(t)
                frontier.append((t, d + 1))
    return ids


def _module(g: _Graph, module_id: str, label: str, kind: str, anchors: list, members: set) -> dict:
    anchors = [a for a in anchors if a in g.nodes]
    anchorset = set(anchors)
    contributors, consumers, sub_edges, conditions = [], [], set(), set()

    def note(e):
        sub_edges.add(e["edge_id"])
        for c in e.get("condition_ids", []) or []:
            conditions.add(c)
        # include the causal provenance path from any operation endpoint up to its ability/face
        for endpoint in (e["source"], e["target"]):
            if endpoint.startswith("op:") and _card_of(endpoint):
                sub_edges.update(_provenance_edges(g, endpoint))

    for a in anchors:
        for e in g.inc.get(a, []):                    # upstream: edges feeding the anchor
            contributors.append({"card": _card_of(e["source"]), "edge_id": e["edge_id"],
                                 "predicate": e["predicate"], "source": e["source"], "into": a})
            note(e)
        for e in g.out.get(a, []):                    # downstream: edges the anchor feeds
            consumers.append({"card": _card_of(e["target"]), "edge_id": e["edge_id"],
                              "predicate": e["predicate"], "target": e["target"], "from": a})
            note(e)
            # gate -> state -> ENABLES ability : follow one more hop to the true consumer
            if e["predicate"] == "PRODUCES" and e["target"].startswith("state:"):
                for e2 in g.out.get(e["target"], []):
                    if e2["predicate"] == "ENABLES":
                        consumers.append({"card": _card_of(e2["target"]), "edge_id": e2["edge_id"],
                                          "predicate": "ENABLES", "target": e2["target"], "from": e["target"]})
                        note(e2)

    # include the downstream resolution chain (e.g. legend SBA ability CAUSES op MOVES_TO
    # graveyard) so the module is expandable through the mechanism it claims to represent
    sub_edges |= _resolution_edges(g, {c.get("target") for c in consumers if c.get("target")})

    members = set(members) | {c["card"] for c in contributors if c["card"]} | \
              {c["card"] for c in consumers if c["card"]}
    feedback = [c for a in anchors for c in g.cycles_through(a)]
    return {
        "module_id": module_id, "label": label, "kind": kind,
        "anchors": anchors, "members": sorted(members),
        "contributors": sorted(contributors, key=lambda x: (x["source"], x["predicate"])),
        "consumers": sorted(consumers, key=lambda x: (str(x["target"]), x["predicate"])),
        "conditions": sorted(conditions),
        "feedback_cycles": feedback,
        "subgraph_edge_ids": sorted(sub_edges),
        "stats": {"members": len(members), "contributors": len(contributors),
                  "consumers": len(consumers), "conditions": len(conditions),
                  "feedback_cycles": len(feedback)},
    }


def build_modules(repo: Path = REPO) -> dict:
    materialize_legend(repo)                              # (re)materialize the legend-rule layer
    g = _Graph(repo)
    mods = []

    # --- legend rule as an explicit state-based-action transition (not subjective synergy) ---
    legend_states = sorted(n for n in g.nodes if n.startswith("state:legend-conflict:"))
    if legend_states:
        mods.append(_module(g, "module:legend-rule", "legend rule (state-based action)",
                            "state_constraint", legend_states, set()))

    # --- per-gate modules (the spec's mechanism_modules) ---
    for gate in sorted(n for n in g.nodes if n.startswith("gate:")):
        mods.append(_module(g, f"module:{gate}", gate, "gate", [gate], set()))

    # --- named mechanic modules (labels index formal subgraphs) ---
    named = [
        ("Recruit", "recruit", ["rule:recruit", "gate:recruit-nonland-discard"], ("Recruit",)),
        ("Storied", "storied", ["gate:storied", "state:enduring_story", "rule:storied"], ("Storied",)),
        ("Hone/Equipment", "hone_equipment", ["counter:hone", "rule:hone", "rule:equip", "keyword:equip"],
         ("Hone", "Equip")),
        ("Amass", "amass", ["rule:amass", "op:amass", "obj:army-A", "gate:amass-no-army"], ("Amass",)),
        ("Ferocious", "ferocious", ["rule:ferocious", "keyword:ferocious"], ("Ferocious",)),
        ("Landfall", "landfall", ["rule:landfall", "keyword:landfall"], ("Landfall",)),
        ("Saga", "saga", ["rule:saga", "counter:lore"], ("Saga",)),
    ]
    for label, kind, anchors, mechs in named:
        mods.append(_module(g, f"module:{kind}", label, kind, anchors, g.cards_with_mechanic(*mechs)))

    # --- graveyard reuse: cards that MOVE cards FROM the graveyard ---
    gy_members = {_card_of(e["source"]) for e in g.edges
                  if e["predicate"] == "MOVES_FROM" and e["target"] == "zone:graveyard"} - {None}
    mods.append(_module(g, "module:graveyard-reuse", "graveyard reuse", "zone_flow",
                        ["zone:graveyard"], gy_members))

    # --- token production: a module for EVERY created token, recovering members by
    # upstream traversal so gate-mediated creators (e.g. Recruit -> token:human-soldier
    # via gate:recruit-nonland-discard) are included. ---
    created_tokens = sorted({e["target"] for e in g.edges
                             if e["predicate"] == "CREATES_OBJECT" and e["target"].startswith("token:")})
    for tok in created_tokens:
        mods.append(_module(g, f"module:token:{tok.split(':')[-1]}", f"token production ({tok})",
                            "token_production", [tok], g.upstream_cards(tok)))

    # --- second-draw triggers: abilities that trigger on a draw event, flagged where a
    # "second"/"two or more" draw condition is present (the Master's-Councillors pattern) ---
    condmap = {c["condition_id"]: c.get("human_readable", "")
               for c in _load_dicts(repo / "data/graph_global/conditions.jsonl")}
    draw_triggered, second = set(), set()
    for e in g.edges:
        if e["predicate"] == "TRIGGERS" and "draw" in e["source"]:
            c = _card_of(e["target"])
            if c:
                draw_triggered.add(c)
            txt = " ".join(condmap.get(x, "") for x in (e.get("condition_ids") or [])).lower()
            if c and ("second" in txt or "two or more" in txt or "drawn two" in txt):
                second.add(c)
    mods.append(_module(g, "module:second-draw", "second-draw triggers", "trigger",
                        [n for n in g.nodes if n.startswith("event:") and "draw" in n],
                        second or draw_triggered))

    # --- generalized anchor discovery: any shared functional concept node that has BOTH a
    # producer side and a consumer side and touches >=2 distinct cards is a structural hub.
    # Recognized anchors get a curated label; the rest are labelled by their node kind. ---
    _LABELS = {
        "event:draw": "draw engine", "event:player-loses-life": "life-loss trigger",
        "event:counters-placed": "counter-placement trigger",
        "event:activate-creature-ability": "activated-ability trigger",
        "event:enters_the_battlefield": "ETB trigger", "event:this-creature-enters": "ETB trigger",
        "resource:mana": "mana base", "resource:card": "card advantage", "resource:life": "life swing",
        "zone:graveyard": "graveyard reuse", "counter:+1/+1": "+1/+1 counters",
        "state:enduring_story": "enduring story",
    }
    used = {a for m in mods for a in m["anchors"]}

    def prod_cons(nid):
        inc_c = {_card_of(e["source"]) for e in g.inc.get(nid, [])
                 if e["predicate"] in ("PRODUCES", "CAUSES", "CREATES_OBJECT", "ADDS_COUNTER",
                                       "MODIFIES", "REPLACES", "QUALIFIES_FOR", "CONTRIBUTES_TO")}
        out_c = {_card_of(e["target"]) for e in g.out.get(nid, [])
                 if e["predicate"] in ("TRIGGERS", "ENABLES", "COUNTS", "PRODUCES")}
        con_c = {_card_of(e["source"]) for e in g.inc.get(nid, [])
                 if e["predicate"] in ("CONSUMES", "REQUIRES", "SCALES_WITH", "HAS_TYPE")}
        return inc_c - {None}, (out_c | con_c) - {None}

    # object subtypes are functional anchors when an anthem MODIFIES them AND members carry
    # the type (tribal / anthem structures, e.g. Thranduil MODIFIES obj:subtype:elf).
    def _subtype_ok(nid):
        return (nid.startswith("obj:subtype:")
                and any(e["predicate"] == "MODIFIES" for e in g.inc.get(nid, []))
                and any(e["predicate"] == "HAS_TYPE" for e in g.inc.get(nid, [])))

    for nid in sorted(g.nodes):
        if nid in used:
            continue
        if not (nid.startswith(("resource:", "event:", "state:", "counter:")) or _subtype_ok(nid)):
            continue
        producers, consumers = prod_cons(nid)
        if len(producers | consumers) >= 2 and producers and consumers:
            label = _LABELS.get(nid, f"shared {nid.split(':')[0]}: {nid}")
            mods.append(_module(g, f"module:anchor:{nid}", label, f"discovered_{nid.split(':')[0]}",
                                [nid], producers | consumers))

    mods = [m for m in mods if m["members"] or m["contributors"] or m["consumers"]]
    mods.sort(key=lambda m: m["module_id"])
    with (repo / "data/graph_global/mechanism_modules.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for m in mods:
            fh.write(json.dumps(m, ensure_ascii=False, sort_keys=True) + "\n")
    stats = {"modules": len(mods), "by_kind": dict(_count(m["kind"] for m in mods)),
             "with_feedback_cycles": sum(1 for m in mods if m["feedback_cycles"])}
    _report(repo, g, mods, stats)
    return stats


def _count(it):
    from collections import Counter
    return Counter(it)


def _report(repo: Path, g: _Graph, mods: list, stats: dict) -> None:
    L = ["# HOB Phase 6 — Higher-Order Mechanism Modules", "",
         f"- **modules**: {stats['modules']}",
         f"- **modules with feedback cycles**: {stats['with_feedback_cycles']}",
         f"- **by kind**: {stats['by_kind']}", "", "## Modules", ""]
    for m in mods:
        L.append(f"### {m['label']}  (`{m['kind']}`)")
        L.append(f"- anchors: {', '.join('`' + a + '`' for a in m['anchors'])}")
        L.append(f"- members: {m['stats']['members']}  · contributors: {m['stats']['contributors']}  · "
                 f"consumers: {m['stats']['consumers']}  · conditions: {m['stats']['conditions']}  · "
                 f"feedback cycles: {m['stats']['feedback_cycles']}")
        if m["feedback_cycles"]:
            L.append(f"  - cycle: {' → '.join(m['feedback_cycles'][0])}")
        L.append("")
    (repo / "reports" / "mechanism_modules.md").write_text("\n".join(L) + "\n", encoding="utf-8")

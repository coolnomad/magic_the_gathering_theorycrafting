"""Phase 2: mechanic rule-template library.

Each HOB mechanic is encoded once as a reusable rule and instantiated on the
cards that carry it (detected in Phase 1). Templates emit typed, directed,
provenance-bearing graph fragments (nodes/edges/gates/conditions) with
extractor='rule_expansion'. No value judgments; no pair projection (Phase 5).

Canonical shared nodes (one Recruit rule, one Storied gate, one lore counter,
etc.) are created once; each instantiation's operations remain attributable to
their source face via id prefix.
"""

from __future__ import annotations

import re

from .models import Edge, Gate, Node, Provenance, StructuredCondition

# --- rule references (provenance anchors) -----------------------------------
RULE_REFS = {
    "recruit": "HOB release notes / mechanics article: Recruit",
    "storied": "HOB release notes / mechanics article: Storied",
    "hone": "CR 122.1j (hone counter)",
    "adventure": "CR 715 (Adventurer cards)",
    "saga": "CR 714 (Saga cards)",
}

_ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6}
_CHAPTER_RE = re.compile(r"(?m)^\s*([IVX]+)\s*(?:,\s*[IVX]+\s*)*—")


class GraphBuilder:
    """Accumulates nodes (deduped by id), edges, gates, and structured conditions."""

    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}
        self.edges: list[Edge] = []
        self.gates: dict[str, Gate] = {}
        self.conditions: dict[str, StructuredCondition] = {}
        self._edge_seq: dict[tuple[str, str, str], int] = {}

    def node(self, id: str, type: str, label: str, data: dict | None = None,
             provenance: list[Provenance] | None = None) -> str:
        if id not in self.nodes:
            self.nodes[id] = Node(id=id, type=type, label=label, data=data or {},
                                  provenance=provenance or [])
        return id

    def edge(self, source: str, target: str, predicate: str, *,
             timing: str | None = None, quantity: int | None = None,
             optional: bool = False, condition_ids: list[str] | None = None,
             provenance: list[Provenance] | None = None) -> Edge:
        key = (source, predicate, target)
        n = self._edge_seq.get(key, 0)
        self._edge_seq[key] = n + 1
        e = Edge(
            edge_id=f"e:{source}|{predicate}|{target}#{n}",
            source=source, target=target, predicate=predicate,
            timing=timing, quantity=quantity, optional=optional,
            condition_ids=condition_ids or [], provenance=provenance or [],
        )
        self.edges.append(e)
        return e

    def gate(self, g: Gate) -> str:
        # A gate is a reified graph node (so edges resolve) AND a rich Gate record.
        self.gates.setdefault(g.gate_id, g)
        self.node(g.gate_id, "Gate", g.label, {"gate_type": g.gate_type}, g.provenance)
        return g.gate_id

    def condition(self, c: StructuredCondition) -> str:
        self.conditions.setdefault(c.condition_id, c)
        return c.condition_id


# --- shared / canonical nodes ----------------------------------------------

ZONES = ["hand", "battlefield", "graveyard", "exile", "library", "stack"]


def _prov(card_id: str, face_id: str | None, rule_key: str, text: str | None = None,
          span: tuple[int, int] | None = None) -> Provenance:
    return Provenance(card_id=card_id, face_id=face_id,
                      source=f"rule.template:{rule_key}", text=text, span=span,
                      rule_ref=RULE_REFS[rule_key])


def add_shared_nodes(gb: GraphBuilder) -> None:
    for z in ZONES:
        gb.node(f"zone:{z}", "Zone", z)
    for key, ref in RULE_REFS.items():
        gb.node(f"rule:{key}", "Rule", key, {"rule_ref": ref})
    gb.node("counter:hone", "CounterType", "hone counter", {"rule_ref": RULE_REFS["hone"]})
    gb.node("counter:lore", "CounterType", "lore counter", {"rule_ref": RULE_REFS["saga"]})
    gb.node("event:card-drawn", "Event", "a card is drawn")
    gb.node("token:human-soldier", "TokenSpec",
            "1/1 white Human Soldier", {"colors": ["W"], "power": 1, "toughness": 1,
                                        "types": ["Creature"], "subtypes": ["Human", "Soldier"]})
    # Storied ObjectClass predicate members
    for oc, lbl in [("legendary", "Legendary permanent"), ("artifact", "Artifact"), ("saga", "Saga")]:
        gb.node(f"obj:{oc}", "ObjectClass", lbl)
    _storied_gate(gb)
    _recruit_gate(gb)


def _storied_gate(gb: GraphBuilder) -> None:
    gate = Gate(
        gate_id="gate:storied", gate_type="distinct_object_threshold",
        label="Storied distinct-count threshold",
        definition={
            "population": {"zone": "battlefield", "controller": "you",
                           "predicate": {"op": "or", "args": [
                               {"has_supertype": "Legendary"},
                               {"has_type": "Artifact"},
                               {"has_subtype": "Saga"}]}},
            "aggregation": "count_distinct_objects", "comparison": ">=", "threshold": 3,
            "output_state": "enduring_story", "output_persistence": "rest_of_game",
            "double_count_multiqualifying_object": False,
        },
        output_state="state:enduring_story",
        provenance=[Provenance(card_id="", source="rule.template:storied", rule_ref=RULE_REFS["storied"])],
    )
    gb.gate(gate)
    gb.node("state:enduring_story", "State", "enduring story",
            {"persistence": "rest_of_game", "on": "player", "removable": False})
    gb.edge("gate:storied", "state:enduring_story", "PRODUCES",
            provenance=[Provenance(card_id="", source="rule.template:storied", rule_ref=RULE_REFS["storied"])])
    gb.edge("state:enduring_story", "state:enduring_story", "PERSISTS_AS")
    for oc in ("legendary", "artifact", "saga"):
        gb.edge("gate:storied", f"obj:{oc}", "COUNTS")


def _recruit_gate(gb: GraphBuilder) -> None:
    gb.gate(Gate(
        gate_id="gate:recruit-nonland-discard", gate_type="branch_condition",
        label="Recruit: discarded card is nonland",
        definition={"predicate": {"op": "is_nonland", "arg": "the_discarded_card"}},
        provenance=[Provenance(card_id="", source="rule.template:recruit", rule_ref=RULE_REFS["recruit"])],
    ))
    gb.condition(StructuredCondition(
        condition_id="cond:recruit-nonland-discard",
        expression={"op": "is_nonland", "arg": "the_discarded_card"},
        human_readable="the discarded card is a nonland card",
        provenance=[Provenance(card_id="", source="rule.template:recruit", rule_ref=RULE_REFS["recruit"])],
    ))


# --- templates --------------------------------------------------------------

def _find_span(text: str | None, pat: str) -> tuple[int, int] | None:
    if not text:
        return None
    m = re.search(pat, text, re.I)
    return (m.start(), m.end()) if m else None


def expand_recruit(gb: GraphBuilder, face: dict) -> None:
    """draw -> discard -> (nonland gate) -> create 1/1 Human Soldier. (spec expand_recruit)"""
    fid, cid = face["id"], face["card_id"]
    span = _find_span(face.get("oracle_text"), r"\brecruit\b")
    p = [_prov(cid, fid, "recruit", "recruit", span)]
    gb.node(fid, "CardFace", face.get("name", fid))
    op = gb.node(f"op:{fid}:recruit", "Operation", "recruit", provenance=p)
    draw = gb.node(f"op:{fid}:recruit:draw", "Operation", "draw", {"quantity": 1}, p)
    disc = gb.node(f"op:{fid}:recruit:discard", "Operation", "discard",
                   {"quantity": 1, "choice": "controller"}, p)
    gb.edge(fid, op, "HAS_ABILITY", provenance=p)
    gb.edge(op, "rule:recruit", "REFERENCES_RULE", provenance=p)
    gb.edge(op, draw, "CAUSES", provenance=p)
    gb.edge(draw, "event:card-drawn", "PRODUCES", quantity=1, provenance=p)
    gb.edge(draw, disc, "CAUSES", timing="after", provenance=p)
    gb.edge(disc, "zone:graveyard", "MOVES_TO", provenance=p)
    gb.edge(disc, "gate:recruit-nonland-discard", "CAUSES", provenance=p)
    gb.edge("gate:recruit-nonland-discard", "token:human-soldier", "CREATES_OBJECT",
            quantity=1, condition_ids=["cond:recruit-nonland-discard"], provenance=p)


def expand_storied_payoff(gb: GraphBuilder, face: dict) -> None:
    """A card with a Storied payoff: enduring_story ENABLES its static/enabled effect."""
    fid, cid = face["id"], face["card_id"]
    span = _find_span(face.get("oracle_text"), r"\bstoried\b")
    p = [_prov(cid, fid, "storied", "storied", span)]
    gb.node(fid, "CardFace", face.get("name", fid))
    ab = gb.node(f"ab:{fid}:storied", "Ability", "storied payoff", provenance=p)
    gb.edge(fid, ab, "HAS_ABILITY", provenance=p)
    gb.edge(ab, "rule:storied", "REFERENCES_RULE", provenance=p)
    gb.edge("state:enduring_story", ab, "ENABLES", provenance=p)


def storied_contributor(gb: GraphBuilder, node_id: str, node_type: str, label: str,
                        provenance: list[Provenance]) -> None:
    """Emit exactly one CONTRIBUTES_TO edge for a qualifying object (invariant #5:
    a legendary artifact counts once)."""
    gb.node(node_id, node_type, label)
    # dedup: at most one contributor edge per object
    for e in gb.edges:
        if e.source == node_id and e.predicate == "CONTRIBUTES_TO" and e.target == "gate:storied":
            return
    gb.edge(node_id, "gate:storied", "CONTRIBUTES_TO", provenance=provenance)


def expand_hone(gb: GraphBuilder, face: dict) -> None:
    """hone counter on Equipment gives +1/+0 to the attached creature (not the source card)."""
    fid, cid = face["id"], face["card_id"]
    span = _find_span(face.get("oracle_text"), r"\bhone counter")
    p = [_prov(cid, fid, "hone", "hone counter", span)]
    gb.node(fid, "CardFace", face.get("name", fid))
    boost = gb.node("effect:hone-boost", "Effect", "+1/+0 to the equipped creature",
                    {"power": 1, "toughness": 0, "target": "attached_creature"})
    add = gb.node(f"op:{fid}:add-hone", "Operation", "put a hone counter", provenance=p)
    gb.edge(fid, add, "HAS_ABILITY", provenance=p)
    gb.edge(add, "counter:hone", "ADDS_COUNTER", provenance=p)
    gb.edge(add, "rule:hone", "REFERENCES_RULE", provenance=p)
    gb.edge(boost, "counter:hone", "SCALES_WITH", provenance=p)  # +1 power per hone counter
    gb.edge("counter:hone", boost, "PRODUCES", provenance=p)


def expand_adventure(gb: GraphBuilder, primary: dict, adventure: dict) -> None:
    """Adventure spell castable from hand; on resolution -> exile; enables casting the
    permanent face from exile; permanent may also be cast normally from hand. Faces stay distinct."""
    pid, aid, cid = primary["id"], adventure["id"], primary["card_id"]
    p = [_prov(cid, aid, "adventure", "Adventure")]
    gb.node(pid, "CardFace", primary.get("name", pid))
    gb.node(aid, "CardFace", adventure.get("name", aid))
    cast_adv = gb.node(f"op:{aid}:cast", "Operation", "cast adventure spell", provenance=p)
    resolve = gb.node(f"op:{aid}:resolve", "Operation", "adventure spell resolves", provenance=p)
    cast_exile = gb.node(f"op:{pid}:cast-from-exile", "Operation", "cast permanent from exile", provenance=p)
    cast_hand = gb.node(f"op:{pid}:cast-from-hand", "Operation", "cast permanent from hand", provenance=p)
    gb.edge(aid, cast_adv, "HAS_ABILITY", provenance=p)
    gb.edge(cast_adv, "zone:hand", "MOVES_FROM", provenance=p)
    gb.edge(cast_adv, resolve, "CAUSES", provenance=p)
    gb.edge(resolve, "zone:exile", "MOVES_TO", provenance=p)
    gb.edge("zone:exile", cast_exile, "ENABLES", provenance=p)
    gb.edge(cast_exile, "zone:exile", "MOVES_FROM", provenance=p)
    gb.edge(cast_hand, "zone:hand", "MOVES_FROM", optional=True, provenance=p)  # normal alternative
    gb.edge(cast_adv, "rule:adventure", "REFERENCES_RULE", provenance=p)


def expand_saga(gb: GraphBuilder, face: dict) -> None:
    """Lore counters (ETB + each turn), chapter triggers, sacrifice after final chapter."""
    fid, cid = face["id"], face["card_id"]
    p = [_prov(cid, fid, "saga", "Saga")]
    gb.node(fid, "CardFace", face.get("name", fid))
    etb = gb.node(f"op:{fid}:add-lore-etb", "Operation", "add a lore counter as it enters", provenance=p)
    turn = gb.node(f"op:{fid}:add-lore-turn", "Operation", "add a lore counter each turn",
                   {"timing": "first_main_phase"}, p)
    gb.edge(fid, etb, "HAS_ABILITY", provenance=p)
    gb.edge(fid, turn, "HAS_ABILITY", provenance=p)
    gb.edge(etb, "counter:lore", "ADDS_COUNTER", provenance=p)
    gb.edge(turn, "counter:lore", "ADDS_COUNTER", provenance=p)
    gb.edge(fid, "rule:saga", "REFERENCES_RULE", provenance=p)

    chapters = _CHAPTER_RE.findall(face.get("oracle_text") or "")
    values = sorted({_ROMAN.get(c, 0) for c in chapters if c in _ROMAN})
    for n in values:
        ab = gb.node(f"ab:{fid}:chapter-{n}", "Ability", f"chapter {n}", {"chapter": n}, p)
        gb.edge("counter:lore", ab, "ENABLES", condition_ids=[], provenance=p)
    if values:
        final = max(values)
        sac = gb.node(f"op:{fid}:sacrifice", "Operation", "sacrifice after final chapter",
                      {"after_chapter": final}, p)
        gb.edge(f"ab:{fid}:chapter-{final}", sac, "CAUSES", timing="after", provenance=p)
        gb.edge(sac, "zone:graveyard", "MOVES_TO", provenance=p)

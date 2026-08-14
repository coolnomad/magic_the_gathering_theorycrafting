"""Phase 2: mechanic rule-template library (object-identity-correct).

Each HOB mechanic is encoded once as a generic, reusable rule template. Card-
specific instantiations INVOKE the generic template (INSTANTIATES / REFERENCES_RULE)
rather than duplicating its output edges, and every object-bound fact (a card's
Adventure-exiled state, a Saga's lore-count, an Equipment's hone counters) is a
*per-object state node*, never a shared concept/type node. This preserves object
identity so Phase 5 pair traversal cannot manufacture false paths (see
docs/hob-kg-phase2-review.md). Capacity only; no value judgments; no pair projection.
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
    "amass": "HOB mechanics article: Amass (keyword action)",
    "typecycling": "CR 702.29 (cycling / typecycling)",
}

_ROMAN = {"I": 1, "II": 2, "III": 3, "IV": 4, "V": 5, "VI": 6}
# A chapter header may name several chapter numbers, e.g. "I, II —".
_CHAPTER_LINE_RE = re.compile(r"(?m)^\s*([IVX]+(?:\s*,\s*[IVX]+)*)\s*—")


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


ZONES = ["hand", "battlefield", "graveyard", "exile", "library", "stack"]


def _prov(card_id: str, face_id: str | None, rule_key: str, text: str | None = None,
          span: tuple[int, int] | None = None) -> Provenance:
    return Provenance(card_id=card_id, face_id=face_id,
                      source=f"rule.template:{rule_key}", text=text, span=span,
                      rule_ref=RULE_REFS[rule_key])


def _rule_prov(rule_key: str) -> list[Provenance]:
    return [Provenance(card_id="", source=f"rule.template:{rule_key}", rule_ref=RULE_REFS[rule_key])]


# ===========================================================================
# Shared / generic template graph (built once)
# ===========================================================================

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
    for oc, lbl in [("legendary", "Legendary permanent"), ("artifact", "Artifact"), ("saga", "Saga")]:
        gb.node(f"obj:{oc}", "ObjectClass", lbl)
    gb.node("counter:+1/+1", "CounterType", "+1/+1 counter")
    _storied_gate(gb)
    _recruit_generic(gb)
    _hone_generic(gb)
    _amass_generic(gb)
    _typecycling_generic(gb)


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
        output_state="state:enduring_story", provenance=_rule_prov("storied"),
    )
    gb.gate(gate)
    gb.node("state:enduring_story", "State", "enduring story",
            {"persistence": "rest_of_game", "on": "player", "removable": False})
    gb.edge("gate:storied", "state:enduring_story", "PRODUCES", provenance=_rule_prov("storied"))
    gb.edge("state:enduring_story", "state:enduring_story", "PERSISTS_AS")
    for oc in ("legendary", "artifact", "saga"):
        gb.edge("gate:storied", f"obj:{oc}", "COUNTS")


def _recruit_generic(gb: GraphBuilder) -> None:
    """The single generic Recruit template: one draw->discard->gate->create-Soldier
    chain. Card-specific recruit operations INSTANTIATE `op:recruit`; the Soldier is
    created by exactly ONE edge, not one per card."""
    p = _rule_prov("recruit")
    gb.gate(Gate(gate_id="gate:recruit-nonland-discard", gate_type="branch_condition",
                 label="Recruit: discarded card is nonland",
                 definition={"predicate": {"op": "is_nonland", "arg": "the_discarded_card"}},
                 provenance=p))
    gb.condition(StructuredCondition(
        condition_id="cond:recruit-nonland-discard",
        expression={"op": "is_nonland", "arg": "the_discarded_card"},
        human_readable="the discarded card is a nonland card", provenance=p))
    gb.node("op:recruit", "Operation", "recruit (generic keyword action)", provenance=p)
    gb.node("op:recruit:draw", "Operation", "draw", {"quantity": 1}, p)
    gb.node("op:recruit:discard", "Operation", "discard", {"quantity": 1, "choice": "controller"}, p)
    gb.edge("op:recruit", "rule:recruit", "REFERENCES_RULE", provenance=p)
    gb.edge("op:recruit", "op:recruit:draw", "CAUSES", provenance=p)
    gb.edge("op:recruit:draw", "event:card-drawn", "PRODUCES", quantity=1, provenance=p)
    gb.edge("op:recruit:draw", "op:recruit:discard", "CAUSES", timing="after", provenance=p)
    gb.edge("op:recruit:discard", "zone:graveyard", "MOVES_TO", provenance=p)
    gb.edge("op:recruit:discard", "gate:recruit-nonland-discard", "CAUSES", provenance=p)
    gb.edge("gate:recruit-nonland-discard", "token:human-soldier", "CREATES_OBJECT",
            quantity=1, condition_ids=["cond:recruit-nonland-discard"], provenance=p)


def _hone_generic(gb: GraphBuilder) -> None:
    """Generic hone rule (once), parameterized over a single bound Equipment E and the
    creature C it is attached to: E has a per-object hone-count state; the +n/+0 boost
    scales with THAT Equipment's count and modifies THAT attached creature — both
    references bind the same E. (Phase 2 review pt2, blocking #2.)"""
    p = _rule_prov("hone")
    eq = gb.node("obj:equipment-E", "ObjectClass", "an Equipment E (bound variable)")
    cr = gb.node("obj:creature-C", "ObjectClass", "the creature C equipped by E")
    hc = gb.node("state:hone-count:E", "State", "hone-count of Equipment E",
                 {"object": "obj:equipment-E", "counter": "hone", "value": 0}, p)
    boost = gb.node("effect:hone-boost", "Effect", "+n/+0 to the creature equipped by E",
                    {"power_per_counter": 1, "toughness": 0, "target": "obj:creature-C"}, p)
    gb.edge(eq, hc, "HAS_STATE", provenance=p)
    gb.edge(hc, "counter:hone", "HAS_COUNTER_TYPE", provenance=p)
    gb.edge(eq, cr, "ATTACHED_TO", provenance=p)
    gb.edge(boost, hc, "SCALES_WITH", provenance=p)   # +n scales with THIS E's hone-count
    gb.edge(boost, cr, "MODIFIES", provenance=p)      # applies to THIS E's attached creature
    gb.edge(boost, "rule:hone", "REFERENCES_RULE", provenance=p)


def _amass_generic(gb: GraphBuilder) -> None:
    """Generic Amass template (once), invoked per card via INSTANTIATES. Encodes the
    conditional sequence: if the controller has no qualifying Army, create the 0/0 Army
    token; then put N +1/+1 counters on an Army the controller controls. The Army
    subtype and N are supplied by each instantiation. No `AMASSES` primitive is added
    (Amass is a template, not a predicate — cf. Recruit)."""
    p = _rule_prov("amass")
    gb.node("token:army", "TokenSpec", "0/0 Army token (subtype supplied by the amass instance)")
    gb.node("op:amass", "Operation", "amass (generic keyword action)", provenance=p)
    gb.node("op:amass:add-counters", "Operation", "put +1/+1 counters on an Army you control", provenance=p)
    gb.gate(Gate(gate_id="gate:amass-no-army", gate_type="branch_condition",
                 label="Amass: controller controls no qualifying Army",
                 definition={"predicate": {"op": "controls_no", "arg": "Army"}}, provenance=p))
    gb.condition(StructuredCondition(
        condition_id="cond:amass-no-army", expression={"op": "controls_no", "arg": "Army"},
        human_readable="the controller controls no Army", provenance=p))
    gb.edge("op:amass", "rule:amass", "REFERENCES_RULE", provenance=p)
    gb.edge("op:amass", "gate:amass-no-army", "CAUSES", provenance=p)
    gb.edge("gate:amass-no-army", "token:army", "CREATES_OBJECT",
            condition_ids=["cond:amass-no-army"], provenance=p)
    gb.edge("op:amass", "op:amass:add-counters", "CAUSES", timing="after", provenance=p)
    gb.edge("op:amass:add-counters", "counter:+1/+1", "ADDS_COUNTER", provenance=p)


def _typecycling_generic(gb: GraphBuilder) -> None:
    """Generic typecycling template (once): pay the cycling cost AND discard this card ->
    search library for a card of the named type, reveal, put into hand, shuffle. The
    searched type is supplied by each instantiation. No new primitive predicate."""
    p = _rule_prov("typecycling")
    gb.node("op:typecycling", "Operation", "typecycling (generic keyword action)", provenance=p)
    gb.node("op:typecycling:search", "Operation", "search library for a card of the named type", provenance=p)
    gb.edge("op:typecycling", "rule:typecycling", "REFERENCES_RULE", provenance=p)
    gb.edge("op:typecycling", "zone:graveyard", "MOVES_TO", provenance=p)   # discard this card (cost)
    gb.edge("op:typecycling", "op:typecycling:search", "CAUSES", provenance=p)
    gb.edge("op:typecycling:search", "zone:library", "MOVES_FROM", provenance=p)
    gb.edge("op:typecycling:search", "zone:hand", "MOVES_TO", provenance=p)


# ===========================================================================
# Per-card instantiations
# ===========================================================================

def _find_span(text: str | None, pat: str) -> tuple[int, int] | None:
    if not text:
        return None
    m = re.search(pat, text, re.I)
    return (m.start(), m.end()) if m else None


def expand_recruit(gb: GraphBuilder, face: dict) -> None:
    """This face has the Recruit keyword: its recruit op INSTANTIATES the generic template."""
    fid, cid = face["id"], face["card_id"]
    p = [_prov(cid, fid, "recruit", "recruit", _find_span(face.get("oracle_text"), r"\brecruit\b"))]
    gb.node(fid, "CardFace", face.get("name", fid))
    op = gb.node(f"op:{fid}:recruit", "Operation", "recruit", provenance=p)
    gb.edge(fid, op, "HAS_ABILITY", provenance=p)
    gb.edge(op, "op:recruit", "INSTANTIATES", provenance=p)


def expand_storied_payoff(gb: GraphBuilder, face: dict) -> None:
    """A card with a Storied payoff: enduring_story ENABLES its static/enabled effect."""
    fid, cid = face["id"], face["card_id"]
    p = [_prov(cid, fid, "storied", "storied", _find_span(face.get("oracle_text"), r"\bstoried\b"))]
    gb.node(fid, "CardFace", face.get("name", fid))
    ab = gb.node(f"ab:{fid}:storied", "Ability", "storied payoff", provenance=p)
    gb.edge(fid, ab, "HAS_ABILITY", provenance=p)
    gb.edge(ab, "rule:storied", "REFERENCES_RULE", provenance=p)
    gb.edge("state:enduring_story", ab, "ENABLES", provenance=p)


def storied_qualifier(gb: GraphBuilder, node_id: str, node_type: str, label: str,
                      provenance: list[Provenance]) -> None:
    """Card-definition capacity: this object CAN qualify for Storied (QUALIFIES_FOR).
    Runtime battlefield instances would CONTRIBUTE_TO the count — not modeled in Phase 2.
    Exactly one edge per object (invariant #5: a legendary artifact qualifies once)."""
    gb.node(node_id, node_type, label)
    for e in gb.edges:
        if e.source == node_id and e.predicate == "QUALIFIES_FOR" and e.target == "gate:storied":
            return
    gb.edge(node_id, "gate:storied", "QUALIFIES_FOR", provenance=provenance)


def expand_hone(gb: GraphBuilder, face: dict) -> None:
    """This face places hone counters: its add-hone op invokes the generic hone rule.
    The +1/+0 lives on the generic effect (once), never on the source card."""
    fid, cid = face["id"], face["card_id"]
    p = [_prov(cid, fid, "hone", "hone counter", _find_span(face.get("oracle_text"), r"\bhone counter"))]
    gb.node(fid, "CardFace", face.get("name", fid))
    add = gb.node(f"op:{fid}:add-hone", "Operation", "put a hone counter on an Equipment", provenance=p)
    gb.edge(fid, add, "HAS_ABILITY", provenance=p)
    gb.edge(add, "counter:hone", "ADDS_COUNTER", provenance=p)
    gb.edge(add, "state:hone-count:E", "MODIFIES", quantity=1, provenance=p)  # increments that Equipment's count
    gb.edge(add, "rule:hone", "REFERENCES_RULE", provenance=p)


def expand_adventure(gb: GraphBuilder, primary: dict, adventure: dict) -> None:
    """Adventure: casting the spell may (CAN_LEAD_TO) resolve; resolution puts THIS card
    into a per-object Adventure-exiled state, which enables casting this card's permanent
    face from exile. Normal-from-hand casting preserved. Faces stay distinct."""
    pid, aid, cid = primary["id"], adventure["id"], primary["card_id"]
    p = [_prov(cid, aid, "adventure", "Adventure")]
    st = f"state:{cid}:adventure-exiled"
    gb.node(pid, "CardFace", primary.get("name", pid))
    gb.node(aid, "CardFace", adventure.get("name", aid))
    gb.node(st, "State", f"{primary.get('name', cid)}: Adventure-exiled",
            {"zone": "exile", "object": cid}, p)
    cast_adv = gb.node(f"op:{aid}:cast", "Operation", "cast adventure spell", provenance=p)
    resolve = gb.node(f"op:{aid}:resolve", "Operation", "adventure spell resolves", provenance=p)
    cast_exile = gb.node(f"op:{pid}:cast-from-exile", "Operation", "cast permanent from exile", provenance=p)
    cast_hand = gb.node(f"op:{pid}:cast-from-hand", "Operation", "cast permanent from hand", provenance=p)
    gb.edge(aid, cast_adv, "HAS_ABILITY", provenance=p)
    gb.edge(cast_adv, "zone:hand", "MOVES_FROM", provenance=p)
    gb.edge(cast_adv, "zone:stack", "MOVES_TO", provenance=p)
    gb.edge(cast_adv, resolve, "CAN_LEAD_TO", provenance=p)   # casting is not guaranteed to resolve
    gb.edge(resolve, st, "PRODUCES", provenance=p)            # resolution -> this object is exiled
    gb.edge(st, cast_exile, "ENABLES", provenance=p)          # its exiled state enables the permanent cast
    gb.edge(cast_exile, "zone:exile", "MOVES_FROM", provenance=p)
    gb.edge(cast_hand, "zone:hand", "MOVES_FROM", optional=True, provenance=p)
    gb.edge(cast_adv, "rule:adventure", "REFERENCES_RULE", provenance=p)


def expand_amass(gb: GraphBuilder, face: dict, army_subtype: str, n: str) -> None:
    """This face amasses: its amass op INSTANTIATES the generic Amass template, supplying
    the Army subtype and N (card-specific preceding/following effects stay on the card)."""
    fid, cid = face["id"], face["card_id"]
    p = [_prov(cid, fid, "amass", "amass", _find_span(face.get("oracle_text"), r"\bamass\b"))]
    gb.node(fid, "CardFace", face.get("name", fid))
    op = gb.node(f"op:{fid}:amass", "Operation", f"amass {army_subtype} {n}",
                 {"army_subtype": army_subtype, "n": n}, p)
    gb.edge(fid, op, "HAS_ABILITY", provenance=p)
    gb.edge(op, "op:amass", "INSTANTIATES", provenance=p)


def expand_typecycling(gb: GraphBuilder, face: dict, search_type: str) -> None:
    """This face has a typecycling variant (e.g. Halflingcycling): its typecycling op
    INSTANTIATES the generic template, supplying the searched card type."""
    fid, cid = face["id"], face["card_id"]
    p = [_prov(cid, fid, "typecycling", f"{search_type}cycling",
               _find_span(face.get("oracle_text"), r"\b\w+cycling\b"))]
    gb.node(fid, "CardFace", face.get("name", fid))
    op = gb.node(f"op:{fid}:typecycling", "Operation", f"{search_type}cycling",
                 {"search_type": search_type}, p)
    gb.edge(fid, op, "HAS_ABILITY", provenance=p)
    gb.edge(op, "op:typecycling", "INSTANTIATES", provenance=p)


def expand_saga(gb: GraphBuilder, face: dict) -> None:
    """Saga: a per-object lore-count state (HAS_COUNTER_TYPE lore); the Saga's own lore
    operations modify its own state; its own chapters are enabled by its own count;
    sacrifice after the final chapter. No lore counter enables another Saga's chapters."""
    fid, cid = face["id"], face["card_id"]
    p = [_prov(cid, fid, "saga", "Saga")]
    gb.node(fid, "CardFace", face.get("name", fid))
    lore = gb.node(f"state:{fid}:lore-count", "State", f"{face.get('name', fid)}: lore-count",
                   {"object": fid, "counter": "lore", "value": 0}, p)
    gb.edge(lore, "counter:lore", "HAS_COUNTER_TYPE", provenance=p)
    etb = gb.node(f"op:{fid}:add-lore-etb", "Operation", "add a lore counter as it enters", provenance=p)
    turn = gb.node(f"op:{fid}:add-lore-turn", "Operation", "add a lore counter each turn",
                   {"timing": "first_main_phase"}, p)
    gb.edge(fid, etb, "HAS_ABILITY", provenance=p)
    gb.edge(fid, turn, "HAS_ABILITY", provenance=p)
    gb.edge(etb, lore, "MODIFIES", quantity=1, provenance=p)
    gb.edge(turn, lore, "MODIFIES", quantity=1, provenance=p)
    gb.edge(fid, "rule:saga", "REFERENCES_RULE", provenance=p)

    # Parse chapter headers, each possibly naming several chapter numbers (e.g. "I, II").
    chapters: list[tuple[int, ...]] = []
    for m in _CHAPTER_LINE_RE.finditer(face.get("oracle_text") or ""):
        nums = tuple(_ROMAN[r] for r in re.findall(r"[IVX]+", m.group(1)) if r in _ROMAN)
        if nums:
            chapters.append(nums)

    all_values = sorted({n for nums in chapters for n in nums})
    ab_by_value: dict[int, str] = {}
    for nums in chapters:
        tag = "-".join(str(n) for n in nums)
        ab = gb.node(f"ab:{fid}:chapter-{tag}", "Ability",
                     f"chapter {', '.join(str(n) for n in nums)}", {"chapters": list(nums)}, p)
        # A chapter fires when the Saga's lore count *becomes* one of its numbers.
        cond_id = f"cond:{fid}:chapter-{tag}"
        gb.condition(StructuredCondition(
            condition_id=cond_id,
            expression={"condition_type": "state_transition_equals",
                        "state": lore, "accepted_values": list(nums)},
            human_readable=f"{face.get('name', fid)} lore count becomes "
                           + " or ".join(str(n) for n in nums),
            provenance=p))
        gb.edge(lore, ab, "ENABLES", condition_ids=[cond_id], provenance=p)
        for n in nums:
            ab_by_value[n] = ab

    if all_values:
        final = max(all_values)
        sac = gb.node(f"op:{fid}:sacrifice", "Operation", "sacrifice after final chapter",
                      {"after_chapter": final}, p)
        gb.edge(ab_by_value[final], sac, "CAUSES", timing="after", provenance=p)
        gb.edge(sac, "zone:graveyard", "MOVES_TO", provenance=p)

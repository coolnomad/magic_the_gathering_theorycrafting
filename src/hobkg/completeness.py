"""Additive "resource / trigger completeness" layer (three related families the reviewer
flagged as genuinely-missing typed pathways in the frozen HOB graph). Materialized as an
ADDITIVE layer (`data/graph_global/completeness_{nodes,edges,conditions}.jsonl`, origin
`completeness`) then REPROJECTED into `card_pair_projection_completeness.jsonl` as CONTINUOUS,
card-grounded typed paths over graph + completeness layer. The frozen graph and every other
layer are untouched.

FAMILY 2 — token-entry triggers.
  Belladonna Took: "Whenever a token you control enters, you gain 1 life ...". Its ability
  currently only hangs off the generic `event:enters_the_battlefield`, which no operation
  produces. We model a canonical `event:token-you-control-enters` (Event): every op with a
  frozen `op CREATES_OBJECT token:*` edge that creates a token FOR THE CONTROLLER PRODUCES it,
  and it TRIGGERS Belladonna's token-entry ability. Reproject: each token-creator CARD ->
  Belladonna Took, relation ENABLES_TRIGGER, grounded path
    card:creator -HAS_FACE-> face -HAS_ABILITY-> ability -CAUSES-> op
                 -PRODUCES-> event:token-you-control-enters -TRIGGERS-> belladonna-ability
                 <-HAS_ABILITY- face:belladonna <-HAS_FACE- card:belladonna.
  Gate-mediated creators (a `gate:*` source, no card op) and opponent-owned tokens
  (`creates_for=opponent`, not "a token you control") cannot be grounded from a card and are
  skipped (counted in stats).

FAMILY 3 — sacrifice-outlet -> dies-trigger.
  Sacrificing a creature is a death event. Each sac OUTLET whose cost/effect can sacrifice a
  CREATURE gets a completeness sac op (`op:completeness:sac:{face}`) that CAUSES the shared
  `event:dies`, so it feeds every dies-triggered ability (Lake-town Lookout, Fearsome Goblin
  Pair, Front Porch Sentries, Rhovanion Rampager -> amass, The Great Goblin). Reproject:
  sac-outlet CARD -> dies-trigger CARD, ENABLES_TRIGGER, grounded path
    card:outlet -HAS_FACE-> face -HAS_ABILITY-> ability -CAUSES-> op:sac -CAUSES-> event:dies
                -TRIGGERS-> dies-ability <-HAS_ABILITY- face:dies <-HAS_FACE- card:dies-creature.
  The `another`/self constraint is honoured by dropping outlet==target. Stone-Giant of High
  Pass sacrifices only an artifact, so it is NOT a family-3 enabler.

FAMILY 4 — general typed-cost + permanent-consumption (sacrifice fodder).
  Each sacrifice-as-cost operation gets a typed cost gate `gate:completeness:sac-cost:{face}`
  (accepted types, `another` bool, `or_pay` mana), plus `op:sac CONSUMES obj:type:{artifact,
  creature}` (only accepted types), `op:sac MOVES_TO zone:graveyard`, and conditions. Reproject:
  every controlled PERMANENT card P that is an artifact or creature -> the sac-cost CARD,
  relation SATISFIES_SACRIFICE_COST, grounded path
    card:P -HAS_FACE-> face:P -HAS_TYPE-> obj:type:{artifact|creature}
           <-CONSUMES- op:sac <-CAUSES- ability <-HAS_ABILITY- face:saccard <-HAS_FACE- card:saccard.
  Source is always a permanent, target always a sac-cost card (no reverse emitted). Equipment
  fodder carries `terminates_attachment: true`.
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

ORIGIN = "completeness"

# ---- canonical completeness nodes ---------------------------------------------------------
EVENT_TOKEN_ENTERS = "event:token-you-control-enters"
# the dies events the frozen dies-triggered abilities actually listen to (Lake-town Lookout /
# The Great Goblin -> event:dies; Front Porch Sentries -> event:this_creature_dies; Rhovanion
# Rampager / Fearsome Goblin Pair -> event:this-creature-dies). Sacrificing a creature is a
# death, so it feeds every "when [a/this] creature dies" trigger.
DIES_EVENTS = ["event:dies", "event:this-creature-dies", "event:this_creature_dies"]
OBJ_TYPE_ARTIFACT = "obj:type:artifact"
OBJ_TYPE_CREATURE = "obj:type:creature"
ZONE_GRAVEYARD = "zone:graveyard"

# Belladonna Took's token-entry triggered ability (currently only off event:enters_the_battlefield)
BELLADONNA_ABILITY = "ability:face:011da9c5-aa8a-4fa0-b1f2-62b9f3760476:0:token_enters_escalating"

_CR_TOKEN_ENTERS = "CR 603.2 (triggered abilities) / 111 (tokens)"
_CR_SACRIFICE = "CR 701.21 (Sacrifice) / 603.2 (dies triggers) / 118 (costs)"
# an OR additional cost is a cost-payment choice, NOT the Equipment/leave rules
_CR_OR_COST = "CR 118.8 (alternative/additional costs) / 601.2b, 601.2f-h (paying costs while casting)"

# ---- FAMILY 3/4 sacrifice outlets (surveyed from data/normalized/faces.jsonl oracle_text) ---
# face_id -> spec: name, accepts (subset of {"artifact","creature"}), another (bool),
#            or_pay (mana string or None), kind ("activated_cost"|"additional_cast_cost"|"effect")
SAC_OUTLETS = {
    "face:0ea58cfe-b37c-49a6-a3be-7e60065b8238:0": {   # Tom, Bert, and William
        "name": "Tom, Bert, and William", "accepts": ["creature"], "another": True,
        "or_pay": None, "kind": "activated_cost", "mana_cost": "{1}",
        "oracle_span": None, "clause": "{1}, Sacrifice another creature"},
    "face:8d88facd-cf7e-498e-ab6b-6bd021316162:0": {   # Gollum the Abandoned
        "name": "Gollum the Abandoned", "accepts": ["artifact", "creature"], "another": False,
        "or_pay": None, "kind": "activated_cost", "mana_cost": "{2}",
        "oracle_span": None, "clause": "{2}, Sacrifice an artifact or creature"},
    "face:fdf7f144-56e4-4f88-b81a-b85473922355:0": {   # Snowslope Hunter
        "name": "Snowslope Hunter", "accepts": ["artifact", "creature"], "another": True,
        "or_pay": None, "kind": "activated_cost", "mana_cost": None,
        "oracle_span": None, "clause": "Sacrifice another creature or artifact"},
    "face:008a11c1-d283-49fe-abd7-ff4fe8b1fe79:0": {   # Rhovanion Rampager
        "name": "Rhovanion Rampager", "accepts": ["creature"], "another": True,
        "or_pay": None, "kind": "effect", "mana_cost": None,
        "oracle_span": None, "clause": "Whenever this creature attacks, you may sacrifice another creature"},
    "face:88522a0f-5377-4522-97f4-4148bef954af:0": {   # Bolg of the North
        "name": "Bolg of the North", "accepts": ["creature"], "another": True,
        "or_pay": None, "kind": "effect", "mana_cost": None,
        "oracle_span": None, "clause": "When Bolg enters, you may sacrifice another creature"},
    "face:e3a665f9-6e51-4e0d-923b-e9552d5978a4:0": {   # The Sackville-Bagginses
        "name": "The Sackville-Bagginses", "accepts": ["artifact", "creature"], "another": True,
        "or_pay": None, "kind": "effect", "mana_cost": None,
        "oracle_span": None, "clause": "you may sacrifice another creature or artifact"},
    "face:dda607bd-f419-4b7f-b052-a5ce6ce22bfe:0": {   # Stir Up Trouble
        "name": "Stir Up Trouble", "accepts": ["artifact", "creature"], "another": False,
        "or_pay": "{4}", "kind": "additional_cast_cost", "mana_cost": None,
        "oracle_span": None,
        "clause": "As an additional cost to cast this spell, sacrifice an artifact or creature or pay {4}"},
    "face:2e728381-6db0-4c66-883d-82d718fef833:1": {   # Allure of Power (adventure face)
        "name": "Allure of Power", "accepts": ["creature"], "another": False,
        "or_pay": None, "kind": "additional_cast_cost", "mana_cost": None,
        "oracle_span": None, "clause": "As an additional cost to cast this spell, sacrifice a creature"},
    "face:cfaa8b7b-7bfc-4660-bbc7-a717e05df6ef:0": {   # Stone-Giant of High Pass (ARTIFACT ONLY)
        "name": "Stone-Giant of High Pass", "accepts": ["artifact"], "another": False,
        "or_pay": None, "kind": "activated_cost", "mana_cost": "{2}{R}",
        "oracle_span": None, "clause": "{2}{R}, Sacrifice an artifact"},
}

COND_SAC_CONTROLLED = "cond:completeness-sac-controlled"
COND_SAC_ON_BATTLEFIELD = "cond:completeness-sac-on-battlefield"
COND_SAC_ANOTHER = "cond:completeness-sac-another"
# pt9: for an OR additional cost (Stir's "sacrifice ... OR pay {4}") the sacrifice executes ONLY when
# the sacrifice branch is chosen — mutually exclusive with the pay branch. So a simulator executing
# the pay branch does not reach the sacrifice op / consume a permanent / terminate an attachment.
COND_OR_SACRIFICE = "cond:completeness-or-sacrifice-branch-chosen"
COND_OR_PAY = "cond:completeness-or-pay-branch-chosen"
# pt10: sacrificing a permanent is a death (dies) event ONLY when the sacrificed object is a
# creature. For an outlet that accepts BOTH artifact and creature, the dies event must be gated on
# this — otherwise sacrificing a noncreature artifact wrongly enables creature-dies triggers.
COND_SAC_IS_CREATURE = "cond:completeness-sacrificed-is-creature"


def _card_of(nid):
    m = _UUID.search(nid or "")
    return "card:" + m.group(0) if m else None


def _face_of(nid):
    m = _FACE.search(nid or "")
    return m.group(0) if m else None


def _mid(source, predicate, target):
    return "c" + hashlib.sha1(f"{source}|{predicate}|{target}".encode("utf-8")).hexdigest()[:15]


def _step(edge, direction):
    """Lean path step: keep edge_id/predicate/endpoints/direction + semantic props, drop the
    provenance blob (it stays retrievable via edge_id)."""
    s = project._step(edge, direction)
    s.pop("provenance", None)
    return s


def _reverse_steps(steps):
    """Reverse a forward chain (A→…→Z) into Z→…→A: reverse order, swap each step's endpoints/direction."""
    out = []
    for s in reversed(steps):
        r = dict(s)
        r["source"], r["target"] = s["target"], s["source"]
        r["direction"] = "reverse" if s.get("direction") == "forward" else "forward"
        out.append(r)
    return out


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


def _node(nid, ntype, label, data, provs):
    return {"id": nid, "type": ntype, "label": label, "data": data,
            "provenance": provs, "origin": ORIGIN}


def _edge(source, predicate, target, provs, **props):
    return {"edge_id": _mid(source, predicate, target), "source": source, "predicate": predicate,
            "target": target, "provenance": provs, "origin": ORIGIN, **props}


def _prov(rule_ref, derivation, face_id=None, oracle_span=None, text=None):
    p = {"source": ORIGIN, "rule_ref": rule_ref, "derivation": derivation}
    if face_id:
        p["face_id"] = face_id
    if oracle_span and face_id:
        p["oracle_span"] = oracle_span
    if text:
        p["text"] = text
    return p


# --------------------------------------------------------------------------- #
#  materialize                                                                 #
# --------------------------------------------------------------------------- #
def materialize(repo: Path = REPO) -> dict:
    g = _G(repo)
    nodes: dict = {}
    edges: list = []
    conditions: dict = {}

    def node(nid, ntype, label, data, provs):
        nodes.setdefault(nid, _node(nid, ntype, label, data, provs))

    def add_cond(cid, expression, human, note):
        conditions.setdefault(cid, {"condition_id": cid, "executable": True, "expression": expression,
                                    "human_readable": human,
                                    "provenance": [_prov(_CR_SACRIFICE, note)], "origin": ORIGIN})

    # ---- FAMILY 2: token-you-control-enters -----------------------------------------------
    node(EVENT_TOKEN_ENTERS, "Event", "a token you control enters",
         {"kind": "zone_change", "object": "token", "controller_constraint": "you control"},
         [_prov(_CR_TOKEN_ENTERS, "canonical 'a token you control enters' event")])
    fam2_creators = 0
    fam2_skipped_gate = 0
    fam2_skipped_opponent = 0
    for e in g.edges:
        if e["predicate"] != "CREATES_OBJECT" or not e["target"].startswith("token:"):
            continue
        op = e["source"]
        if not op.startswith("op:") or not _card_of(op):    # gate-mediated (no card op) -> can't ground
            fam2_skipped_gate += 1
            continue
        if (e.get("creates_for") or "controller") != "controller":   # opponent's token: not "you control"
            fam2_skipped_opponent += 1
            continue
        edges.append(_edge(op, "PRODUCES", EVENT_TOKEN_ENTERS,
                           [_prov(_CR_TOKEN_ENTERS,
                                  "creating a token you control makes a token-you-control-enters event",
                                  face_id=_face_of(op))]))
        fam2_creators += 1
    # the event triggers Belladonna's token-entry ability
    if BELLADONNA_ABILITY in g.nodes:
        edges.append(_edge(EVENT_TOKEN_ENTERS, "TRIGGERS", BELLADONNA_ABILITY,
                           [_prov(_CR_TOKEN_ENTERS,
                                  "Belladonna Took triggers whenever a token you control enters",
                                  face_id=_face_of(BELLADONNA_ABILITY))]))

    # ---- FAMILY 3 + 4: sacrifice outlets --------------------------------------------------
    add_cond(COND_SAC_CONTROLLED, {"op": "controls", "subject": "activator", "object": "sacrificed_permanent"},
             "The sacrificed permanent must be one the activating player controls.", "sacrifice controller")
    add_cond(COND_SAC_ON_BATTLEFIELD, {"op": "in_zone", "subject": "sacrificed_permanent", "zone": "battlefield"},
             "Only a permanent on the battlefield can be sacrificed.", "sacrifice battlefield zone")
    add_cond(COND_OR_SACRIFICE, {"op": "branch_chosen", "or_gate": "additional_cost", "branch": "sacrifice",
                                 "mutually_exclusive_with": COND_OR_PAY},
             "The sacrifice branch of the OR additional cost was chosen (mutually exclusive with paying).",
             "OR additional cost — sacrifice branch")
    add_cond(COND_OR_PAY, {"op": "branch_chosen", "or_gate": "additional_cost", "branch": "pay",
                           "mutually_exclusive_with": COND_OR_SACRIFICE},
             "The pay branch of the OR additional cost was chosen (mutually exclusive with sacrificing).",
             "OR additional cost — pay branch")
    add_cond(COND_SAC_IS_CREATURE, {"op": "has_type", "subject": "sacrificed_permanent", "type": "creature"},
             "The sacrificed permanent is a creature (so its removal is a death / dies event).",
             "sacrificed object is a creature")
    add_cond(COND_SAC_ANOTHER, {"op": "distinct", "left": "sacrificed_permanent", "right": "source_permanent"},
             "The sacrificed permanent must be ANOTHER permanent (not the source itself).", "sacrifice another")

    fam3_enablers = 0
    fam4_gates = 0
    for fid, spec in sorted(SAC_OUTLETS.items()):
        if fid not in g.face_by_id:
            continue
        name = spec["name"]
        accepts = spec["accepts"]
        ability = f"ability:completeness:sac:{fid}"
        op = f"op:completeness:sac:{fid}"
        gate = f"gate:completeness:sac-cost:{fid}"
        p = [_prov(_CR_SACRIFICE, "sacrifice-outlet cost/effect", face_id=fid,
                   oracle_span=spec.get("oracle_span"), text=spec["clause"])]
        # the sac ability + op, hung off the outlet's face (HAS_ABILITY: CardFace -> Ability)
        node(ability, "Ability", f"sacrifice outlet: {name}",
             {"equipment": None, "kind": "sacrifice_outlet", "outlet_kind": spec["kind"],
              "accepts": accepts, "another": spec["another"], "or_pay": spec["or_pay"]}, p)
        node(op, "Operation", f"sacrifice a permanent: {name}",
             {"kind": "sacrifice", "accepts": accepts, "another": spec["another"],
              "or_pay": spec["or_pay"], "destination": "graveyard"}, p)
        edges.append(_edge(fid, "HAS_ABILITY", ability, p))
        # pt10: for an OR additional cost the OR gate is the SOLE causal parent of the sacrifice —
        # remove the direct ability->CAUSES->sac (which would double-cause it) and route
        # ability -REQUIRES-> gate:or-cost -CAUSES-> sac [sacrifice branch] / -CAUSES-> pay [pay branch].
        or_pay = spec.get("or_pay")
        if or_pay:
            or_gate = f"gate:or-cost:{fid}"
            pay_op = f"op:pay:{fid}"
            pay_cost = f"cost:pay:{or_pay}"
            po = [_prov(_CR_OR_COST, "OR additional cost (sacrifice or pay)", face_id=fid,
                        oracle_span=spec.get("oracle_span"), text=spec["clause"])]
            node(or_gate, "Gate", f"OR cost: sacrifice or pay {or_pay}",
                 {"gate_type": "or", "mutually_exclusive": True, "branches": ["sacrifice", "pay"],
                  "pay": or_pay, "sacrifice_branch": op, "pay_branch": pay_op,
                  "sacrifice_condition": COND_OR_SACRIFICE, "pay_condition": COND_OR_PAY}, po)
            node(pay_cost, "Cost", f"pay {or_pay}", {"mana_cost": or_pay, "kind": "mana"}, po)
            node(pay_op, "Operation", f"pay {or_pay} (OR alternative)",
                 {"kind": "pay_mana", "mana_cost": or_pay, "consumes_permanent": False}, po)
            edges.append(_edge(ability, "REQUIRES", or_gate, po))          # the additional cost = the OR gate
            edges.append(_edge(or_gate, "HAS_ALTERNATIVE", op, po))        # sacrifice branch
            edges.append(_edge(or_gate, "HAS_ALTERNATIVE", pay_op, po))    # pay branch
            edges.append(_edge(or_gate, "CAUSES", op, po, condition_ids=[COND_OR_SACRIFICE]))   # sole cause of sac
            edges.append(_edge(or_gate, "CAUSES", pay_op, po, condition_ids=[COND_OR_PAY]))
            edges.append(_edge(pay_op, "HAS_COST", pay_cost, po))
            edges.append(_edge(pay_op, "CONSUMES", "resource:mana", po, quantity=4))  # pays {4} generic
        else:
            edges.append(_edge(ability, "CAUSES", op, p))                  # mandatory sacrifice
        # typed cost gate (FAMILY 4): alternatives = accepted types, `another`, `or_pay`
        node(gate, "Gate", f"sacrifice cost: {name}",
             {"gate_type": "typed_sacrifice_cost", "alternatives": accepts, "another": spec["another"],
              "or_pay": spec["or_pay"], "mana_cost": spec.get("mana_cost"),
              "destination": "graveyard"}, p)
        # gate REQUIRES the accepted object type(s) (Gate -> ObjectClass)
        sac_conds = [COND_SAC_CONTROLLED, COND_SAC_ON_BATTLEFIELD]
        if spec["another"]:
            sac_conds = sac_conds + [COND_SAC_ANOTHER]
        for t in accepts:
            cls = OBJ_TYPE_ARTIFACT if t == "artifact" else OBJ_TYPE_CREATURE
            edges.append(_edge(gate, "REQUIRES", cls, p, condition_ids=list(sac_conds)))
            # the sac op CONSUMES the accepted permanent type (Operation -> ObjectClass)
            edges.append(_edge(op, "CONSUMES", cls, p, condition_ids=list(sac_conds)))
        # the sacrifice destination (Operation -> Zone)
        edges.append(_edge(op, "MOVES_TO", ZONE_GRAVEYARD, p))
        fam4_gates += 1
        # FAMILY 3: sacrificing a CREATURE is a death event -> feed every dies event a frozen
        # dies-triggered ability listens to (event:dies / this-creature-dies / this_creature_dies)
        if "creature" in accepts:
            fired = [ev for ev in DIES_EVENTS if ev in g.nodes]
            # pt10 #1: if the outlet ALSO accepts artifacts, the death event happens only when the
            # sacrificed object is actually a creature — gate it so sacrificing an artifact does NOT
            # emit a creature-dies event. Creature-only outlets always sacrifice a creature.
            dies_conds = [COND_SAC_IS_CREATURE] if "artifact" in accepts else []
            for ev in fired:
                edges.append(_edge(op, "CAUSES", ev,
                                   [_prov(_CR_SACRIFICE,
                                          "sacrificing a creature to this outlet is a death event (feeds dies triggers)",
                                          face_id=fid, text=spec["clause"])],
                                   **({"condition_ids": dies_conds} if dies_conds else {})))
            if fired:
                fam3_enablers += 1

    # ---- write + validate -----------------------------------------------------------------
    outdir = repo / "data" / "graph_global"
    uniq = {}
    for e in edges:
        uniq.setdefault(e["edge_id"], {k: v for k, v in e.items() if v is not None})
    edges = sorted(uniq.values(), key=lambda e: (e["source"], e["predicate"], e["target"]))
    with (outdir / "completeness_nodes.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for n in sorted(nodes.values(), key=lambda n: n["id"]):
            fh.write(json.dumps(n, ensure_ascii=False, sort_keys=True) + "\n")
    with (outdir / "completeness_edges.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for e in edges:
            fh.write(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n")
    with (outdir / "completeness_conditions.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for c in sorted(conditions.values(), key=lambda c: c["condition_id"]):
            fh.write(json.dumps(c, ensure_ascii=False, sort_keys=True) + "\n")

    from .graph_repair import _validate_repair_layer
    violations = _validate_repair_layer(repo, g.nodes, nodes, edges)
    defined = {c["condition_id"] for c in _load_dicts(repo / "data/graph_global/conditions.jsonl")} | set(conditions)
    referenced = {c for e in edges for c in (e.get("condition_ids") or [])}
    unresolved = sorted(referenced - defined)
    return {"completeness_nodes": len(nodes), "completeness_edges": len(edges),
            "completeness_conditions": len(conditions),
            "fam2_token_creators": fam2_creators, "fam2_skipped_gate_mediated": fam2_skipped_gate,
            "fam2_skipped_opponent_tokens": fam2_skipped_opponent,
            "fam3_dies_enablers": fam3_enablers, "fam4_sac_cost_gates": fam4_gates,
            "unresolved_conditions": unresolved, "signature_violations": len(violations),
            "_violations": violations}


# --------------------------------------------------------------------------- #
#  Reprojection: CONTINUOUS, card-to-card grounded typed paths                  #
# --------------------------------------------------------------------------- #
def reproject(repo: Path = REPO) -> dict:
    g = _G(repo)
    c_nodes = {n["id"]: n for n in _load_dicts(repo / "data/graph_global/completeness_nodes.jsonl")}
    c_edges = list(_load_dicts(repo / "data/graph_global/completeness_edges.jsonl"))
    all_edges = g.edges + c_edges
    c_ids = {e["edge_id"] for e in c_edges}
    real_ids = {e["edge_id"] for e in g.edges}
    index = {}
    for e in all_edges:
        index.setdefault((e["source"], e["predicate"], e["target"]), e)

    def E(source, predicate, target):
        return index.get((source, predicate, target))

    # card <-> face structural edges (frozen)
    hasface = {}                         # card -> HAS_FACE edge (card -> face)
    hasface_by_face = {}                 # face -> HAS_FACE edge
    for e in g.edges:
        if e["predicate"] == "HAS_FACE":
            hasface.setdefault(_card_of(e["source"]), e)
            hasface_by_face.setdefault(e["target"], e)
    hasab_by_ability = {}                # ability -> HAS_ABILITY edge (face -> ability), frozen
    for e in g.edges:
        if e["predicate"] == "HAS_ABILITY":
            hasab_by_ability.setdefault(e["target"], e)

    metaedges = []

    def emit(a_card, b_card, relation, steps, extra):
        if not a_card or not b_card or a_card == b_card or any(s is None for s in steps):
            return
        for x, y in zip(steps, steps[1:]):                    # CONTINUITY
            if x["target"] != y["source"]:
                return
        nodes_seq = [steps[0]["source"]] + [s["target"] for s in steps]
        if _card_of(nodes_seq[0]) != a_card or _card_of(nodes_seq[-1]) != b_card:   # CARD-GROUNDED
            return
        conds = sorted({c for s in steps for c in (s.get("condition_ids") or [])})
        m = {"source_card": a_card, "target_card": b_card, "relation": relation, "origin": ORIGIN,
             "path_kind": "grounded", "steps": steps, "primitive_path": nodes_seq,
             "path_predicates": [s["predicate"] for s in steps], "edge_ids": [s["edge_id"] for s in steps],
             "uses_completeness_edges": [s["edge_id"] for s in steps if s["edge_id"] in c_ids],
             "connecting_node": nodes_seq[1]}
        if conds:
            m["condition_ids"] = conds
        m.update(extra)
        metaedges.append(m)

    def ability_to_card_tail(ability):
        """Reverse tail  ability <-HAS_ABILITY- face <-HAS_FACE- card  (two reverse steps)."""
        hab = hasab_by_ability.get(ability)
        if not hab:
            return None, None
        face = hab["source"]
        hf = hasface_by_face.get(face)
        if not hf:
            return None, None
        return [_step(hab, "reverse"), _step(hf, "reverse")], _card_of(face)

    # ---- FAMILY 2: token creator CARD -> Belladonna Took (ENABLES_TRIGGER) -----------------
    trig = E(EVENT_TOKEN_ENTERS, "TRIGGERS", BELLADONNA_ABILITY)
    tail, bella_card = ability_to_card_tail(BELLADONNA_ABILITY) if trig else (None, None)
    fam2_reprojected = fam2_ungrounded = 0
    if trig and tail:
        for prod in [e for e in c_edges if e["predicate"] == "PRODUCES" and e["target"] == EVENT_TOKEN_ENTERS]:
            op = prod["source"]
            a_card = _card_of(op)
            # frozen head:  card:A -HAS_FACE-> face:A -HAS_ABILITY-> ability -CAUSES-> op
            hf = hasface.get(a_card)
            cause = next((e for e in g.edges if e["predicate"] == "CAUSES" and e["target"] == op), None)
            hab = hasab_by_ability.get(cause["source"]) if cause else None
            if not (hf and cause and hab):
                fam2_ungrounded += 1
                continue
            steps = [_step(hf, "forward"), _step(hab, "forward"), _step(cause, "forward"),
                     _step(prod, "forward"), _step(trig, "forward")] + tail
            before = len(metaedges)
            emit(a_card, bella_card, "ENABLES_TRIGGER", steps,
                 {"trigger": "token-you-control-enters"})
            fam2_reprojected += (len(metaedges) - before)

    def sac_head(fid):
        """Head steps card:O -> op:completeness:sac:{fid}. pt10: for an OR-cost outlet the OR gate
        is the SOLE causal parent (ability -REQUIRES-> gate:or-cost -CAUSES-> op:sac); a non-OR
        outlet keeps ability -CAUSES-> op:sac."""
        op = f"op:completeness:sac:{fid}"
        a_card = _card_of(fid)
        hf = hasface_by_face.get(fid)      # key by the OUTLET's face (adventure faces are :1, not :0)
        hab = E(fid, "HAS_ABILITY", f"ability:completeness:sac:{fid}")
        if not (hf and hab):
            return None, None
        if SAC_OUTLETS.get(fid, {}).get("or_pay"):
            req = E(f"ability:completeness:sac:{fid}", "REQUIRES", f"gate:or-cost:{fid}")
            cau = E(f"gate:or-cost:{fid}", "CAUSES", op)
            if not (req and cau):
                return None, None
            return [_step(hf, "forward"), _step(hab, "forward"), _step(req, "forward"), _step(cau, "forward")], a_card
        cau = E(f"ability:completeness:sac:{fid}", "CAUSES", op)
        if not cau:
            return None, None
        return [_step(hf, "forward"), _step(hab, "forward"), _step(cau, "forward")], a_card

    # ---- FAMILY 3: sac-outlet CARD -> dies-trigger CARD (ENABLES_TRIGGER) ------------------
    # each sac op CAUSES every dies event; each dies event TRIGGERS the frozen dies-abilities.
    fam3_reprojected = 0
    dies_causers = [e for e in c_edges if e["predicate"] == "CAUSES" and e["target"] in DIES_EVENTS]
    dies_triggers_by_ev = defaultdict(list)
    for e in all_edges:
        if e["predicate"] == "TRIGGERS" and e["source"] in DIES_EVENTS:
            dies_triggers_by_ev[e["source"]].append(e)
    for cause_dies in dies_causers:
        op = cause_dies["source"]              # op:completeness:sac:{fid}
        ev = cause_dies["target"]
        fid = _face_of(op)
        base, a_card = sac_head(fid)
        if not base:
            continue
        head = base + [_step(cause_dies, "forward")]
        for trg in dies_triggers_by_ev.get(ev, []):
            dies_ability = trg["target"]
            b_tail, b_card = ability_to_card_tail(dies_ability)
            if not b_tail:
                continue
            steps = head + [_step(trg, "forward")] + b_tail
            emit(a_card, b_card, "ENABLES_TRIGGER", steps,
                 {"trigger": "dies", "via": "sacrifice", "dies_event": ev})
            fam3_reprojected += 1

    # ---- FAMILY 4: controlled permanent CARD -> sac-cost CARD (SATISFIES_SACRIFICE_COST) ---
    fam4_reprojected = 0
    # permanent population per accepted type: card -> a representative HAS_TYPE edge (face -> type)
    htype = {OBJ_TYPE_ARTIFACT: {}, OBJ_TYPE_CREATURE: {}}
    equipment_faces = set(e["source"] for e in g.edges
                          if e["predicate"] == "HAS_TYPE" and e["target"] == "obj:subtype:equipment")
    for e in g.edges:
        if e["predicate"] == "HAS_TYPE" and e["target"] in htype and _card_of(e["source"]):
            htype[e["target"]].setdefault(_card_of(e["source"]), e)
    for con in [e for e in c_edges if e["predicate"] == "CONSUMES" and e["target"] in htype]:
        op = con["source"]                     # op:completeness:sac:{fid}
        fid = _face_of(op)
        cls = con["target"]
        b_card = _card_of(op)
        # tail:  cls <-CONSUMES- op <- (causal chain) <- card:saccard. The causal chain routes
        # through the OR gate for OR-cost outlets (pt10) — reuse the forward head, reversed.
        base, _ = sac_head(fid)
        if not base:
            continue
        spec = SAC_OUTLETS.get(fid, {})
        tail = [_step(con, "reverse")] + _reverse_steps(base)
        for p_card, ht in sorted(htype[cls].items()):
            hf_p = hasface.get(p_card)
            if not hf_p:
                continue
            face_p = ht["source"]
            # head:  card:P -HAS_FACE-> face:P -HAS_TYPE-> obj:type:{cls}
            steps = [_step(hf_p, "forward"), _step(ht, "forward")] + tail
            extra = {"sacrificed_type": "artifact" if cls == OBJ_TYPE_ARTIFACT else "creature",
                     "accepts": spec.get("accepts"), "another": spec.get("another"),
                     "or_pay": spec.get("or_pay"), "outlet_kind": spec.get("kind")}
            if face_p in equipment_faces:
                extra["terminates_attachment"] = True
            # pt7: distinguish a MANDATORY sacrifice COST (activated/additional-cast cost — the
            # permanent is genuine fodder a deck needs) from an OPTIONAL sacrifice EFFECT
            # ("you may sacrifice ..." on resolution — merely an eligible target, not required).
            relation = ("SATISFIES_SACRIFICE_COST"
                        if spec.get("kind") in ("activated_cost", "additional_cast_cost")
                        else "IS_ELIGIBLE_SACRIFICE_TARGET")
            before = len(metaedges)
            emit(p_card, b_card, relation, steps, extra)
            fam4_reprojected += (len(metaedges) - before)

    metaedges.sort(key=lambda m: (m["source_card"], m["target_card"], m["relation"],
                                  m.get("sacrificed_type") or "", m["connecting_node"]))
    with (repo / "data/graph_global/card_pair_projection_completeness.jsonl").open(
            "w", encoding="utf-8", newline="\n") as fh:
        for m in metaedges:
            fh.write(json.dumps(m, ensure_ascii=False, sort_keys=True) + "\n")

    # SELF-CHECK gates: continuity, card-grounded endpoints, edge resolution
    paths_continuous = all(x["target"] == y["source"]
                           for m in metaedges for x, y in zip(m["steps"], m["steps"][1:]))
    paths_card_grounded = all(_card_of(m["primitive_path"][0]) == m["source_card"]
                              and _card_of(m["primitive_path"][-1]) == m["target_card"] for m in metaedges)
    edges_resolve = all(s["edge_id"] in real_ids or s["edge_id"] in c_ids
                        for m in metaedges for s in m["steps"])
    by_rel = {}
    for m in metaedges:
        by_rel[m["relation"]] = by_rel.get(m["relation"], 0) + 1
    _report(repo, g, metaedges, by_rel, paths_continuous, paths_card_grounded, edges_resolve)
    return {"reprojected": len(metaedges), "by_relation": by_rel,
            "fam2_enables_trigger": fam2_reprojected, "fam2_ungrounded_creators": fam2_ungrounded,
            "fam3_enables_trigger": fam3_reprojected, "fam4_satisfies_sacrifice_cost": fam4_reprojected,
            "paths_continuous": paths_continuous, "paths_card_grounded": paths_card_grounded,
            "edges_resolve": edges_resolve}


def _report(repo, g, metaedges, by_rel, continuous, grounded, ok):
    L = ["# HOB Completeness Layer — Materialization + Reprojection", "",
         f"- **reprojected metaedges**: {len(metaedges)} (origin `completeness`)",
         f"- **by relation**: {by_rel}",
         f"- **paths continuous (step joins connect)**: {continuous}",
         f"- **paths card-grounded (card:A ... card:B)**: {grounded}",
         f"- **all path edges resolve**: {ok}", "", "## Sample relations", ""]
    for m in metaedges[:60]:
        a, b = g.names.get(m["source_card"], m["source_card"]), g.names.get(m["target_card"], m["target_card"])
        L.append(f"- **{a} -> {b}** [{m['relation']}] via `{m['connecting_node']}` — "
                 f"{' -> '.join(m['path_predicates'])}")
    if len(metaedges) > 60:
        L.append("- ... (truncated)")
    (repo / "reports" / "completeness.md").write_text("\n".join(L) + "\n", encoding="utf-8")

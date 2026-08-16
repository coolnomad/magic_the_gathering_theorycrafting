"""Additive Equip attachment layer for "The Hobbit" Equipment cards.

The 12 Equipment card faces (those with `HAS_TYPE -> obj:subtype:equipment` that also
have a face record; the `token:axe` Equipment has no face and is skipped) each print an
Equip activated ability and, usually, continuous "equipped creature" effects. The frozen
Phase 4 graph modelled the Equipment TYPE line but not the *attachment* mechanic: what the
Equip ability does, what it costs, what target it binds, and how the equipped-creature
bonuses route through that binding.

This module materializes a small ADDITIVE layer
(`data/graph_global/equip_{nodes,edges,conditions}.jsonl`, origin `equip`) — the frozen
graph, the graph-repair layer, the legend layer and the mechanism layer are all untouched —
then REPROJECTS it into `card_pair_projection_equip.jsonl` as faithful typed paths over the
finite creature population (112 creature cards).

The reusable Equip template binds the target creature C as a VARIABLE (one
`state:attachment:E` per Equipment, NOT one per pair):

    face:E  HAS_ABILITY -> ability:equip:E ; HAS_COST(on ability) -> cost:equip:E ;
            REFERENCES_RULE -> rule:equip
    ability:equip:E  CAUSES -> op:equip:E
    op:equip:E  REQUIRES -> obj:creature-you-control
    op:equip:E  CAUSES  -> state:attachment:E   (the bound attachment State)

Every continuous "equipped creature" bonus (P/T modification, granted keyword/ability) and
every automatic (ETB) attachment routes through the SAME `state:attachment:E` /
`obj:bound-creature:E`, so a bonus is only ever expressed while the Equipment is attached.
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

RULE_EQUIP = "rule:equip"
OBJ_CREATURE_YOU_CONTROL = "obj:creature-you-control"
OBJ_TYPE_CREATURE = "obj:type:creature"
OBJ_SUBTYPE_WIZARD = "obj:subtype:wizard"
OBJ_SUBTYPE_DWARF = "obj:subtype:dwarf"

# shared conditions (same object for every Equipment)
COND_TARGET_CONTROLLED = "cond:equip-target-controlled-by-activator"
COND_SORCERY_TIMING = "cond:equip-sorcery-timing"
COND_TARGET_IS_WIZARD = "cond:equip-target-is-wizard"
COND_AUTO_ATTACH_TARGET_IS_DWARF = "cond:auto-attach-target-is-dwarf"

# keyword abilities the equipped-creature line can grant (normalized lowercase tokens)
_KEYWORDS = [
    ("hexproof", "hexproof"), ("trample", "trample"), ("reach", "reach"),
    ("menace", "menace"), ("prowess", "prowess"), ("flying", "flying"),
    ("vigilance", "vigilance"), ("lifelink", "lifelink"), ("deathtouch", "deathtouch"),
    ("first strike", "first strike"), ("double strike", "double strike"),
    ("indestructible", "indestructible"), ("haste", "haste"),
    ("can't be blocked", "can't be blocked"),
]


def _card_of(nid: str):
    m = _UUID.search(nid)
    return "card:" + m.group(0) if m else None


def _slug(name: str) -> str:
    s = (name or "").lower()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def _mid(source: str, predicate: str, target: str) -> str:
    return "e" + hashlib.sha1(f"{source}|{predicate}|{target}".encode("utf-8")).hexdigest()[:15]


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

    def equipment_faces(self) -> list:
        """The 12 Equipment CardFaces: HAS_TYPE -> obj:subtype:equipment AND has a face
        record (skips token:axe, which has no face)."""
        ids = sorted({e["source"] for e in self.edges
                      if e["predicate"] == "HAS_TYPE" and e["target"] == "obj:subtype:equipment"
                      and e["source"] in self.face_by_id})
        return [self.face_by_id[i] for i in ids]


def _node(nid: str, ntype: str, label: str, data: dict, note: str) -> dict:
    return {"id": nid, "type": ntype, "label": label, "data": data,
            "provenance": [{"source": "equip", "derivation": note}], "origin": "equip"}


def _edge(source: str, predicate: str, target: str, note: str, **props) -> dict:
    return {"edge_id": _mid(source, predicate, target), "source": source, "predicate": predicate,
            "target": target, "provenance": [{"source": "equip", "derivation": note}],
            "origin": "equip", **props}


# --------------------------------------------------------------------------- #
#  Oracle parsing                                                              #
# --------------------------------------------------------------------------- #
_JUNK_SEP = re.compile("[ —�]")


def _clean(text: str) -> str:
    # normalize stray separators glued to "Equip" (non-breaking space U+00A0, em dash
    # U+2014, U+FFFD replacement char, e.g. "Equip<sep>{2}") to a plain space.
    return _JUNK_SEP.sub(" ", text or "")


def _parse_equip_costs(oracle: str) -> list:
    """Return the list of Equip cost modes, each a dict:
        {mana_cost, additional_cost, restriction, alternative, raw}
    Handles `Equip {N}`, `Equip {N}, Pay 2 life`, and restricted modes `Equip Wizard {1}`
    alongside a plain `Equip {3}` (alternative modes)."""
    text = _clean(oracle)
    modes = []
    # e.g. "Equip Wizard {1}", "Equip {2}, Pay 2 life", "Equip {3}"
    pat = re.compile(r"Equip(?:\s+([A-Za-z]+))?\s*(\{[^}]+\}(?:\{[^}]+\})*)((?:,\s*Pay\s+\d+\s+life)?)")
    for m in pat.finditer(text):
        restriction_word, mana, addl = m.group(1), m.group(2), m.group(3).strip()
        # a bare "Equip {N} ({N}: Attach ...)" reminder repeats the cost; the regex only
        # matches the printed "Equip {N}" (reminder text is inside parens, "{N}:" form).
        restriction = None
        if restriction_word and restriction_word.lower() != "pay":
            restriction = restriction_word.lower()      # e.g. "wizard"
        additional_cost = None
        am = re.search(r"Pay\s+(\d+)\s+life", addl)
        if am:
            additional_cost = {"kind": "pay_life", "amount": int(am.group(1))}
        modes.append({"mana_cost": mana, "additional_cost": additional_cost,
                      "restriction": restriction, "raw": m.group(0).strip()})
    # order: the plain (unrestricted) mode first, restricted alternative modes after, so the
    # "primary" equip ability id is stable regardless of print order.
    modes.sort(key=lambda d: (d["restriction"] is not None, d["restriction"] or "", d["mana_cost"]))
    for i, mode in enumerate(modes):
        mode["alternative"] = i > 0
    return modes


def _parse_pt(oracle: str):
    """Return (power, toughness) strings like ('+2','+2') for 'Equipped creature gets +X/+Y',
    or None."""
    text = _clean(oracle)
    m = re.search(r"Equipped creature gets ([+\-]\d+)/([+\-]\d+)", text)
    return (m.group(1), m.group(2)) if m else None


def _parse_granted_keywords(oracle: str) -> list:
    """Keywords/abilities the 'Equipped creature ... has <kw>' line grants."""
    text = _clean(oracle).lower()
    # only look at the "equipped creature ... has ..." clauses
    granted = []
    for sent in re.split(r"(?<=[.\n])", text):
        if "equipped creature" not in sent or " has " not in sent and " and has " not in sent:
            continue
        for token, label in _KEYWORDS:
            if re.search(r"\b" + re.escape(token), sent):
                granted.append(label)
        # ward {N}
        wm = re.search(r"ward \{(\d+)\}", sent)
        if wm:
            granted.append("ward {%s}" % wm.group(1))
    # stable, de-duplicated
    seen, out = set(), []
    for g in granted:
        if g not in seen:
            seen.add(g)
            out.append(g)
    return sorted(out)


# ETB-attach oracle signatures -> (kind description, target restriction condition/object)
def _auto_attach_spec(oracle: str):
    """If the Equipment attaches automatically on ETB, return a dict describing it, else None.
    Distinct from the Equip activation (kind='automatic', trigger='etb')."""
    text = _clean(oracle).lower()
    if "attach sting" in text and "target creature you control" in text:
        return {"kind": "automatic", "trigger": "etb", "target": "up to one target creature you control",
                "restriction_object": OBJ_CREATURE_YOU_CONTROL, "restriction_condition": None}
    if "create a 2/2" in text and "attach this equipment to it" in text:
        return {"kind": "automatic", "trigger": "etb", "target": "the created 2/2 Dwarf token",
                "restriction_object": OBJ_CREATURE_YOU_CONTROL, "restriction_condition": None,
                "creates": "2/2 red Dwarf creature token"}
    if "amass goblins" in text and "attach this equipment to the amassed army" in text:
        return {"kind": "automatic", "trigger": "etb", "target": "the amassed Goblin Army",
                "restriction_object": OBJ_CREATURE_YOU_CONTROL, "restriction_condition": None,
                "amass": "Goblins 1"}
    if "attach it to target dwarf you control" in text:
        return {"kind": "automatic", "trigger": "etb", "target": "target Dwarf you control",
                "restriction_object": OBJ_SUBTYPE_DWARF,
                "restriction_condition": COND_AUTO_ATTACH_TARGET_IS_DWARF}
    return None


# --------------------------------------------------------------------------- #
#  materialize                                                                 #
# --------------------------------------------------------------------------- #
def materialize(repo: Path = REPO) -> dict:
    g = _G(repo)
    nodes: dict = {}
    edges: list = []
    conditions: dict = {}

    def add_cond(cid, executable, expression, human, note):
        conditions.setdefault(cid, {
            "condition_id": cid, "executable": executable, "expression": expression,
            "human_readable": human,
            "provenance": [{"source": "equip", "derivation": note}], "origin": "equip"})

    # shared conditions (referenced on many CAN_ATTACH_TO relations)
    add_cond(COND_TARGET_CONTROLLED, True,
             {"op": "controls", "subject": "activator", "object": "attachment_target"},
             "The Equip target must be a creature the activating player controls.",
             "equip target controller restriction")
    add_cond(COND_SORCERY_TIMING, True,
             {"op": "timing", "restriction": "sorcery_speed"},
             "Equip may be activated only any time you could cast a sorcery.",
             "equip sorcery-speed timing restriction")
    add_cond(COND_TARGET_IS_WIZARD, True,
             {"op": "has_subtype", "subject": "attachment_target", "subtype": "wizard"},
             "This alternative Equip mode may target only a Wizard creature you control.",
             "Wizard's Staff alternative equip restriction")
    add_cond(COND_AUTO_ATTACH_TARGET_IS_DWARF, True,
             {"op": "has_subtype", "subject": "attachment_target", "subtype": "dwarf"},
             "The automatic (ETB) attachment targets a Dwarf you control.",
             "Dwarven Mattock auto-attach target restriction")

    stats_cards = 0
    for face in g.equipment_faces():
        E = face["id"]
        name = face.get("name") or E
        slug = _slug(name)
        oracle = face.get("oracle_text") or ""
        stats_cards += 1

        # ---- the bound attachment State + the bound creature ObjectClass ----------------
        state = f"state:attachment:{E}"
        bound = f"obj:bound-creature:{E}"
        cond_attached = f"cond:equipment-{slug}-attached"
        nodes[state] = _node(
            state, "State", f"{name} attached", {
                "equipment": name, "equipment_face": E,
                "attached_object": "bound C (variable creature)",
                "controller_constraint": "target creature you control",
                "timing": "sorcery"},
            "the bound attachment state for this Equipment (one per Equipment, C is a variable)")
        nodes[bound] = _node(
            bound, "ObjectClass", f"creature equipped by {name}",
            {"equipment": name, "equipment_face": E, "kind": "bound_creature_variable"},
            "the (variable) creature bound by this Equipment's attachment")
        add_cond(cond_attached, True,
                 {"op": "attached", "equipment": E},
                 f"{name} is attached to the creature (the bound attachment state holds).",
                 "per-equipment attachment state condition")

        # ---- the Equip activated ability(es) -------------------------------------------
        modes = _parse_equip_costs(oracle)
        if not modes:                                    # defensive; every Equipment prints one
            modes = [{"mana_cost": None, "additional_cost": None, "restriction": None,
                      "alternative": False, "raw": "Equip"}]
        primary_op = None
        for mode in modes:
            alt = mode["alternative"]
            suffix = "equip-alt" if alt else "equip"
            ability = f"ability:{suffix}:{E}"
            cost = f"cost:{suffix}:{E}"
            op = f"op:{suffix}:{E}"
            if not alt:
                primary_op = op

            nodes[ability] = _node(
                ability, "Ability", f"equip{' (alt)' if alt else ''}: {name}",
                {"equipment": name, "mode": ("alternative" if alt else "primary"),
                 "restriction": mode["restriction"], "keyword": "equip"},
                "the Equip activated ability" + (" (alternative restricted mode)" if alt else ""))
            nodes[cost] = _node(
                cost, "Cost", f"equip cost: {mode['raw']}",
                {"mana_cost": mode["mana_cost"], "additional_cost": mode["additional_cost"],
                 "raw": mode["raw"], "alternative": alt}, "printed Equip cost (preserved verbatim)")
            # target restriction object: alt mode may add a subtype restriction (e.g. Wizard)
            req_obj = OBJ_CREATURE_YOU_CONTROL
            mode_conds = [COND_TARGET_CONTROLLED, COND_SORCERY_TIMING]
            op_data = {"kind": "equip_activation", "equipment": name, "mode": ("alternative" if alt else "primary"),
                       "timing": "sorcery", "attaches": state}
            if mode["restriction"] == "wizard":
                req_obj = OBJ_SUBTYPE_WIZARD
                mode_conds = [COND_TARGET_CONTROLLED, COND_SORCERY_TIMING, COND_TARGET_IS_WIZARD]
                op_data["target_restriction"] = "wizard"
            nodes[op] = _node(op, "Operation", f"equip{' (alt)' if alt else ''} {name}", op_data,
                              "the equip attachment operation for this mode")

            edges.append(_edge(E, "HAS_ABILITY", ability, "the Equipment's Equip activated ability"))
            edges.append(_edge(ability, "HAS_COST", cost, "the printed Equip cost is a cost of the Equip ability"))
            edges.append(_edge(E, "REFERENCES_RULE", RULE_EQUIP, "Equip is a keyworded activated ability"))
            edges.append(_edge(ability, "CAUSES", op, "activating Equip performs the attachment operation"))
            edges.append(_edge(op, "REQUIRES", req_obj,
                               "the equip target is a creature the activator controls"
                               + (" that is a Wizard" if req_obj == OBJ_SUBTYPE_WIZARD else ""),
                               condition_ids=list(mode_conds)))
            edges.append(_edge(op, "CAUSES", state,
                               "resolving the Equip ability attaches the Equipment to the bound creature",
                               condition_ids=[cond_attached]))

        # ---- automatic (ETB) attachment, DISTINCT from the equip activation -------------
        auto = _auto_attach_spec(oracle)
        if auto:
            aa_ability = f"ability:auto-attach:{E}"
            aa_op = f"op:auto-attach:{E}"
            nodes[aa_ability] = _node(
                aa_ability, "Ability", f"auto-attach (ETB): {name}",
                {"equipment": name, "kind": "automatic", "trigger": "etb"},
                "the triggered ability that attaches this Equipment automatically on entry")
            aa_data = {"kind": "automatic", "trigger": "etb", "equipment": name,
                       "target": auto["target"], "attaches": state}
            for k in ("creates", "amass"):
                if auto.get(k):
                    aa_data[k] = auto[k]
            nodes[aa_op] = _node(aa_op, "Operation", f"auto-attach {name}", aa_data,
                                 "the automatic (ETB) attachment operation — NOT the equip activation")
            aa_conds = [cond_attached]
            if auto.get("restriction_condition"):
                aa_conds = [cond_attached, auto["restriction_condition"]]
            edges.append(_edge(aa_ability, "CAUSES", aa_op,
                               "the ETB trigger performs the automatic attachment"))
            edges.append(_edge(aa_op, "REQUIRES", auto["restriction_object"],
                               "the automatic attachment binds a controlled creature"
                               + (" that is a Dwarf" if auto["restriction_object"] == OBJ_SUBTYPE_DWARF else ""),
                               condition_ids=list(aa_conds)))
            edges.append(_edge(aa_op, "CAUSES", state,
                               "the automatic (ETB) attachment reaches the SAME bound attachment state",
                               condition_ids=[cond_attached]))

        # ---- continuous "equipped creature" P/T modification ----------------------------
        pt = _parse_pt(oracle)
        if pt:
            mod_ability = f"ability:equipped-bonus:{E}"
            mod_op = f"op:modify-equipped:{E}"
            nodes[mod_ability] = _node(
                mod_ability, "Ability", f"equipped-creature bonus: {name}",
                {"equipment": name, "kind": "static_pt_bonus"},
                "the static ability granting the equipped creature a P/T bonus")
            nodes[mod_op] = _node(
                mod_op, "Operation", f"modify equipped creature: {name}",
                {"kind": "modify_equipped", "equipment": name,
                 "modification": {"power": pt[0], "toughness": pt[1]}},
                "the operation applying the equipped-creature P/T modification")
            edges.append(_edge(mod_ability, "CAUSES", mod_op, "the static bonus is applied by this operation"))
            edges.append(_edge(mod_op, "REQUIRES", state,
                               "the bonus applies only while the Equipment is attached",
                               condition_ids=[cond_attached]))
            edges.append(_edge(mod_op, "MODIFIES", bound,
                               "modifies the bound (equipped) creature",
                               modification={"power": pt[0], "toughness": pt[1]},
                               condition_ids=[cond_attached]))

        # ---- continuous granted keywords/abilities --------------------------------------
        granted = _parse_granted_keywords(oracle)
        if granted:
            grant_ability = f"ability:equipped-grant:{E}"
            nodes[grant_ability] = _node(
                grant_ability, "Ability", f"equipped-creature grants: {name}",
                {"equipment": name, "kind": "static_grant", "granted": granted},
                "the static ability granting the equipped creature keyword abilities")
            edges.append(_edge(grant_ability, "CAUSES", f"op:grant-equipped:{E}",
                               "the grant is applied by this operation"))
            grant_op = f"op:grant-equipped:{E}"
            nodes[grant_op] = _node(
                grant_op, "Operation", f"grant to equipped creature: {name}",
                {"kind": "grant_equipped", "equipment": name, "granted_abilities": granted},
                "the operation granting the equipped-creature keyword abilities")
            edges.append(_edge(grant_op, "REQUIRES", state,
                               "the granted abilities apply only while attached",
                               condition_ids=[cond_attached]))
            edges.append(_edge(grant_op, "MODIFIES", bound,
                               "grants keyword abilities to the bound (equipped) creature",
                               granted_abilities=granted, condition_ids=[cond_attached]))

    # ---- write + validate ---------------------------------------------------------------
    outdir = repo / "data" / "graph_global"
    # drop null-valued props (e.g. condition_ids=None) so records stay clean/deterministic
    cleaned = []
    for e in edges:
        cleaned.append({k: v for k, v in e.items() if v is not None})
    uniq = {}
    for e in cleaned:
        uniq.setdefault(e["edge_id"], e)
    edges = sorted(uniq.values(), key=lambda e: (e["source"], e["predicate"], e["target"]))

    with (outdir / "equip_nodes.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for n in sorted(nodes.values(), key=lambda n: n["id"]):
            fh.write(json.dumps(n, ensure_ascii=False, sort_keys=True) + "\n")
    with (outdir / "equip_edges.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for e in edges:
            fh.write(json.dumps(e, ensure_ascii=False, sort_keys=True) + "\n")
    with (outdir / "equip_conditions.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for c in sorted(conditions.values(), key=lambda c: c["condition_id"]):
            fh.write(json.dumps(c, ensure_ascii=False, sort_keys=True) + "\n")

    from .graph_repair import _validate_repair_layer
    violations = _validate_repair_layer(repo, g.nodes, nodes, edges)
    defined = {c["condition_id"] for c in _load_dicts(repo / "data/graph_global/conditions.jsonl")}
    defined |= set(conditions)
    referenced = {c for e in edges for c in (e.get("condition_ids") or [])}
    unresolved = sorted(referenced - defined)
    return {"equip_cards": stats_cards, "equip_nodes": len(nodes), "equip_edges": len(edges),
            "equip_conditions": len(conditions), "unresolved_conditions": unresolved,
            "signature_violations": len(violations), "_violations": violations}


# --------------------------------------------------------------------------- #
#  Reprojection: faithful typed paths over graph + equip layer                 #
# --------------------------------------------------------------------------- #
def reproject(repo: Path = REPO) -> dict:
    g = _G(repo)
    eq_nodes = {n["id"]: n for n in _load_dicts(repo / "data/graph_global/equip_nodes.jsonl")}
    eq_edges = list(_load_dicts(repo / "data/graph_global/equip_edges.jsonl"))
    all_edges = g.edges + eq_edges
    eq_ids = {e["edge_id"] for e in eq_edges}
    real_ids = {e["edge_id"] for e in g.edges}

    def find(source=None, predicate=None, target=None, cond=None):
        for e in all_edges:
            if (source is None or e["source"] == source) and (predicate is None or e["predicate"] == predicate) \
                    and (target is None or e["target"] == target):
                if cond is not None and cond not in (e.get("condition_ids") or []):
                    continue
                return e
        return None

    # populations over the frozen graph
    def _pop(target):
        return sorted({c for e in g.edges if e["predicate"] == "HAS_TYPE" and e["target"] == target
                       for c in [_card_of(e["source"])] if c})
    creature_cards = _pop(OBJ_TYPE_CREATURE)
    wizard_cards = set(_pop(OBJ_SUBTYPE_WIZARD))
    # HAS_TYPE edge per creature card (one representative), so the projected path is grounded
    creature_htype = {}
    for e in g.edges:
        if e["predicate"] == "HAS_TYPE" and e["target"] == OBJ_TYPE_CREATURE:
            creature_htype.setdefault(_card_of(e["source"]), e)
    wizard_htype = {}
    for e in g.edges:
        if e["predicate"] == "HAS_TYPE" and e["target"] == OBJ_SUBTYPE_WIZARD:
            wizard_htype.setdefault(_card_of(e["source"]), e)

    metaedges = []

    def emit(a_card, b_card, relation, steps, equip_cost, extra):
        if not a_card or not b_card or a_card == b_card:
            return
        nodes_seq = [steps[0]["source"]] + [s["target"] for s in steps]
        conds = sorted({c for s in steps for c in (s.get("condition_ids") or [])})
        m = {"source_card": a_card, "target_card": b_card, "relation": relation, "origin": "equip",
             "path_kind": "grounded", "steps": steps, "primitive_path": nodes_seq,
             "path_predicates": [s["predicate"] for s in steps],
             "edge_ids": [s["edge_id"] for s in steps],
             "uses_equip_edges": [s["edge_id"] for s in steps if s["edge_id"] in eq_ids],
             "connecting_node": nodes_seq[1], "condition_ids": conds}
        if equip_cost is not None:
            m["equip_cost"] = equip_cost
        if extra:
            m.update(extra)
        metaedges.append(m)

    for face in g.equipment_faces():
        E = face["id"]
        e_card = _card_of(E)
        state = f"state:attachment:{E}"
        bound = f"obj:bound-creature:{E}"
        n_cost = eq_nodes.get(f"cost:equip:{E}", {}).get("data", {})
        equip_cost = {"mana_cost": n_cost.get("mana_cost"), "additional_cost": n_cost.get("additional_cost"),
                      "raw": n_cost.get("raw")}

        # ---- CAN_ATTACH_TO (primary equip mode: any creature you control) ---------------
        ab_equip = find(source=E, predicate="HAS_ABILITY", target=f"ability:equip:{E}")
        causes = find(source=f"ability:equip:{E}", predicate="CAUSES", target=f"op:equip:{E}")
        requires = find(source=f"op:equip:{E}", predicate="REQUIRES", target=OBJ_CREATURE_YOU_CONTROL)
        if ab_equip and causes and requires:
            for c_card in creature_cards:
                htype = creature_htype.get(c_card)
                if not htype:
                    continue
                steps = [project._step(ab_equip, "forward"), project._step(causes, "forward"),
                         project._step(requires, "forward"), project._step(htype, "reverse")]
                emit(e_card, c_card, "CAN_ATTACH_TO", steps, equip_cost, {"equip_mode": "primary"})

        # ---- CAN_ATTACH_TO (Wizard's Staff alt mode: only Wizard creatures) -------------
        ab_alt = find(source=E, predicate="HAS_ABILITY", target=f"ability:equip-alt:{E}")
        causes_alt = find(source=f"ability:equip-alt:{E}", predicate="CAUSES", target=f"op:equip-alt:{E}")
        req_alt = find(source=f"op:equip-alt:{E}", predicate="REQUIRES", target=OBJ_SUBTYPE_WIZARD)
        if ab_alt and causes_alt and req_alt:
            alt_cost_n = eq_nodes.get(f"cost:equip-alt:{E}", {}).get("data", {})
            alt_cost = {"mana_cost": alt_cost_n.get("mana_cost"),
                        "additional_cost": alt_cost_n.get("additional_cost"), "raw": alt_cost_n.get("raw")}
            for c_card in sorted(wizard_cards):
                htype = wizard_htype.get(c_card)
                if not htype:
                    continue
                steps = [project._step(ab_alt, "forward"), project._step(causes_alt, "forward"),
                         project._step(req_alt, "forward"), project._step(htype, "reverse")]
                emit(e_card, c_card, "CAN_ATTACH_TO", steps, alt_cost, {"equip_mode": "alternative-wizard"})

        # ---- MODIFIES_WHEN_ATTACHED (P/T modification through the attachment) ------------
        mod = find(source=f"op:modify-equipped:{E}", predicate="MODIFIES", target=bound)
        state_link = find(source=f"op:modify-equipped:{E}", predicate="REQUIRES", target=state)
        if mod and state_link:
            for c_card in creature_cards:
                htype = creature_htype.get(c_card)
                if not htype:
                    continue
                # path: attachment state <-REQUIRES- modify-op -MODIFIES-> bound-creature ; C is a creature
                steps = [project._step(state_link, "reverse"), project._step(mod, "forward")]
                emit(e_card, c_card, "MODIFIES_WHEN_ATTACHED", steps, equip_cost,
                     {"modification": mod.get("modification"), "attachment_state": state,
                      "bound_creature": bound})

        # ---- GRANTS_ABILITY_WHEN_ATTACHED (keyword grants through the attachment) --------
        grant = find(source=f"op:grant-equipped:{E}", predicate="MODIFIES", target=bound)
        grant_state = find(source=f"op:grant-equipped:{E}", predicate="REQUIRES", target=state)
        if grant and grant_state:
            for kw in (grant.get("granted_abilities") or []):
                for c_card in creature_cards:
                    htype = creature_htype.get(c_card)
                    if not htype:
                        continue
                    steps = [project._step(grant_state, "reverse"), project._step(grant, "forward")]
                    emit(e_card, c_card, "GRANTS_ABILITY_WHEN_ATTACHED", steps, equip_cost,
                         {"granted_ability": kw, "attachment_state": state, "bound_creature": bound})

    metaedges.sort(key=lambda m: (m["source_card"], m["target_card"], m["relation"],
                                  m.get("granted_ability") or "", m["connecting_node"]))
    with (repo / "data/graph_global/card_pair_projection_equip.jsonl").open(
            "w", encoding="utf-8", newline="\n") as fh:
        for m in metaedges:
            fh.write(json.dumps(m, ensure_ascii=False, sort_keys=True) + "\n")

    edges_resolve = all(s["edge_id"] in real_ids or s["edge_id"] in eq_ids
                        for m in metaedges for s in m["steps"])
    by_rel = {}
    for m in metaedges:
        by_rel[m["relation"]] = by_rel.get(m["relation"], 0) + 1
    _report(repo, g, metaedges, by_rel, edges_resolve)
    return {"reprojected": len(metaedges), "by_relation": by_rel, "edges_resolve": edges_resolve}


def _report(repo, g, metaedges, by_rel, ok):
    L = ["# HOB Equip Attachment Layer — Materialization + Reprojection", "",
         f"- **reprojected metaedges**: {len(metaedges)} (origin `equip`)",
         f"- **by relation**: {by_rel}",
         f"- **all path edges resolve (frozen or equip layer)**: {ok}", "",
         "## Sample relations (origin: equip)", ""]
    shown = 0
    for m in metaedges:
        if shown >= 60:
            L.append("- … (truncated)")
            break
        a = g.names.get(m["source_card"], m["source_card"])
        b = g.names.get(m["target_card"], m["target_card"])
        detail = ""
        if m.get("modification"):
            detail = f"  _(mod: {m['modification']})_"
        elif m.get("granted_ability"):
            detail = f"  _(grants: {m['granted_ability']})_"
        elif m.get("equip_cost"):
            detail = f"  _(cost: {m['equip_cost'].get('raw')})_"
        conds = f"  _(cond: {', '.join(m['condition_ids'])})_" if m.get("condition_ids") else ""
        L.append(f"- **{a} -> {b}** [{m['relation']}] via `{m['connecting_node']}` "
                 f"— {' -> '.join(m['path_predicates'])}{detail}{conds}")
        shown += 1
    (repo / "reports" / "equip.md").write_text("\n".join(L) + "\n", encoding="utf-8")

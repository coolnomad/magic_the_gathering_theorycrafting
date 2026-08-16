"""Additive Equip attachment layer for "The Hobbit" Equipment (rebuilt for pt5).

Models the objective, directed capacity: *Equipment E can legally attach to creature C, and
while E is attached to C, E's "equipped creature" effects apply to C.* NOT synergy. Distinguishes
the capacity to Equip, the attachment action, the resulting attachment state, effects conditional
on that state, and special automatic (ETB) attachment — see spec §Phase 2 Equip.

Additive layer (`data/graph_global/equip_{nodes,edges,conditions}.jsonl`, origin `equip`); the
frozen graph and every other layer are untouched. The reusable template binds the target creature
C as a VARIABLE (one `state:attachment:E` / `obj:bound-creature:E` per Equipment):

    card:E -HAS_FACE-> face:E -HAS_ABILITY-> ability:equip:E -HAS_COST-> cost:equip:E
    face:E -REFERENCES_RULE-> rule:equip
    ability:equip:E -CAUSES-> op:equip:E -REQUIRES-> obj:creature-you-control -HAS_TYPE-> obj:type:creature
    op:equip:E -CAUSES-> state:attachment:E                       (attachment is the RESULT, uncond.)
    face:E -HAS_ABILITY-> ability:equipped-bonus:E -CAUSES-> op:modify-equipped:E
    op:modify-equipped:E -REQUIRES-> state:attachment:E ; -MODIFIES-> obj:bound-creature:E
    obj:bound-creature:E -HAS_TYPE-> obj:type:creature            (binding: the bound C is a creature)

pt5 correctness properties, all self-checked in reproject() and gated by tests:
  * every projected relation is a CONTINUOUS path (step[i].target == step[i+1].source),
    grounded card:E ... card:C (path[0].source == source_card, path[-1].target == target_card);
  * equipped-bonus / grant / auto-attach abilities each have an incoming face HAS_ABILITY;
  * no operation REQUIRES the state it CAUSES (attachment is a result, not a precondition);
  * the `token:axe` Equipment (no card face) gets primitive template coverage + creator projection;
  * every equip node/edge carries exact Oracle-span provenance;
  * every printed "equipped creature" clause is dispositioned (represented / ignored / unresolved).
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
TOKEN_AXE = "token:axe"
_CR_EQUIP = "CR 301.5 (Equipment) / 702.6 (Equip)"

COND_TARGET_CONTROLLED = "cond:equip-target-controlled-by-activator"
COND_SORCERY_TIMING = "cond:equip-sorcery-timing"
COND_TARGET_IS_WIZARD = "cond:equip-target-is-wizard"
COND_AUTO_ATTACH_TARGET_IS_DWARF = "cond:auto-attach-target-is-dwarf"

_KEYWORDS = [
    "hexproof", "trample", "reach", "menace", "prowess", "flying", "vigilance", "lifelink",
    "deathtouch", "first strike", "double strike", "indestructible", "haste", "can't be blocked",
]


def _card_of(nid: str):
    m = _UUID.search(nid or "")
    return "card:" + m.group(0) if m else None


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")


def _mid(source: str, predicate: str, target: str) -> str:
    return "e" + hashlib.sha1(f"{source}|{predicate}|{target}".encode("utf-8")).hexdigest()[:15]


def _step(edge: dict, direction: str) -> dict:
    """A lean path step: keeps the edge_id (so provenance is retrievable from the edge), the
    predicate, traversed endpoints, direction, and semantic props — but NOT the full provenance
    blob (embedding it in every step of 3,250 long paths bloats the projection ~10x and is
    redundant, since each step's edge_id resolves to the edge that carries the provenance)."""
    s = project._step(edge, direction)
    s.pop("provenance", None)
    return s


class _G:
    def __init__(self, repo: Path):
        self.nodes = {n["id"]: n for n in _load_dicts(repo / "data/graph_global/nodes.jsonl")}
        self.edges = list(_load_dicts(repo / "data/graph_global/edges.jsonl"))
        self.faces = list(_load_dicts(repo / "data/normalized/faces.jsonl"))
        self.face_by_id = {f["id"]: f for f in self.faces}
        self.names = {c["id"]: c["name"] for c in _load_dicts(repo / "data/normalized/cards.jsonl")}
        self.hasface = {e["target"]: e for e in self.edges if e["predicate"] == "HAS_FACE"}  # face -> edge

    def equipment_faces(self) -> list:
        ids = sorted({e["source"] for e in self.edges
                      if e["predicate"] == "HAS_TYPE" and e["target"] == "obj:subtype:equipment"
                      and e["source"] in self.face_by_id})
        return [self.face_by_id[i] for i in ids]


# --------------------------------------------------------------------------- #
#  Oracle parsing (returns spans for provenance)                               #
# --------------------------------------------------------------------------- #
_JUNK_SEP = re.compile("[ —�]")


def _clean(text: str) -> str:
    # normalize stray separators glued to "Equip" to a plain space, PRESERVING length/offsets
    return _JUNK_SEP.sub(" ", text or "")


def _parse_equip_costs(oracle: str) -> list:
    text = _clean(oracle)
    modes = []
    pat = re.compile(r"Equip(?:\s+([A-Za-z]+))?\s*(\{[^}]+\}(?:\{[^}]+\})*)((?:,\s*Pay\s+\d+\s+life)?)")
    for m in pat.finditer(text):
        restriction_word, mana, addl = m.group(1), m.group(2), m.group(3).strip()
        restriction = restriction_word.lower() if (restriction_word and restriction_word.lower() != "pay") else None
        am = re.search(r"Pay\s+(\d+)\s+life", addl)
        additional_cost = {"kind": "pay_life", "amount": int(am.group(1))} if am else None
        modes.append({"mana_cost": mana, "additional_cost": additional_cost, "restriction": restriction,
                      "raw": m.group(0).strip(), "span": [m.start(), m.end()]})
    modes.sort(key=lambda d: (d["restriction"] is not None, d["restriction"] or "", d["mana_cost"]))
    for i, mode in enumerate(modes):
        mode["alternative"] = i > 0
    return modes


def _parse_pt(oracle: str):
    m = re.search(r"Equipped creature gets ([+\-]\d+)/([+\-]\d+)", _clean(oracle))
    return (m.group(1), m.group(2), [m.start(), m.end()]) if m else None


def _equipped_clauses(oracle: str) -> list:
    """Every printed sentence that REFERS to the equipped creature (anywhere in the sentence,
    not only those starting with 'Equipped creature'), with its span — so complex effects like
    Glamdring's cost reduction and Orcrist's combat trigger are captured for disposition."""
    text = _clean(oracle)
    out, pos = [], 0
    for m in re.finditer(r"[^.]*equipped creature[^.]*\.", text, flags=re.IGNORECASE):
        out.append({"text": m.group(0).strip(), "span": [m.start(), m.end()]})
    return out


def _parse_granted_keywords(oracle: str) -> list:
    """(keyword, span) grants from 'Equipped creature ... has <kw>' clauses."""
    out, seen = [], set()
    for cl in _equipped_clauses(oracle):
        low = cl["text"].lower()
        if " has " not in low:
            continue
        for kw in _KEYWORDS:
            if re.search(r"\b" + re.escape(kw), low) and kw not in seen:
                seen.add(kw)
                out.append((kw, cl["span"]))
        wm = re.search(r"ward \{(\d+)\}", low)
        if wm and ("ward {%s}" % wm.group(1)) not in seen:
            seen.add("ward {%s}" % wm.group(1))
            out.append(("ward {%s}" % wm.group(1), cl["span"]))
    return out


def _auto_attach_spec(oracle: str):
    text = _clean(oracle).lower()
    m = re.search(r"(attach [^.]*\.)", text)
    span = [m.start(), m.end()] if m else None
    if "attach sting" in text and "target creature you control" in text:
        return {"target": "up to one target creature you control", "restriction_object": OBJ_CREATURE_YOU_CONTROL,
                "restriction_condition": None, "span": span}
    if "create a 2/2" in text and "attach this equipment to it" in text:
        return {"target": "the created 2/2 Dwarf token", "restriction_object": OBJ_CREATURE_YOU_CONTROL,
                "restriction_condition": None, "creates": "2/2 red Dwarf creature token", "span": span}
    if "amass goblins" in text and "attach this equipment to the amassed army" in text:
        return {"target": "the amassed Goblin Army", "restriction_object": OBJ_CREATURE_YOU_CONTROL,
                "restriction_condition": None, "amass": "Goblins 1", "span": span}
    if "attach it to target dwarf you control" in text:
        return {"target": "target Dwarf you control", "restriction_object": OBJ_SUBTYPE_DWARF,
                "restriction_condition": COND_AUTO_ATTACH_TARGET_IS_DWARF, "span": span}
    return None


# --------------------------------------------------------------------------- #
#  materialize                                                                 #
# --------------------------------------------------------------------------- #
def materialize(repo: Path = REPO) -> dict:
    g = _G(repo)
    nodes: dict = {}
    edges: list = []
    conditions: dict = {}
    dispositions: list = []                              # per equipped-creature clause

    def prov(face_id, span, text, note):
        p = {"source": "equip", "rule_ref": _CR_EQUIP, "derivation": note}
        if face_id:
            p["face_id"] = face_id
        if span and face_id:                             # a span is an offset into a face's Oracle
            p["oracle_span"] = span
        if text:
            p["text"] = text
        return p

    def node(nid, ntype, label, data, provs):
        nodes.setdefault(nid, {"id": nid, "type": ntype, "label": label, "data": data,
                               "provenance": provs, "origin": "equip"})

    def edge(source, predicate, target, provs, **props):
        edges.append({"edge_id": _mid(source, predicate, target), "source": source,
                      "predicate": predicate, "target": target, "provenance": provs,
                      "origin": "equip", **props})

    def add_cond(cid, expression, human, note):
        conditions.setdefault(cid, {"condition_id": cid, "executable": True, "expression": expression,
                                    "human_readable": human,
                                    "provenance": [{"source": "equip", "rule_ref": _CR_EQUIP, "derivation": note}],
                                    "origin": "equip"})

    add_cond(COND_TARGET_CONTROLLED, {"op": "controls", "subject": "activator", "object": "attachment_target"},
             "The Equip target must be a creature the activating player controls.", "equip target controller")
    add_cond(COND_SORCERY_TIMING, {"op": "timing", "restriction": "sorcery_speed"},
             "Equip may be activated only any time you could cast a sorcery.", "equip sorcery timing")
    add_cond(COND_TARGET_IS_WIZARD, {"op": "has_subtype", "subject": "attachment_target", "subtype": "wizard"},
             "This alternative Equip mode may target only a Wizard creature you control.", "wizard equip restriction")
    add_cond(COND_AUTO_ATTACH_TARGET_IS_DWARF, {"op": "has_subtype", "subject": "attachment_target", "subtype": "dwarf"},
             "The automatic (ETB) attachment targets a Dwarf you control.", "mattock auto-attach restriction")

    # shared binding edge: a controlled creature IS a creature (connects equip REQUIRES -> creature type)
    node(OBJ_CREATURE_YOU_CONTROL, "ObjectClass", "creature you control",
         {"type_kind": "role", "base_type": "creature"}, [prov(None, None, None, "equip target class")])
    edge(OBJ_CREATURE_YOU_CONTROL, "HAS_TYPE", OBJ_TYPE_CREATURE,
         [prov(None, None, None, "a creature you control is a creature (grounding binding)")])

    def build_equip_template(host, host_kind, name, slug, oracle, face_id):
        """Materialize the Equip template for a host that carries the Equipment (a card face E,
        or the token:axe TokenSpec). `host` is the node the template hangs off (HAS_ABILITY source)."""
        state = f"state:attachment:{host}"
        bound = f"obj:bound-creature:{host}"
        cond_attached = f"cond:equipment-{slug}-attached"
        node(state, "State", f"{name} attached",
             {"equipment": name, "equipment_host": host, "attached_object": "bound C (variable creature)",
              "controller_constraint": "target creature you control", "timing": "sorcery"},
             [prov(face_id, None, None, "bound attachment state (one per Equipment; C is a variable)")])
        node(bound, "ObjectClass", f"creature equipped by {name}",
             {"equipment": name, "kind": "bound_creature_variable"},
             [prov(face_id, None, None, "the variable creature bound by this Equipment")])
        # binding: the bound creature is a creature (grounds modify/grant paths to creature cards)
        edge(bound, "HAS_TYPE", OBJ_TYPE_CREATURE,
             [prov(face_id, None, None, "the equipped (bound) creature is a creature")])
        add_cond(cond_attached, {"op": "attached", "equipment": host},
                 f"{name} is attached to the creature (the bound attachment state holds).",
                 "per-equipment attachment state")

        modes = _parse_equip_costs(oracle) or [{"mana_cost": None, "additional_cost": None,
                                                 "restriction": None, "alternative": False,
                                                 "raw": "Equip", "span": None}]
        for mode in modes:
            alt = mode["alternative"]
            suffix = "equip-alt" if alt else "equip"
            ability, cost, op = f"ability:{suffix}:{host}", f"cost:{suffix}:{host}", f"op:{suffix}:{host}"
            p_cost = [prov(face_id, mode.get("span"), mode["raw"], "printed Equip cost")]
            node(ability, "Ability", f"equip{' (alt)' if alt else ''}: {name}",
                 {"equipment": name, "mode": "alternative" if alt else "primary",
                  "restriction": mode["restriction"], "keyword": "equip"}, p_cost)
            node(cost, "Cost", f"equip cost: {mode['raw']}",
                 {"mana_cost": mode["mana_cost"], "additional_cost": mode["additional_cost"],
                  "raw": mode["raw"], "alternative": alt}, p_cost)
            req_obj = OBJ_CREATURE_YOU_CONTROL
            mode_conds = [COND_TARGET_CONTROLLED, COND_SORCERY_TIMING]
            op_data = {"kind": "equip_activation", "mode": "alternative" if alt else "primary",
                       "equipment": name, "timing": "sorcery", "attaches": state}
            if mode["restriction"] == "wizard":
                req_obj, mode_conds = OBJ_SUBTYPE_WIZARD, [COND_TARGET_CONTROLLED, COND_SORCERY_TIMING, COND_TARGET_IS_WIZARD]
                op_data["target_restriction"] = "wizard"
            node(op, "Operation", f"equip{' (alt)' if alt else ''} {name}", op_data,
                 [prov(face_id, mode.get("span"), mode["raw"], "equip attachment operation")])
            edge(host, "HAS_ABILITY", ability, [prov(face_id, mode.get("span"), mode["raw"], "the Equip activated ability")])
            edge(ability, "HAS_COST", cost, p_cost)
            # REFERENCES_RULE from the CardFace (spec convention) for cards; from the Ability for
            # the token:axe TokenSpec (TokenSpec is not a valid REFERENCES_RULE source).
            ref_source = host if host_kind == "face" else ability
            edge(ref_source, "REFERENCES_RULE", RULE_EQUIP, [prov(face_id, mode.get("span"), "Equip", "Equip is a keyworded ability")])
            edge(ability, "CAUSES", op, [prov(face_id, mode.get("span"), mode["raw"], "activating Equip performs attachment")])
            edge(op, "REQUIRES", req_obj,
                 [prov(face_id, mode.get("span"), mode["raw"], "equip target is a controlled creature"
                       + (" that is a Wizard" if req_obj == OBJ_SUBTYPE_WIZARD else ""))],
                 condition_ids=list(mode_conds))
            # attachment is the RESULT of Equip — NOT conditioned on already being attached (no circular cond)
            edge(op, "CAUSES", state, [prov(face_id, mode.get("span"), mode["raw"],
                                            "resolving Equip attaches the Equipment to the bound creature")])
        return state, bound, cond_attached

    stats_cards = 0
    for face in g.equipment_faces():
        E, name = face["id"], (face.get("name") or face["id"])
        slug, oracle = _slug(name), (face.get("oracle_text") or "")
        stats_cards += 1
        state, bound, cond_attached = build_equip_template(E, "face", name, slug, oracle, E)

        # ---- automatic (ETB) attachment, DISTINCT from equip; wired to the face -----------
        auto = _auto_attach_spec(oracle)
        if auto:
            aa_ability, aa_op = f"ability:auto-attach:{E}", f"op:auto-attach:{E}"
            node(aa_ability, "Ability", f"auto-attach (ETB): {name}",
                 {"equipment": name, "kind": "automatic", "trigger": "etb"},
                 [prov(E, auto.get("span"), None, "the ETB triggered ability that attaches automatically")])
            aa_data = {"kind": "automatic", "trigger": "etb", "equipment": name, "target": auto["target"], "attaches": state}
            for k in ("creates", "amass"):
                if auto.get(k):
                    aa_data[k] = auto[k]
            node(aa_op, "Operation", f"auto-attach {name}", aa_data,
                 [prov(E, auto.get("span"), None, "the automatic (ETB) attachment operation — NOT the equip activation")])
            # face HAS_ABILITY the auto-attach ability (was orphaned in the prior build)
            edge(E, "HAS_ABILITY", aa_ability, [prov(E, auto.get("span"), None, "the ETB auto-attach ability")])
            edge(aa_ability, "CAUSES", aa_op, [prov(E, auto.get("span"), None, "the ETB trigger performs the auto attachment")])
            aa_conds = [c for c in [auto.get("restriction_condition")] if c]
            edge(aa_op, "REQUIRES", auto["restriction_object"],
                 [prov(E, auto.get("span"), None, "the auto attachment binds a controlled creature"
                       + (" that is a Dwarf" if auto["restriction_object"] == OBJ_SUBTYPE_DWARF else ""))],
                 **({"condition_ids": aa_conds} if aa_conds else {}))
            # attachment is the RESULT — not conditioned on being attached (fixes the circular condition)
            edge(aa_op, "CAUSES", state, [prov(E, auto.get("span"), None, "the auto attachment reaches the same bound state")])

        # ---- continuous "equipped creature" P/T modification (face HAS_ABILITY) -----------
        pt = _parse_pt(oracle)
        if pt:
            mab, mop = f"ability:equipped-bonus:{E}", f"op:modify-equipped:{E}"
            span = pt[2]
            node(mab, "Ability", f"equipped-creature bonus: {name}", {"equipment": name, "kind": "static_pt_bonus"},
                 [prov(E, span, None, "static equipped-creature P/T bonus")])
            node(mop, "Operation", f"modify equipped creature: {name}",
                 {"kind": "modify_equipped", "equipment": name, "modification": {"power": pt[0], "toughness": pt[1]}},
                 [prov(E, span, None, "applies the equipped-creature P/T modification")])
            edge(E, "HAS_ABILITY", mab, [prov(E, span, None, "the equipped-creature bonus ability")])
            edge(mab, "CAUSES", mop, [prov(E, span, None, "the static bonus is applied by this operation")])
            edge(mop, "REQUIRES", state, [prov(E, span, None, "the bonus applies only while attached")],
                 condition_ids=[cond_attached])
            edge(mop, "MODIFIES", bound, [prov(E, span, None, "modifies the bound (equipped) creature")],
                 modification={"power": pt[0], "toughness": pt[1]}, condition_ids=[cond_attached])
            dispositions.append({"face": E, "equipment": name, "clause": "Equipped creature gets %s/%s" % (pt[0], pt[1]),
                                 "disposition": "represented", "relation": "MODIFIES_WHEN_ATTACHED"})

        # ---- continuous granted keywords/abilities (face HAS_ABILITY) ----------------------
        granted = _parse_granted_keywords(oracle)
        if granted:
            gab, gop = f"ability:equipped-grant:{E}", f"op:grant-equipped:{E}"
            kws = [k for k, _ in granted]
            gspan = granted[0][1]
            node(gab, "Ability", f"equipped-creature grants: {name}", {"equipment": name, "kind": "static_grant", "granted": kws},
                 [prov(E, gspan, None, "static equipped-creature keyword grant")])
            node(gop, "Operation", f"grant to equipped creature: {name}",
                 {"kind": "grant_equipped", "equipment": name, "granted_abilities": kws},
                 [prov(E, gspan, None, "grants keyword abilities to the equipped creature")])
            edge(E, "HAS_ABILITY", gab, [prov(E, gspan, None, "the equipped-creature grant ability")])
            edge(gab, "CAUSES", gop, [prov(E, gspan, None, "the grant is applied by this operation")])
            edge(gop, "REQUIRES", state, [prov(E, gspan, None, "the grants apply only while attached")],
                 condition_ids=[cond_attached])
            edge(gop, "MODIFIES", bound, [prov(E, gspan, None, "grants keyword abilities to the bound creature")],
                 granted_abilities=kws, condition_ids=[cond_attached])
            for k, sp in granted:
                dispositions.append({"face": E, "equipment": name, "clause": "Equipped creature has %s" % k,
                                     "disposition": "represented", "relation": "GRANTS_ABILITY_WHEN_ATTACHED"})

        # ---- disposition every remaining "Equipped creature ..." clause -------------------
        represented_spans = set()
        if pt:
            represented_spans.add(tuple(pt[2]))
        for _, sp in granted:
            represented_spans.add(tuple(sp))
        for cl in _equipped_clauses(oracle):
            if tuple(cl["span"]) in represented_spans:
                continue
            low = cl["text"].lower()
            if re.search(r"gets [+\-]\d+/[+\-]\d+", low) or " has " in low:
                continue                                 # already represented by a P/T or grant clause
            # pt6: these complex effects are NOT "successfully disposed" — they are UNRESOLVED, and
            # the ones needing new predicates (triggers / dynamic costs / ability modification) are
            # explicit schema-extension requests. Strategically material for later deck projection.
            needs_schema = any(k in low for k in
                               ("whenever", "triggers an additional", "cost {", "costs {",
                                "deals combat damage", "for each", "instead", "additional time"))
            dispositions.append({
                "face": E, "equipment": name, "clause": cl["text"],
                "disposition": "schema_extension_required" if needs_schema else "unresolved",
                "schema_extension_required": needs_schema,
                "reason": ("complex equipped-creature effect not expressible with the current Equip "
                           "template primitives" + (" — needs a schema extension (trigger / dynamic-cost / "
                           "ability-modification predicates)" if needs_schema else " — pending structured "
                           "extraction"))})

    # ---- token:axe (Equipment with no card face): primitive template coverage -------------
    axe_creator_ops = [e for e in g.edges if e["predicate"] == "CREATES_OBJECT" and e["target"] == TOKEN_AXE]
    axe_oracle = "Equipped creature gets +1/+0. Equip {2}"     # the Axe token's printed characteristics
    if TOKEN_AXE in g.nodes or axe_creator_ops:
        node(TOKEN_AXE, "TokenSpec", "Axe (Equipment token)", {"equipment": "Axe", "subtype": "equipment"},
             [prov(None, None, None, "the Axe Equipment token created by Dáin Ironfoot")]) if TOKEN_AXE not in g.nodes else None
        build_equip_template(TOKEN_AXE, "token", "Axe", "axe", axe_oracle, None)
        pt = _parse_pt(axe_oracle)
        state, bound = f"state:attachment:{TOKEN_AXE}", f"obj:bound-creature:{TOKEN_AXE}"
        cond_attached = "cond:equipment-axe-attached"
        mab, mop = f"ability:equipped-bonus:{TOKEN_AXE}", f"op:modify-equipped:{TOKEN_AXE}"
        node(mab, "Ability", "equipped-creature bonus: Axe", {"equipment": "Axe", "kind": "static_pt_bonus"},
             [prov(None, None, None, "Axe equipped-creature P/T bonus")])
        node(mop, "Operation", "modify equipped creature: Axe",
             {"kind": "modify_equipped", "equipment": "Axe", "modification": {"power": pt[0], "toughness": pt[1]}},
             [prov(None, None, None, "applies the Axe P/T modification")])
        edge(TOKEN_AXE, "HAS_ABILITY", mab, [prov(None, None, None, "the Axe equipped-creature bonus ability")])
        edge(mab, "CAUSES", mop, [prov(None, None, None, "the static bonus is applied by this operation")])
        edge(mop, "REQUIRES", state, [prov(None, None, None, "the bonus applies only while attached")], condition_ids=[cond_attached])
        edge(mop, "MODIFIES", bound, [prov(None, None, None, "modifies the bound (equipped) creature")],
             modification={"power": pt[0], "toughness": pt[1]}, condition_ids=[cond_attached])
        dispositions.append({"face": TOKEN_AXE, "equipment": "Axe", "clause": "Equipped creature gets +1/+0",
                             "disposition": "represented", "relation": "MODIFIES_WHEN_ATTACHED"})

    # ---- write + validate ---------------------------------------------------------------
    outdir = repo / "data" / "graph_global"
    uniq = {}
    for e in edges:
        uniq.setdefault(e["edge_id"], {k: v for k, v in e.items() if v is not None})
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
    with (outdir / "equip_dispositions.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for d in sorted(dispositions, key=lambda d: (d["face"], d["clause"])):
            fh.write(json.dumps(d, ensure_ascii=False, sort_keys=True) + "\n")

    from .graph_repair import _validate_repair_layer
    violations = _validate_repair_layer(repo, g.nodes, nodes, edges)
    defined = {c["condition_id"] for c in _load_dicts(repo / "data/graph_global/conditions.jsonl")} | set(conditions)
    referenced = {c for e in edges for c in (e.get("condition_ids") or [])}
    unresolved = sorted(referenced - defined)
    # structural: no operation REQUIRES the state it CAUSES
    causes_state = {(e["source"], e["target"]) for e in edges if e["predicate"] == "CAUSES" and e["target"].startswith("state:")}
    requires_state = {(e["source"], e["target"]) for e in edges if e["predicate"] == "REQUIRES" and e["target"].startswith("state:")}
    circular = sorted(s for (s, t) in causes_state if (s, t) in requires_state)
    # every equipped-bonus/grant/auto-attach ability has an incoming face/token HAS_ABILITY
    has_ability_targets = {e["target"] for e in edges if e["predicate"] == "HAS_ABILITY"}
    orphan_abilities = sorted(nid for nid, n in nodes.items() if n["type"] == "Ability" and nid not in has_ability_targets)
    return {"equip_cards": stats_cards, "equip_nodes": len(nodes), "equip_edges": len(edges),
            "equip_conditions": len(conditions), "equip_dispositions": len(dispositions),
            "token_axe_covered": TOKEN_AXE in nodes or f"ability:equip:{TOKEN_AXE}" in nodes,
            "unresolved_conditions": unresolved, "circular_attach_ops": circular,
            "orphan_abilities": orphan_abilities, "signature_violations": len(violations), "_violations": violations}


# --------------------------------------------------------------------------- #
#  Reprojection: CONTINUOUS, card-to-card grounded typed paths                  #
# --------------------------------------------------------------------------- #
def reproject(repo: Path = REPO) -> dict:
    g = _G(repo)
    eq_nodes = {n["id"]: n for n in _load_dicts(repo / "data/graph_global/equip_nodes.jsonl")}
    eq_edges = list(_load_dicts(repo / "data/graph_global/equip_edges.jsonl"))
    all_edges = g.edges + eq_edges
    eq_ids = {e["edge_id"] for e in eq_edges}
    real_ids = {e["edge_id"] for e in g.edges}
    index = {}
    for e in all_edges:
        index.setdefault((e["source"], e["predicate"], e["target"]), e)

    def E(source, predicate, target):
        return index.get((source, predicate, target))

    def _pop(target):
        return sorted({c for e in g.edges if e["predicate"] == "HAS_TYPE" and e["target"] == target
                       for c in [_card_of(e["source"])] if c})
    creature_cards = _pop(OBJ_TYPE_CREATURE)
    wizard_cards = set(_pop(OBJ_SUBTYPE_WIZARD))
    # a representative HAS_TYPE edge + HAS_FACE edge per creature/wizard card (for grounded tails)
    htype = defaultdict(dict)   # obj -> {card: edge}
    for e in g.edges:
        if e["predicate"] == "HAS_TYPE" and e["target"] in (OBJ_TYPE_CREATURE, OBJ_SUBTYPE_WIZARD):
            htype[e["target"]].setdefault(_card_of(e["source"]), e)
    hasface = {}   # card -> HAS_FACE edge (card -> face)
    for e in g.edges:
        if e["predicate"] == "HAS_FACE":
            hasface.setdefault(_card_of(e["source"]), e)

    metaedges = []

    def emit(a_card, b_card, relation, steps, equip_cost, extra):
        if not a_card or not b_card or a_card == b_card or any(s is None for s in steps):
            return
        # CONTINUITY: adjacent steps must share the traversed endpoint
        for x, y in zip(steps, steps[1:]):
            if x["target"] != y["source"]:
                return
        nodes_seq = [steps[0]["source"]] + [s["target"] for s in steps]
        if _card_of(nodes_seq[0]) != a_card or _card_of(nodes_seq[-1]) != b_card:
            return
        conds = sorted({c for s in steps for c in (s.get("condition_ids") or [])} | set(extra.pop("_conds", [])))
        m = {"source_card": a_card, "target_card": b_card, "relation": relation, "origin": "equip",
             "path_kind": "grounded", "steps": steps, "primitive_path": nodes_seq,
             "path_predicates": [s["predicate"] for s in steps], "edge_ids": [s["edge_id"] for s in steps],
             "uses_equip_edges": [s["edge_id"] for s in steps if s["edge_id"] in eq_ids],
             "connecting_node": nodes_seq[1], "condition_ids": conds}
        if equip_cost is not None:
            m["equip_cost"] = equip_cost
        m.update(extra)
        metaedges.append(m)

    def tail_to_creature(obj_class, c_card):
        """The grounded tail obj_class -> face:C -> card:C (two reverse steps)."""
        ht = htype[obj_class].get(c_card)
        hf = hasface.get(c_card)
        if not ht or not hf:
            return None
        return [_step(ht, "reverse"), _step(hf, "reverse")]

    def can_attach(host, e_card, cost, mode, req_obj, suffix, pop_cards, cond_extra):
        hf_e = hasface.get(e_card)
        hab = E(host, "HAS_ABILITY", f"ability:{suffix}:{host}")
        cau = E(f"ability:{suffix}:{host}", "CAUSES", f"op:{suffix}:{host}")
        req = E(f"op:{suffix}:{host}", "REQUIRES", req_obj)
        if not (hf_e and hab and cau and req):
            return
        head = [_step(hf_e, "forward"), _step(hab, "forward"),
                _step(cau, "forward"), _step(req, "forward")]
        # bridge from req_obj to the creature type if needed (obj:creature-you-control -> obj:type:creature)
        bridge_obj = OBJ_TYPE_CREATURE if req_obj == OBJ_CREATURE_YOU_CONTROL else req_obj
        if req_obj == OBJ_CREATURE_YOU_CONTROL:
            b = E(OBJ_CREATURE_YOU_CONTROL, "HAS_TYPE", OBJ_TYPE_CREATURE)
            if not b:
                return
            head.append(_step(b, "forward"))
        for c_card in pop_cards:
            tail = tail_to_creature(bridge_obj, c_card)
            if not tail:
                continue
            emit(e_card, c_card, "CAN_ATTACH_TO", head + tail, cost,
                 {"equip_mode": mode, "_conds": cond_extra})

    for face in g.equipment_faces():
        host = face["id"]
        e_card = _card_of(host)
        cost_n = eq_nodes.get(f"cost:equip:{host}", {}).get("data", {})
        cost = {"mana_cost": cost_n.get("mana_cost"), "additional_cost": cost_n.get("additional_cost"), "raw": cost_n.get("raw")}
        alt_n = eq_nodes.get(f"cost:equip-alt:{host}", {}).get("data", {})
        alt_cost = {"mana_cost": alt_n.get("mana_cost"), "additional_cost": alt_n.get("additional_cost"), "raw": alt_n.get("raw")}

        can_attach(host, e_card, cost, "primary", OBJ_CREATURE_YOU_CONTROL, "equip",
                   creature_cards, [COND_TARGET_CONTROLLED, COND_SORCERY_TIMING])
        if E(host, "HAS_ABILITY", f"ability:equip-alt:{host}"):
            can_attach(host, e_card, alt_cost, "alternative-wizard", OBJ_SUBTYPE_WIZARD, "equip-alt",
                       sorted(wizard_cards), [COND_TARGET_CONTROLLED, COND_SORCERY_TIMING, COND_TARGET_IS_WIZARD])

        # MODIFIES_WHEN_ATTACHED / GRANTS_ABILITY_WHEN_ATTACHED — the reviewer's grounded path:
        # card:E -> face:E -> equip ability -> equip op -> ATTACHMENT STATE -> effect op ->
        # bound creature -> creature type -> face:C -> card:C. The attachment state is ON the path.
        bound, state = f"obj:bound-creature:{host}", f"state:attachment:{host}"
        hf_e = hasface.get(e_card)
        hab_equip = E(host, "HAS_ABILITY", f"ability:equip:{host}")
        equip_cau = E(f"ability:equip:{host}", "CAUSES", f"op:equip:{host}")
        equip_state = E(f"op:equip:{host}", "CAUSES", state)
        bnd = E(bound, "HAS_TYPE", OBJ_TYPE_CREATURE)
        for (opnode, relation) in ((f"op:modify-equipped:{host}", "MODIFIES_WHEN_ATTACHED"),
                                   (f"op:grant-equipped:{host}", "GRANTS_ABILITY_WHEN_ATTACHED")):
            req_state = E(opnode, "REQUIRES", state)
            mod = E(opnode, "MODIFIES", bound)
            if not (hf_e and hab_equip and equip_cau and equip_state and req_state and mod and bnd):
                continue
            head = [_step(hf_e, "forward"), _step(hab_equip, "forward"),
                    _step(equip_cau, "forward"), _step(equip_state, "forward"),
                    _step(req_state, "reverse"), _step(mod, "forward"), _step(bnd, "forward")]
            for c_card in creature_cards:
                tail = tail_to_creature(OBJ_TYPE_CREATURE, c_card)
                if not tail:
                    continue
                if relation == "MODIFIES_WHEN_ATTACHED":
                    emit(e_card, c_card, relation, head + tail, cost,
                         {"modification": mod.get("modification"), "attachment_state": state, "bound_creature": bound})
                else:
                    for kw in (mod.get("granted_abilities") or []):
                        emit(e_card, c_card, relation, head + tail, cost,
                             {"granted_ability": kw, "attachment_state": state, "bound_creature": bound})

    # ---- token:axe: the CREATOR card can attach the created Axe to a creature -------------
    axe_state_ok = f"op:equip:{TOKEN_AXE}" in eq_nodes
    for ce in [e for e in g.edges if e["predicate"] == "CREATES_OBJECT" and e["target"] == TOKEN_AXE]:
        creator_face = ce["source"]                       # an op on the creator's face
        creator_card = _card_of(creator_face)
        hf = hasface.get(creator_card)
        if not (axe_state_ok and hf and creator_card):
            continue
        # creator card -> face -> ... -> op(create) -> token:axe -> equip ability -> op -> creature-you-control -> type -> C
        cau_to_op = None
        # find ability -CAUSES-> creator op, and face -HAS_ABILITY-> ability (frozen)
        cause_edge = next((e for e in g.edges if e["predicate"] == "CAUSES" and e["target"] == creator_face), None)
        face_node = re.match(r"(face:[0-9a-f-]+:\d+)", creator_face)
        hab_creator = None
        if cause_edge:
            hab_creator = next((e for e in g.edges if e["predicate"] == "HAS_ABILITY"
                                and e["target"] == cause_edge["source"]), None)
        hab_equip = E(TOKEN_AXE, "HAS_ABILITY", f"ability:equip:{TOKEN_AXE}")
        cau_equip = E(f"ability:equip:{TOKEN_AXE}", "CAUSES", f"op:equip:{TOKEN_AXE}")
        req_equip = E(f"op:equip:{TOKEN_AXE}", "REQUIRES", OBJ_CREATURE_YOU_CONTROL)
        bind = E(OBJ_CREATURE_YOU_CONTROL, "HAS_TYPE", OBJ_TYPE_CREATURE)
        if not (cause_edge and hab_creator and hab_equip and cau_equip and req_equip and bind):
            continue
        head = [_step(hf, "forward"), _step(hab_creator, "forward"),
                _step(cause_edge, "forward"), _step(ce, "forward"),
                _step(hab_equip, "forward"), _step(cau_equip, "forward"),
                _step(req_equip, "forward"), _step(bind, "forward")]
        axe_cost_n = eq_nodes.get(f"cost:equip:{TOKEN_AXE}", {}).get("data", {})
        axe_cost = {"mana_cost": axe_cost_n.get("mana_cost"), "additional_cost": axe_cost_n.get("additional_cost"),
                    "raw": axe_cost_n.get("raw")}
        for c_card in creature_cards:
            tail = tail_to_creature(OBJ_TYPE_CREATURE, c_card)
            if not tail:
                continue
            emit(creator_card, c_card, "CAN_ATTACH_TO", head + tail, axe_cost,
                 {"equip_mode": "via-created-token:axe",
                  "_conds": [COND_TARGET_CONTROLLED, COND_SORCERY_TIMING]})

    metaedges.sort(key=lambda m: (m["source_card"], m["target_card"], m["relation"],
                                  m.get("granted_ability") or "", m.get("equip_mode") or "", m["connecting_node"]))
    with (repo / "data/graph_global/card_pair_projection_equip.jsonl").open("w", encoding="utf-8", newline="\n") as fh:
        for m in metaedges:
            fh.write(json.dumps(m, ensure_ascii=False, sort_keys=True) + "\n")

    # SELF-CHECK gates (pt5): continuity, card-grounded endpoints, edge resolution
    continuous = all(x["target"] == y["source"] for m in metaedges for x, y in zip(m["steps"], m["steps"][1:]))
    grounded = all(_card_of(m["primitive_path"][0]) == m["source_card"]
                   and _card_of(m["primitive_path"][-1]) == m["target_card"] for m in metaedges)
    edges_resolve = all(s["edge_id"] in real_ids or s["edge_id"] in eq_ids for m in metaedges for s in m["steps"])
    by_rel = {}
    for m in metaedges:
        by_rel[m["relation"]] = by_rel.get(m["relation"], 0) + 1
    _report(repo, g, metaedges, by_rel, continuous, grounded, edges_resolve)
    return {"reprojected": len(metaedges), "by_relation": by_rel, "paths_continuous": continuous,
            "paths_card_grounded": grounded, "edges_resolve": edges_resolve}


def _report(repo, g, metaedges, by_rel, continuous, grounded, ok):
    L = ["# HOB Equip Attachment Layer — Materialization + Reprojection (pt5)", "",
         f"- **reprojected metaedges**: {len(metaedges)} (origin `equip`)",
         f"- **by relation**: {by_rel}",
         f"- **paths continuous (step joins connect)**: {continuous}",
         f"- **paths card-grounded (card:E … card:C)**: {grounded}",
         f"- **all path edges resolve**: {ok}", "", "## Sample relations", ""]
    for m in metaedges[:60]:
        a, b = g.names.get(m["source_card"], m["source_card"]), g.names.get(m["target_card"], m["target_card"])
        detail = (f"  _(mod: {m['modification']})_" if m.get("modification")
                  else f"  _(grants: {m['granted_ability']})_" if m.get("granted_ability")
                  else f"  _(cost: {m.get('equip_cost', {}).get('raw')})_")
        L.append(f"- **{a} -> {b}** [{m['relation']}] — {' -> '.join(m['path_predicates'])}{detail}")
    if len(metaedges) > 60:
        L.append("- … (truncated)")
    (repo / "reports" / "equip.md").write_text("\n".join(L) + "\n", encoding="utf-8")

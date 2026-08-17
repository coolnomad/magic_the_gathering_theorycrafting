"""Additive `audit_repair` layer — applies the HUMAN gold-set audit corrections
(`data/review/human_audit_verdicts.jsonl`, 2026-08-17) WITHOUT touching the frozen core graph.

Design (per the owner's directive): represent each corrected mechanism ONCE at the object-class
level (a canonical class edge grounded in the responsible card's Oracle text), then derive ALL
eligible card pairs mechanically from card characteristics — never hard-code an audited pair. The
derived pair relations are tagged `generic: true` (object-class expansions) so they are filterable,
and carry `origin: audit_repair` + provenance to the audit item. Two kinds of correction:

  * ADD / RETYPE — a canonical class edge + derived pairs (anthem MODIFIES; targeted +1/+1
    ADDS_COUNTER; targeted pump MODIFIES; tutor SUPPLIES_RESOURCE; token-enter ENABLES_TRIGGER;
    tribal-entry ENABLES_TRIGGER, which also RETYPES the mechanism-layer SUPPLIES_RESOURCE it
    replaces via a suppression).
  * SUPPRESS — retract a projected relation the human judged wrong (a false self-loop; a
    coincidental resource match that is really a cast-trigger).

Outputs (all under data/graph_global/): `audit_repair_nodes.jsonl` (object-class nodes),
`audit_repair_edges.jsonl` (canonical class edges), `card_pair_projection_audit_repair.jsonl`
(derived generic pairs), `audit_repair_suppressions.jsonl`. Deterministic; no Date/random.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .pipeline import REPO, _load_dicts

AUDIT = "human_audit_verdicts.jsonl (2026-08-17)"


def _sid(*parts) -> str:
    return "ar" + hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:15]


class _Cards:
    """Card characteristics derived from the normalized faces (the eligibility basis)."""
    def __init__(self, repo: Path):
        self.faces = _load_dicts(repo / "data/normalized/faces.jsonl")
        self.by_card = {}
        self.name_to_card = {}
        self.card_faces = {}
        for f in self.faces:
            self.by_card.setdefault(f["card_id"], []).append(f)
            self.name_to_card[f["name"]] = f["card_id"]
            self.card_faces.setdefault(f["card_id"], []).append(f)

    def face_id(self, name: str) -> str:
        for f in self.faces:
            if f["name"] == name:
                return f["id"]
        raise KeyError(name)

    def card_of_name(self, name: str) -> str:
        return self.name_to_card[name]

    def _has(self, cid, pred):
        return any(pred(f) for f in self.by_card.get(cid, []))

    def _types(self, f):
        return (f.get("type_line") or {}).get("types", [])

    def _subs(self, f):
        return (f.get("type_line") or {}).get("subtypes", [])

    def _sups(self, f):
        return (f.get("type_line") or {}).get("supertypes", [])

    def creatures(self):
        return {c for c in self.by_card if self._has(c, lambda f: "Creature" in self._types(f))}

    def legendary_creatures(self):
        return {c for c in self.by_card
                if self._has(c, lambda f: "Creature" in self._types(f) and "Legendary" in self._sups(f))}

    def dwarves_or_equipment(self):
        return {c for c in self.by_card
                if self._has(c, lambda f: "Dwarf" in self._subs(f) or "Equipment" in self._subs(f))}

    def token_makers(self):
        import re
        pat = re.compile(r"\bcreate[s]?\b[^.]*\btokens?\b|\bamass\b", re.IGNORECASE)
        # exclude reminder-only mentions ("it's an artifact with …") is unnecessary: a Treasure/Food
        # token still enters under your control and triggers a token-enter payoff.
        return {c for c in self.by_card
                if self._has(c, lambda f: bool(pat.search(f.get("oracle_text") or "")))}


# --------------------------------------------------------------------------- #
#  The corrections, grounded in the responsible card's ability (not in pairs)   #
# --------------------------------------------------------------------------- #
import re

# DERIVED P/T mechanisms (Class 2, GENERALIZED): every card whose Oracle text matches the pattern is
# a source — no hand-picked list. Restricted to the GENERAL 'any creature' forms; equipment
# ('Equipped creature …', handled by the equip layer), self-pumps ('This creature …'), tribal anthems
# ('Other Elves/Bears …', partly in graph_repair) and Amass ('… on an Army') are excluded by the
# patterns. target=every creature (a targeted/your-controlled creature can be any creature).
_RE_ANTHEM = re.compile(r"\b(?:other )?creatures you control get \+\d+/\+\d+", re.I)
_RE_PUMP = re.compile(r"\btarget creature(?: you control| an opponent controls)?[^.]*?\bgets? \+\d+/\+\d+", re.I)
_RE_COUNTER = re.compile(r"\+1/\+1 counter(?:s)? on (?:up to \w+ |two |three |x |a )?(?:other )?"
                         r"target creature(?: you control)?\b", re.I)
# (slug, regex, predicate, class_node, note, {audited_source_name: [items]})
_DERIVED = [
    ("anthem", _RE_ANTHEM, "MODIFIES", "obj:creature-you-control",
     "Static/mass anthem: 'creatures you control get +N/+N' modifies every creature you control.",
     {"The Arkenstone": [66, 72, 74]}),
    ("targeted-pump", _RE_PUMP, "MODIFIES", "obj:target-creature",
     "Targeted pump: 'target creature … gets +N/+N' modifies a creature.",
     {"Lake-town Toymaker": [75]}),
    ("targeted-counter", _RE_COUNTER, "ADDS_COUNTER", "obj:target-creature",
     "Targeted +1/+1 counter: 'put a +1/+1 counter on target creature'.",
     {"Meager Meal": [67, 68, 71]}),
]

# ANCHORED specific-card mechanisms (NOT anthem/pump; unchanged):
# (slug, anchor_card, side, predicate, class_node, eligibility, note, items, retype)
_ANCHORED = [
    ("seek-the-heart-tutor", "Seek the Heart", "targets", "SUPPLIES_RESOURCE",
     "obj:legendary-creature-card", "legendary_creatures",
     "Tutor: 'Search your library for a legendary creature card' supplies that creature.",
     [74], None),
    ("belladonna-token-enter", "Belladonna Took", "sources", "ENABLES_TRIGGER",
     "event:token-you-control-enters", "token_makers",
     "A token entering your control triggers Belladonna Took's token-enter payoff.",
     [82], None),
    ("kili-tribal-entry", "Kíli the Resourceful", "sources", "ENABLES_TRIGGER",
     "event:another-dwarf-or-equipment-enters", "dwarves_or_equipment",
     "A Dwarf/Equipment entering triggers Kíli's 'whenever another Dwarf or Equipment enters, draw'.",
     [54], ("SUPPLIES_RESOURCE", "mechanism")),
]

# SUPPRESS: (src_name, tgt_name, relation, layer, note, items)
_SUPPRESS = [
    ("Head of the Hunt", "Head of the Hunt", "ENABLES_TRIGGER", "mechanical",
     "Not a self-loop: the token trigger fires from an OPPONENT's creature being exiled, not from "
     "Head of the Hunt itself.", [111]),
    ("Plunder the Trollshaws", "Uncover the Moon-Letters", "SUPPLIES_RESOURCE", "mechanical",
     "Coincidental card-in-hand match: casting the spell TRIGGERS the enchantment, it does not supply "
     "a consumed resource.", [58]),
]


def materialize(repo: Path = REPO) -> dict:
    repo = Path(repo)
    C = _Cards(repo)
    out = repo / "data" / "graph_global"
    eligible = {"creatures": C.creatures(), "legendary_creatures": C.legendary_creatures(),
                "dwarves_or_equipment": C.dwarves_or_equipment(), "token_makers": C.token_makers()}

    nodes, edges, pairs, suppressions = [], [], [], []
    seen = set()

    def add_pair(s, t, rel, slug, prov, retype=None):
        if s == t or (s, t, rel) in seen:                  # no self-pair; dedupe across mechanisms
            return
        seen.add((s, t, rel))
        pairs.append({"source_card": s, "target_card": t, "relation": rel, "self_pair": False,
                      "generic": True, "class_edge": slug, "origin": "audit_repair", "provenance": [prov]})
        if retype:                                         # the new relation REPLACES a mis-typed one
            suppressions.append({"source_card": s, "target_card": t, "relation": retype[0],
                                 "layer": retype[1], "reason": f"retyped to {rel} by {slug}",
                                 "audit_items": prov.get("audit_items")})

    creatures = eligible["creatures"]
    # DERIVED P/T mechanisms — every matching card is a source (Class 2 generalized to all anthem/pump)
    for slug, regex, pred, class_node, note, audited in _DERIVED:
        nodes.append({"id": class_node, "kind": class_node.split(":")[0], "origin": "audit_repair"})
        for f in sorted(C.faces, key=lambda x: x["id"]):
            if not regex.search(f.get("oracle_text") or ""):
                continue
            prov = {"source": AUDIT + " · Class 2 generalization (all anthem/pump)", "mechanism": slug,
                    "note": note, "anchor_face": f["id"], "audit_items": audited.get(f["name"])}
            edges.append({"id": _sid(slug, f["id"], pred, class_node), "source": f["id"],
                          "predicate": pred, "target": class_node, "origin": "audit_repair",
                          "generic": True, "provenance": [prov]})
            for cid in sorted(creatures):
                add_pair(f["card_id"], cid, pred, slug, prov)

    # ANCHORED specific-card mechanisms (tutor / token-enter / tribal-entry)
    for slug, anchor, side, pred, class_node, elig, note, items, retype in _ANCHORED:
        anchor_face = C.face_id(anchor)
        anchor_card = C.card_of_name(anchor)
        nodes.append({"id": class_node, "kind": class_node.split(":")[0], "origin": "audit_repair"})
        prov = {"source": AUDIT, "audit_items": items, "note": note, "anchor_face": anchor_face}
        e_src, e_tgt = (anchor_face, class_node) if side == "targets" else (class_node, anchor_face)
        edges.append({"id": _sid(slug, e_src, pred, e_tgt), "source": e_src, "predicate": pred,
                      "target": e_tgt, "origin": "audit_repair", "generic": True, "provenance": [prov]})
        for cid in sorted(eligible[elig]):
            s, t = (anchor_card, cid) if side == "targets" else (cid, anchor_card)
            add_pair(s, t, pred, slug, prov, retype)

    for src, tgt, rel, layer, note, items in _SUPPRESS:
        suppressions.append({"source_card": C.card_of_name(src), "target_card": C.card_of_name(tgt),
                             "relation": rel, "layer": layer, "reason": note, "audit_items": items})

    _write(out / "audit_repair_nodes.jsonl", _dedup(nodes, "id"))
    _write(out / "audit_repair_edges.jsonl", sorted(edges, key=lambda e: e["id"]))
    _write(out / "card_pair_projection_audit_repair.jsonl",
           sorted(pairs, key=lambda p: (p["source_card"], p["target_card"], p["relation"])))
    _write(out / "audit_repair_suppressions.jsonl",
           sorted(suppressions, key=lambda s: (s["layer"], s["source_card"], s["target_card"], s["relation"])))
    return {"class_edges": len(edges), "derived_pairs": len(pairs), "suppressions": len(suppressions),
            "eligible_counts": {k: len(v) for k, v in eligible.items()}}


def _dedup(rows, key):
    seen, out = set(), []
    for r in rows:
        if r[key] not in seen:
            seen.add(r[key]); out.append(r)
    return out


def _write(path: Path, rows: list):
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")

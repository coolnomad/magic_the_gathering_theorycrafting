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
# ADD/RETYPE: (slug, anchor_card, side, predicate, class_node, eligibility, note, items, retype)
#   side='targets' → anchor is the SOURCE, derive eligible target cards.
#   side='sources' → anchor is the TARGET, derive eligible source cards.
#   retype=(relation, layer) → also suppress this relation on every derived pair (a mis-typed edge).
_ADDS = [
    ("arkenstone-anthem", "The Arkenstone", "targets", "MODIFIES", "obj:creature-you-control",
     "creatures", "Static anthem: 'Creatures you control get +1/+1' modifies every creature you control.",
     [66, 72, 74], None),
    ("meager-meal-counter", "Meager Meal", "targets", "ADDS_COUNTER", "obj:target-creature",
     "creatures", "'Put a +1/+1 counter on up to one target creature' can modify any creature.",
     [67, 68, 71], None),
    ("lake-town-toymaker-pump", "Lake-town Toymaker", "targets", "MODIFIES",
     "obj:another-target-creature-you-control", "creatures",
     "'another target creature you control gets +3/+0 and gains first strike' modifies a creature.",
     [75], None),
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
    for slug, anchor, side, pred, class_node, elig, note, items, retype in _ADDS:
        anchor_face = C.face_id(anchor)
        anchor_card = C.card_of_name(anchor)
        nodes.append({"id": class_node, "kind": class_node.split(":")[0], "origin": "audit_repair"})
        prov = {"source": AUDIT, "audit_items": items, "note": note, "anchor_face": anchor_face}
        # canonical class edge (grounded once, at the object-class level)
        e_src, e_tgt = (anchor_face, class_node) if side == "targets" else (class_node, anchor_face)
        edges.append({"id": _sid(slug, e_src, pred, e_tgt), "source": e_src, "predicate": pred,
                      "target": e_tgt, "origin": "audit_repair", "generic": True, "provenance": [prov]})
        # derive eligible card pairs mechanically
        for cid in sorted(eligible[elig]):
            if cid == anchor_card:
                continue                                   # no self-pair from a class expansion
            s, t = (anchor_card, cid) if side == "targets" else (cid, anchor_card)
            pairs.append({"source_card": s, "target_card": t, "relation": pred, "self_pair": False,
                          "generic": True, "class_edge": slug, "origin": "audit_repair",
                          "provenance": [prov]})
            if retype:                                     # the new relation REPLACES a mis-typed one
                suppressions.append({"source_card": s, "target_card": t, "relation": retype[0],
                                     "layer": retype[1], "reason": f"retyped to {pred} by {slug}",
                                     "audit_items": items})

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

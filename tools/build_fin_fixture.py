"""Generate the FIN sacrifice fixtures from the real Scryfall FIN dump.

Oracle text is copied BYTE-FOR-BYTE from data/raw/fin/scryfall_fin.json (by Scryfall id / face) —
never hand-typed — so the fixtures are provenanced real second-set text. Only the adjudicated
`expected` structured record is hand-authored here (adjudicated to the rules, not to the parser).

Each entry authors a `selector` dict + a compact `cost` skeleton once; this script expands them into
the flat scored fields (`sel_*`) and the structured cost (with the selector attached to each
sacrifice atom, matching sac_schema._sel_sig). Deterministic; no Date/random.
"""
import io
import json
from pathlib import Path

from hobkg.sac_schema import _sel_sig

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "data/raw/fin/scryfall_fin.json"
OUT = REPO / "tests/fixtures/fin_sacrifice.jsonl"
OUT_HELD = REPO / "tests/fixtures/fin_sacrifice_heldout.jsonl"


def sel(card_types=(), or_types=False, supertypes=(), qualifiers=(), self=False, another=False, quantity=1):
    return {"card_types": list(card_types), "or_types": or_types, "supertypes": list(supertypes),
            "qualifiers": list(qualifiers), "self": self, "another": another, "quantity": quantity}


def cost(*branches):
    """branches = tuples of atoms; atom 'SAC' -> the record selector; ('pay','{3}'), 'TAP', ('discard',n)."""
    return branches or None


def _expand(meta):
    """meta -> flat expected record (is_outlet + scored fields)."""
    if meta.get("is_outlet") is False:
        return {"is_outlet": False}
    s = meta["selector"]
    exp = {"is_outlet": True, "cost_context": meta["cost_context"], "actor": meta["actor"],
           "ability_context": meta["ability_context"], "modal": meta.get("modal", False),
           "sel_card_types": sorted(s["card_types"]), "sel_or_types": s["or_types"],
           "sel_supertypes": sorted(s["supertypes"]), "sel_qualifiers": sorted(s["qualifiers"]),
           "sel_self": s["self"], "sel_another": s["another"], "sel_quantity": s["quantity"],
           "restriction_timing": meta.get("restriction_timing")}
    c = meta.get("cost")
    if not c:
        exp["cost"] = None
    else:
        alt = []
        for branch in c:
            atoms = []
            for a in branch:
                if a == "SAC":
                    atoms.append({"sacrifice": _sel_sig(s)})
                elif a == "TAP":
                    atoms.append({"tap": True})
                elif a[0] == "pay":
                    atoms.append({"pay": a[1]})
                elif a[0] == "discard":
                    atoms.append({"discard": a[1]})
            alt.append({"all": atoms})
        exp["cost"] = {"alt": alt}
    return exp


SAMPLE = [
    ("bdb5452e-d97f-409b-91d0-2664f39b09b8", "Cooking Campsite", {
        "cost_context": "activated_ability", "actor": "you", "ability_context": "activated",
        "restriction_timing": "sorcery", "selector": sel(card_types=["artifact"]),
        "cost": cost([("pay", "{3}"), "TAP", "SAC"])}),
    ("f21f9161-5945-40da-8da0-446f6a4a1c23", None, {
        "cost_context": "activated_ability", "actor": "you", "ability_context": "activated",
        "selector": sel(self=True), "cost": cost([("pay", "{1}"), "SAC"])}),
    ("4a6976f2-0bd5-449a-8fcf-f5a732ce22c1", None, {
        "cost_context": "additional_cast_cost", "actor": "you", "ability_context": "cast",
        "selector": sel(card_types=["creature"], supertypes=["legendary"]),
        "cost": cost(["SAC"], [("pay", "{2}")])}),
    ("162a415c-5465-497e-8f4e-c6f09681641d", None, {
        "cost_context": "activated_ability", "actor": "you", "ability_context": "activated",
        "selector": sel(card_types=["artifact", "creature"], or_types=True, another=True),
        "cost": cost([("pay", "{3}"), "SAC"])}),
    ("7a50d2ac-101d-41e1-b400-18fa7d2d7125", None, {
        "cost_context": "activated_ability", "actor": "you", "ability_context": "activated",
        "selector": sel(card_types=["artifact", "creature"], or_types=True, another=True),
        "cost": cost(["SAC"])}),
    ("688fcf8a-0a44-416a-8086-83acf9a6fe69", None, {
        "cost_context": "resolution_effect", "actor": "target_opponent", "ability_context": "resolution",
        "selector": sel(card_types=["creature"]), "cost": None}),
    ("a4ee8ba5-6a79-4652-b2a4-a3dae804bc28", None, {
        "cost_context": "resolution_effect", "actor": "each_player", "ability_context": "triggered_etb",
        "modal": True, "selector": sel(card_types=["creature"], qualifiers=["token"]), "cost": None}),
    ("6de6d23b-7d42-41c1-be1c-010fe43ee586", None, {
        "cost_context": "kicker", "actor": "you", "ability_context": "cast",
        "selector": sel(card_types=["artifact", "creature"], or_types=True), "cost": cost(["SAC"])}),
    ("f9d25b34-990d-416c-aef7-1b5a73f19dd4", None, {
        "cost_context": "effect", "actor": "you", "ability_context": "triggered_attack",
        "selector": sel(card_types=["artifact", "creature"], or_types=True, another=True), "cost": None}),
    ("9ba292d5-5139-42ea-950d-0a638445277f", None, {
        "cost_context": "resolution_effect", "actor": "each_player", "ability_context": "triggered_etb",
        "selector": sel(card_types=["creature"], qualifiers=["non-god"], quantity="half_rounded_down"),
        "cost": None}),
    ("95318d85-4a08-47ac-a43d-ea83c0bea81c", None, {"is_outlet": False}),
]

HELDOUT = [
    ("a75a6ecc-a6a5-462c-bd92-ae57dde9b965", None, {
        "cost_context": "activated_ability", "actor": "you", "ability_context": "activated",
        "selector": sel(self=True), "cost": cost([("pay", "{7}"), "TAP", "SAC"])}),
    ("85eaf5e7-77dc-4842-a70c-ce4ac7f724df", "Sephiroth, Fabled SOLDIER", {
        "cost_context": "effect", "actor": "you", "ability_context": "triggered_etb_or_attack",
        "selector": sel(card_types=["creature"], another=True), "cost": None}),
    ("c3eb2ae5-10de-4c3d-91c8-8734befc80b2", "Yiazmat, Ultimate Mark", {
        "cost_context": "activated_ability", "actor": "you", "ability_context": "activated",
        "selector": sel(card_types=["artifact", "creature"], or_types=True, another=True),
        "cost": cost([("pay", "{1}{B}"), "SAC"])}),
    ("4ec91fe8-b3da-47fa-b45e-94b62a260aba", "Braska's Final Aeon", {
        "cost_context": "resolution_effect", "actor": "each_opponent", "ability_context": "resolution",
        "selector": sel(card_types=["creature"], quantity=2), "cost": None}),
    ("aa4f6703-21f8-4c29-ad5a-5afb54188ade", None, {
        "cost_context": "resolution_effect", "actor": "each_opponent", "ability_context": "resolution",
        "selector": sel(card_types=["creature"]), "cost": None}),
    ("70f47277-ca47-428a-808f-0fb32e820a71", None, {
        "cost_context": "activated_ability", "actor": "you", "ability_context": "activated",
        "restriction_timing": "sorcery", "selector": sel(self=True), "cost": cost(["TAP", "SAC"])}),
]


def _text(card, face_name):
    if face_name is None:
        return card.get("oracle_text", "")
    for f in card.get("card_faces", []):
        if f.get("name") == face_name:
            return f.get("oracle_text", "")
    raise SystemExit(f"face {face_name!r} not found on {card['name']}")


def _emit(cards, sample, out):
    lines = []
    for cid, face, meta in sample:
        c = cards[cid]
        rec = {"name": (face or c["name"]), "id": cid, "set": c["set"],
               "collector_number": c["collector_number"], "oracle_text": _text(c, face),
               "expected": _expand(meta)}
        lines.append(json.dumps(rec, ensure_ascii=False))
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {len(lines)} FIN records -> {out.relative_to(REPO)}")


def main():
    cards = {c["id"]: c for c in json.load(io.open(SRC, encoding="utf-8"))}
    _emit(cards, SAMPLE, OUT)
    _emit(cards, HELDOUT, OUT_HELD)


if __name__ == "__main__":
    main()

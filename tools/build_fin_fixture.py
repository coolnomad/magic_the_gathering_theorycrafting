"""Generate tests/fixtures/fin_sacrifice.jsonl from the real Scryfall FIN dump.

The Oracle text is copied BYTE-FOR-BYTE from data/raw/fin/scryfall_fin.json (by Scryfall id / face)
— never hand-typed — so the fixture is provenanced real second-set text. Only the `expected`
structured record is hand-authored here: it is my manual adjudication of each clause, against which
`sac_schema.parse_structured` is scored field-by-field. Deterministic; no Date/random.
"""
import io
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / "data/raw/fin/scryfall_fin.json"
OUT = REPO / "tests/fixtures/fin_sacrifice.jsonl"
OUT_HELD = REPO / "tests/fixtures/fin_sacrifice_heldout.jsonl"

# (scryfall id, face-name-or-None, adjudicated expected structured record). Face-name picks a
# specific card_faces entry for DFCs; None = use the top-level oracle_text.
SAMPLE = [
    # activated ability: mana + tap + sacrifice(artifact), sorcery-timing restriction
    ("bdb5452e-d97f-409b-91d0-2664f39b09b8", "Cooking Campsite", {
        "is_outlet": True, "cost_context": "activated_ability", "actor": "you",
        "ability_context": "activated", "modal": False,
        "sel_card_types": ["artifact"], "sel_or_types": False, "sel_supertypes": [],
        "sel_qualifiers": [], "sel_self": False, "sel_another": False, "sel_quantity": 1,
        "cost": ["[['pay={3}'], ['sacrifice=True'], ['tap=True']]"], "restriction_timing": "sorcery"}),
    # activated ability: self-sacrifice by the card's own name
    ("f21f9161-5945-40da-8da0-446f6a4a1c23", None, {
        "is_outlet": True, "cost_context": "activated_ability", "actor": "you",
        "ability_context": "activated", "modal": False,
        "sel_card_types": [], "sel_or_types": False, "sel_supertypes": [],
        "sel_qualifiers": [], "sel_self": True, "sel_another": False, "sel_quantity": 1,
        "cost": ["[['pay={1}'], ['sacrifice=True']]"], "restriction_timing": None}),
    # additional cast cost with a real ALT: sacrifice(legendary creature) OR pay {2}
    ("4a6976f2-0bd5-449a-8fcf-f5a732ce22c1", None, {
        "is_outlet": True, "cost_context": "additional_cast_cost", "actor": "you",
        "ability_context": "cast", "modal": False,
        "sel_card_types": ["creature"], "sel_or_types": False, "sel_supertypes": ["legendary"],
        "sel_qualifiers": [], "sel_self": False, "sel_another": False, "sel_quantity": 1,
        "cost": ["[['pay={2}']]", "[['sacrifice=True']]"], "restriction_timing": None}),
    # activated ability: ALT within the selector (artifact OR creature), 'another', mana cost
    ("162a415c-5465-497e-8f4e-c6f09681641d", None, {
        "is_outlet": True, "cost_context": "activated_ability", "actor": "you",
        "ability_context": "activated", "modal": False,
        "sel_card_types": ["artifact", "creature"], "sel_or_types": True, "sel_supertypes": [],
        "sel_qualifiers": [], "sel_self": False, "sel_another": True, "sel_quantity": 1,
        "cost": ["[['pay={3}'], ['sacrifice=True']]"], "restriction_timing": None}),
    # activated ability with NO mana in the cost (bare 'Sacrifice ...:'), or-selector, 'another'
    ("7a50d2ac-101d-41e1-b400-18fa7d2d7125", None, {
        "is_outlet": True, "cost_context": "activated_ability", "actor": "you",
        "ability_context": "activated", "modal": False,
        "sel_card_types": ["artifact", "creature"], "sel_or_types": True, "sel_supertypes": [],
        "sel_qualifiers": [], "sel_self": False, "sel_another": True, "sel_quantity": 1,
        "cost": ["[['sacrifice=True']]"], "restriction_timing": None}),
    # edict: target opponent sacrifices (a spell resolution effect, NOT an activated cost)
    ("688fcf8a-0a44-416a-8086-83acf9a6fe69", None, {
        "is_outlet": True, "cost_context": "resolution_effect", "actor": "target_opponent",
        "ability_context": "resolution", "modal": False,
        "sel_card_types": ["creature"], "sel_or_types": False, "sel_supertypes": [],
        "sel_qualifiers": [], "sel_self": False, "sel_another": False, "sel_quantity": 1,
        "cost": None, "restriction_timing": None}),
    # modal edict inside an ETB trigger: each player sacrifices (choose one of three fodder types)
    ("a4ee8ba5-6a79-4652-b2a4-a3dae804bc28", None, {
        "is_outlet": True, "cost_context": "resolution_effect", "actor": "each_player",
        "ability_context": "triggered_etb", "modal": True,
        "sel_card_types": ["creature"], "sel_or_types": False, "sel_supertypes": [],
        "sel_qualifiers": ["token"], "sel_self": False, "sel_another": False, "sel_quantity": 1,
        "cost": None, "restriction_timing": None}),
    # kicker as a distinct cost context; or-selector
    ("6de6d23b-7d42-41c1-be1c-010fe43ee586", None, {
        "is_outlet": True, "cost_context": "kicker", "actor": "you",
        "ability_context": "cast", "modal": False,
        "sel_card_types": ["artifact", "creature"], "sel_or_types": True, "sel_supertypes": [],
        "sel_qualifiers": [], "sel_self": False, "sel_another": False, "sel_quantity": 1,
        "cost": ["[['sacrifice=True']]"], "restriction_timing": None}),
    # optional effect ('you may sacrifice') inside an attack trigger; or-selector, 'another'
    ("f9d25b34-990d-416c-aef7-1b5a73f19dd4", None, {
        "is_outlet": True, "cost_context": "effect", "actor": "you",
        "ability_context": "triggered_attack", "modal": False,
        "sel_card_types": ["artifact", "creature"], "sel_or_types": True, "sel_supertypes": [],
        "sel_qualifiers": [], "sel_self": False, "sel_another": True, "sel_quantity": 1,
        "cost": None, "restriction_timing": None}),
    # edict with a FRACTIONAL quantity + qualifier (non-God), inside an ETB trigger
    ("9ba292d5-5139-42ea-950d-0a638445277f", None, {
        "is_outlet": True, "cost_context": "resolution_effect", "actor": "each_player",
        "ability_context": "triggered_etb", "modal": False,
        "sel_card_types": ["creature"], "sel_or_types": False, "sel_supertypes": [],
        "sel_qualifiers": ["non-god"], "sel_self": False, "sel_another": False,
        "sel_quantity": "half_rounded_down", "cost": None, "restriction_timing": None}),
    # true negative: a Saga "Sacrifice after IV" self-timer is NOT a fodder-selection outlet
    ("95318d85-4a08-47ac-a43d-ea83c0bea81c", None, {"is_outlet": False}),
]

# HELD-OUT set: real FIN cards the parser was NEVER tuned against. Adjudicated to the rules (not to
# the parser); the parser is frozen and scored ONCE. Failures here are honest portability evidence
# (a lower held-out score than the dev set is expected and is the point).
HELDOUT = [
    # activated: mana + tap + self-sacrifice (self quantity defaults to 1)
    ("a75a6ecc-a6a5-462c-bd92-ae57dde9b965", None, {
        "is_outlet": True, "cost_context": "activated_ability", "actor": "you",
        "ability_context": "activated", "modal": False,
        "sel_card_types": [], "sel_or_types": False, "sel_supertypes": [], "sel_qualifiers": [],
        "sel_self": True, "sel_another": False, "sel_quantity": 1,
        "cost": ["[['pay={7}'], ['sacrifice=True'], ['tap=True']]"], "restriction_timing": None}),
    # optional effect under a DUAL 'enters or attacks' trigger (schema has no dual-context value yet)
    ("85eaf5e7-77dc-4842-a70c-ce4ac7f724df", "Sephiroth, Fabled SOLDIER", {
        "is_outlet": True, "cost_context": "effect", "actor": "you",
        "ability_context": "triggered_etb_or_attack", "modal": False,
        "sel_card_types": ["creature"], "sel_or_types": False, "sel_supertypes": [], "sel_qualifiers": [],
        "sel_self": False, "sel_another": True, "sel_quantity": 1,
        "cost": None, "restriction_timing": None}),
    # activated: multi-symbol mana {1}{B} (one cost, adjudicated as one pay atom), or-selector, another
    ("c3eb2ae5-10de-4c3d-91c8-8734befc80b2", "Yiazmat, Ultimate Mark", {
        "is_outlet": True, "cost_context": "activated_ability", "actor": "you",
        "ability_context": "activated", "modal": False,
        "sel_card_types": ["artifact", "creature"], "sel_or_types": True, "sel_supertypes": [],
        "sel_qualifiers": [], "sel_self": False, "sel_another": True, "sel_quantity": 1,
        "cost": ["[['pay={1}{B}'], ['sacrifice=True']]"], "restriction_timing": None}),
    # Saga-chapter edict: each opponent sacrifices TWO creatures (quantity 2)
    ("4ec91fe8-b3da-47fa-b45e-94b62a260aba", "Braska's Final Aeon", {
        "is_outlet": True, "cost_context": "resolution_effect", "actor": "each_opponent",
        "ability_context": "resolution", "modal": False,
        "sel_card_types": ["creature"], "sel_or_types": False, "sel_supertypes": [], "sel_qualifiers": [],
        "sel_self": False, "sel_another": False, "sel_quantity": 2,
        "cost": None, "restriction_timing": None}),
    # Saga-chapter edict: each opponent sacrifices a creature
    ("aa4f6703-21f8-4c29-ad5a-5afb54188ade", None, {
        "is_outlet": True, "cost_context": "resolution_effect", "actor": "each_opponent",
        "ability_context": "resolution", "modal": False,
        "sel_card_types": ["creature"], "sel_or_types": False, "sel_supertypes": [], "sel_qualifiers": [],
        "sel_self": False, "sel_another": False, "sel_quantity": 1,
        "cost": None, "restriction_timing": None}),
    # activated: tap-only self-sacrifice with a sorcery-timing restriction (no mana)
    ("70f47277-ca47-428a-808f-0fb32e820a71", None, {
        "is_outlet": True, "cost_context": "activated_ability", "actor": "you",
        "ability_context": "activated", "modal": False,
        "sel_card_types": [], "sel_or_types": False, "sel_supertypes": [], "sel_qualifiers": [],
        "sel_self": True, "sel_another": False, "sel_quantity": 1,
        "cost": ["[['sacrifice=True'], ['tap=True']]"], "restriction_timing": "sorcery"}),
]


def _text(card: dict, face_name):
    if face_name is None:
        return card.get("oracle_text", "")
    for f in card.get("card_faces", []):
        if f.get("name") == face_name:
            return f.get("oracle_text", "")
    raise SystemExit(f"face {face_name!r} not found on {card['name']}")


def _emit(cards, sample, out):
    lines = []
    for cid, face, expected in sample:
        c = cards[cid]
        rec = {"name": (face or c["name"]), "id": cid, "set": c["set"],
               "collector_number": c["collector_number"], "oracle_text": _text(c, face),
               "expected": expected}
        lines.append(json.dumps(rec, ensure_ascii=False))
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {len(lines)} FIN records -> {out.relative_to(REPO)}")


def main():
    cards = {c["id"]: c for c in json.load(io.open(SRC, encoding="utf-8"))}
    _emit(cards, SAMPLE, OUT)
    _emit(cards, HELDOUT, OUT_HELD)


if __name__ == "__main__":
    main()

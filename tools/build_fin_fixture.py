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
OUT_SETWIDE = REPO / "tests/fixtures/fin_sacrifice_setwide.jsonl"


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


# --------------------------------------------------------------------------- #
#  SET-WIDE: every FIN face containing "sacrif", adjudicated outlet/non-outlet   #
#  (review pt1 #1). Adjudication rule (stated in reports/labnotebook):           #
#   OUTLET = a player sacrifices a permanent as an operative action — an         #
#   activated/additional/kicker COST, an optional/resolution EFFECT, or an       #
#   EDICT. NON-OUTLET = (a) parenthetical REMINDER text (Saga "Sacrifice after   #
#   N"; a created token's "{T}, Sacrifice this token"); (b) a "Whenever a player #
#   sacrifices…" trigger CONDITION; (c) automatic CONSEQUENCE/cleanup (delayed   #
#   "Sacrifice it at the beginning of…"; a self-destruction drawback).           #
#  This fixture is authored AFTER the parser was frozen (commit A) and scored    #
#  once; agent-authored reference annotations, NOT an independent human gold set.#
# --------------------------------------------------------------------------- #
NON = {"is_outlet": False}
_ARTC_OR = dict(card_types=["artifact", "creature"], or_types=True)


def O(*clauses):
    return {"is_outlet": True, "clauses": list(clauses)}


def C(cost_context, actor, ability_context, selector, cost=None, modal=False, restriction_timing=None):
    return {"cost_context": cost_context, "actor": actor, "ability_context": ability_context,
            "selector": selector, "cost": cost, "modal": modal, "restriction_timing": restriction_timing}


# keyed by Scryfall id (+ face for DFCs), in collector order
SETWIDE = [
    ("95318d85-4a08-47ac-a43d-ea83c0bea81c", None, NON),                       # Summon: Bahamut — Saga timer
    ("5f51c853-949d-44e9-a3a2-02e1ce69a147", "Summon: Alexander", NON),         # Saga timer
    ("bdb5452e-d97f-409b-91d0-2664f39b09b8", "Cooking Campsite",
     O(C("activated_ability", "you", "activated", sel(card_types=["artifact"]),
         cost([("pay", "{3}"), "TAP", "SAC"]), restriction_timing="sorcery"))),
    ("00546117-018a-4286-bc20-b5446c5be56f", None, NON),                        # Summon: Choco/Mog — Saga timer
    ("44d23652-077e-4c1f-b640-b284685db911", None, NON),                        # Summon: Knights of Round
    ("e44497a8-067e-454e-a9c0-684f03df55ff", None, NON),                        # Summon: Primal Garuda
    ("f21f9161-5945-40da-8da0-446f6a4a1c23", None,
     O(C("activated_ability", "you", "activated", sel(self=True), cost([("pay", "{1}"), "SAC"])))),  # Zack Fair
    ("4a6976f2-0bd5-449a-8fcf-f5a732ce22c1", None,
     O(C("additional_cast_cost", "you", "cast", sel(card_types=["creature"], supertypes=["legendary"]),
         cost(["SAC"], [("pay", "{2}")])))),                                     # Louisoix's Sacrifice
    ("a75a6ecc-a6a5-462c-bd92-ae57dde9b965", None,
     O(C("activated_ability", "you", "activated", sel(self=True), cost([("pay", "{7}"), "TAP", "SAC"])))),  # Qiqirn
    ("c96cae63-7625-48e3-aaba-5b1632a8642d", None, NON),                        # Sleep Magic — self-destruct drawback
    ("ea7f26a9-b203-4ee7-88f1-3d9c77a25bcb", None, NON),                        # Summon: Leviathan
    ("a80511f8-7cb1-4974-afde-8a5cebe13ad7", None, NON),                        # Summon: Shiva
    ("162a415c-5465-497e-8f4e-c6f09681641d", None,
     O(C("activated_ability", "you", "activated", sel(**_ARTC_OR, another=True),
         cost([("pay", "{3}"), "SAC"])))),                                      # Ahriman
    ("688fcf8a-0a44-416a-8086-83acf9a6fe69", None,
     O(C("resolution_effect", "target_opponent", "resolution", sel(card_types=["creature"])))),  # Cornered
    ("a4ee8ba5-6a79-4652-b2a4-a3dae804bc28", None,
     O(C("resolution_effect", "each_player", "triggered_etb",
         sel(card_types=["creature"], qualifiers=["token"]), modal=True))),     # Gaius (modal)
    ("4ec91fe8-b3da-47fa-b45e-94b62a260aba", "Braska's Final Aeon",
     O(C("resolution_effect", "each_opponent", "resolution", sel(card_types=["creature"], quantity=2)))),  # Braska
    ("f9d25b34-990d-416c-aef7-1b5a73f19dd4", None,
     O(C("effect", "you", "triggered_attack", sel(**_ARTC_OR, another=True)))),  # Namazu Trader
    ("7a50d2ac-101d-41e1-b400-18fa7d2d7125", None,
     O(C("activated_ability", "you", "activated", sel(**_ARTC_OR, another=True), cost(["SAC"])))),  # Phantom Train
    ("b5eb0064-c7c4-4e3e-add2-b86269de3fb9", None,
     O(C("effect", "you", "triggered_other", sel(**_ARTC_OR, another=True)))),  # Reno and Rude
    ("85eaf5e7-77dc-4842-a70c-ce4ac7f724df", "Sephiroth, Fabled SOLDIER",
     O(C("effect", "you", "triggered_etb_or_attack", sel(card_types=["creature"], another=True)))),  # Sephiroth FS
    ("85eaf5e7-77dc-4842-a70c-ce4ac7f724df", "Sephiroth, One-Winged Angel",
     O(C("effect", "you", "triggered_attack", sel(card_types=["creature"], another=True, quantity="any")))),  # OWA
    ("c3eb2ae5-10de-4c3d-91c8-8734befc80b2", "Yiazmat, Ultimate Mark",
     O(C("activated_ability", "you", "activated", sel(**_ARTC_OR, another=True),
         cost([("pay", "{1}{B}"), "SAC"])))),                                   # Yiazmat
    ("aa4f6703-21f8-4c29-ad5a-5afb54188ade", None,
     O(C("resolution_effect", "each_opponent", "resolution", sel(card_types=["creature"])))),  # Summon: Anima
    ("8b1b5f06-e34d-44a3-976e-5157c4b7a0f4", None, NON),                        # Summon: Primal Odin
    ("274788f4-fbf3-4a15-bdc0-f513a2fde30d", None, NON),                        # Undercity Dire Rat — Treasure reminder
    ("6de6d23b-7d42-41c1-be1c-010fe43ee586", None,
     O(C("kicker", "you", "cast", sel(**_ARTC_OR), cost(["SAC"])))),           # Vayne's Treachery
    ("9ba292d5-5139-42ea-950d-0a638445277f", None,
     O(C("resolution_effect", "each_player", "triggered_etb",
         sel(card_types=["creature"], qualifiers=["non-god"], quantity="half_rounded_down")))),  # Zodiark
    ("70f47277-ca47-428a-808f-0fb32e820a71", None,
     O(C("activated_ability", "you", "activated", sel(self=True), cost(["TAP", "SAC"]),
         restriction_timing="sorcery"))),                                       # Blazing Bomb
    ("ea430b17-2014-4b8e-b53f-43bcfc06f7cd", None, NON),                        # The Fire Crystal — delayed token cleanup
    ("98366937-d15b-4a66-b9f6-878d50b63871", None, NON),                        # Firion — delayed token cleanup
    ("8ab5429a-1075-49aa-9608-0610080fbf7a", None, NON),                        # Summon: Brynhildr
    ("840659ee-1493-4190-a514-c2c9ae14e331", None, NON),                        # Summon: Esper Ramuh
    ("d0e5cbd4-401b-4456-80bf-d90beadfd1f8", None, NON),                        # Summon: G.F. Cerberus
    ("c6c73092-5195-4bdc-b039-a699f6e297b2", None, NON),                        # Summon: G.F. Ifrit
    ("0f503360-216a-4629-89b2-d32072850aef", "Summon: Esper Maduin", NON),      # Saga timer
    ("4f352b5e-9731-4a8e-b872-db5d3bf32211", None,
     O(C("activated_ability", "you", "activated", sel(quantity=1), cost([("pay", "{2}"), "SAC"])))),  # Quina — subtype 'Frog'
    ("32eb192b-de6b-4814-8077-628d343d014e", None, NON),                        # Summon: Fat Chocobo
    ("93feb9d5-d004-4598-a448-b3488c869c05", None, NON),                        # Summon: Fenrir
    ("5ce6ea96-7293-496d-b9c8-8ed6d6109a4d", None, NON),                        # Summon: Titan
    ("8fcf3fbb-1ddd-437e-81c1-f5a3133f5ee8", "Kefka, Court Mage",
     O(C("resolution_effect", "each_opponent", "activated", sel(quantity=1),
         restriction_timing="sorcery"))),                                       # Kefka — activated edict, generic permanent
    ("a67793ef-ef80-4434-9c54-e3fd8a270bbe", None, NON),                        # Tellah — self-sac consequence
    ("fbd447aa-588d-4c4d-925e-a7d3bdf6a65c", "Esper Terra", NON),               # delayed token cleanup
    ("92f4ad73-42bf-45c0-8bb6-0b44043c81ef", None,
     O(C("activated_ability", "you", "activated", sel(self=True), cost(["TAP", "SAC"])))),  # Blitzball
    ("ef7011f4-fc08-4b15-973d-d15357cbe744", None,
     O(C("activated_ability", "you", "activated", sel(self=True), cost([("pay", "{2}"), "TAP", "SAC"])))),  # Instant Ramen
    ("d6e1e3e7-20d4-42cb-ad22-60356b9e8fdc", None,
     O(C("activated_ability", "you", "activated", sel(self=True), cost([("pay", "{6}"), "TAP", "SAC"])))),  # Lunatic Pandora
    ("57d07ca0-5618-4a90-a605-ca14a193ce3b", None, NON),                        # Magic Pot — Treasure reminder
    ("70d9ab99-ec8a-402e-ba1d-ffa6c4c84a3f", None,
     O(C("activated_ability", "you", "activated", sel(self=True), cost([("pay", "{1}"), "TAP", "SAC"])),
       C("activated_ability", "you", "activated", sel(self=True), cost([("pay", "{3}"), "TAP", "SAC"])))),  # World Map (2)
    ("e28eac1e-adc7-4f8d-b206-bef09ba07d38", None,
     O(C("effect", "you", "activated", sel(self=True)))),                       # Eden — optional self-sac in an activated ability
    ("5363c881-443d-43df-afd8-f81e1a1741a2", None,
     O(C("activated_ability", "you", "activated", sel(card_types=["artifact"], quantity=2),
         cost([("pay", "{3}"), "TAP", "SAC"])))),                               # The Gold Saucer — sacrifice TWO
    ("8a837256-6bb4-4a60-962d-d2793548d26c", "Reactor Raid",
     O(C("effect", "you", "resolution", sel(**_ARTC_OR)))),                     # Reactor Raid
]


def _expand_setwide(meta):
    if meta.get("is_outlet") is False:
        return {"is_outlet": False, "clauses": []}
    return {"is_outlet": True, "clauses": [_expand(c) for c in meta["clauses"]]}


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


def _emit_setwide(cards, out):
    lines = []
    for cid, face, meta in SETWIDE:
        c = cards[cid]
        rec = {"name": (face or c["name"]), "id": cid, "set": c["set"],
               "collector_number": c["collector_number"], "oracle_text": _text(c, face),
               "expected": _expand_setwide(meta)}
        lines.append(json.dumps(rec, ensure_ascii=False))
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    outlets = sum(1 for _, _, m in SETWIDE if m.get("is_outlet") is not False)
    print(f"wrote {len(lines)} FIN set-wide records ({outlets} outlet / {len(lines) - outlets} non-outlet) "
          f"-> {out.relative_to(REPO)}")


def main():
    cards = {c["id"]: c for c in json.load(io.open(SRC, encoding="utf-8"))}
    _emit(cards, SAMPLE, OUT)
    _emit(cards, HELDOUT, OUT_HELD)
    _emit_setwide(cards, OUT_SETWIDE)


if __name__ == "__main__":
    main()

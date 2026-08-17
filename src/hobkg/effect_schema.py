"""Effect-semantics schema (Phase 2): structured selectors, participants, modes, durations, effects —
plus deterministic eligibility resolvers. No card-name/UUID branching: a selector is parsed from a
target phrase and resolved against card/token CHARACTERISTICS.

A `Selector` is a structured description of an affected object:
  card_types, or_types, subtypes, supertypes, controller (you|opponent|any), quantity (1|up_to_1|…),
  exclusions (other/another/self), predicates (flying / power_ge N / token / nontoken), targeted,
  and a stable object-variable id `var`.
Controller is PARTICIPANT metadata, not a card-eligibility filter (any creature can be "yours" or "an
opponent's"), per the instructions (e.g. Meager Meal must not be restricted to creatures you control).
"""

from __future__ import annotations

import re

PERMANENT_TYPES = ["artifact", "creature", "enchantment", "planeswalker", "land", "battle"]
_TYPES_RE = re.compile(r"\b(" + "|".join(PERMANENT_TYPES + ["permanent"]) + r")s?\b", re.I)
_SUBTYPE_RE = re.compile(r"(?<!non-)\b([A-Z][a-z]{2,})\b")
_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


def selector(phrase: str, var: str = "x") -> dict:
    """Parse a post-'target'/'destroy' object phrase into a structured selector."""
    p = phrase.strip().rstrip(".")
    low = p.lower()
    types = sorted({m.group(1).lower() for m in _TYPES_RE.finditer(low)})
    generic_permanent = "permanent" in types
    types = [t for t in types if t != "permanent"]
    or_types = bool(re.search(r"\b" + _TYPES_RE.pattern + r"\s+or\s+" + _TYPES_RE.pattern, low)) and len(types) >= 2
    # subtypes are Title-Case in the ORIGINAL phrase (not lowercased)
    subtypes = sorted({m.group(1).lower() for m in _SUBTYPE_RE.finditer(p)})
    controller = "you" if "you control" in low else ("opponent" if re.search(r"opponent(?:s)? control|an opponent controls", low) else "any")
    m = re.search(r"up to (\w+)", low)
    quantity = f"up_to_{_NUM.get(m.group(1), m.group(1))}" if m else 1
    exclusions = [w for w in ("other", "another") if re.search(r"\b" + w + r"\b", low)]
    preds = {}
    if re.search(r"\bwith flying\b|\bflying\b", low):
        preds["flying"] = True
    pm = re.search(r"power (\d+) or greater", low)
    if pm:
        preds["power_ge"] = int(pm.group(1))
    if re.search(r"\btokens?\b", low):
        preds["token"] = True
    if re.search(r"\bnontoken\b", low):
        preds["nontoken"] = True
    return {"card_types": types, "or_types": or_types, "subtypes": subtypes,
            "generic_permanent": generic_permanent, "controller": controller, "quantity": quantity,
            "exclusions": sorted(exclusions), "predicates": preds, "targeted": "target" in low, "var": var}


# --------------------------------------------------------------------------- #
#  Deterministic eligibility: which cards / token specs a selector can match     #
# --------------------------------------------------------------------------- #
def _kw(face, kw: str) -> bool:
    """A face HAS keyword `kw` if it appears NOT in a grant/reference context ('gains flying', 'with
    flying', 'creatures … have flying')."""
    ot = face.get("oracle_text") or ""
    for m in re.finditer(r"\b" + kw + r"\b", ot, re.I):
        pre = ot[max(0, m.start() - 14):m.start()].lower()
        if not re.search(r"(gains?|have|has|with|grant[s]?|of) $|(gains?|have|has|with|grant[s]?) \w* $", pre):
            if not re.search(r"(gains?|have|has|with|grant[s]?) $", pre):
                return True
    return False


def _power(obj):
    p = obj.get("power")
    if isinstance(p, int):
        return p
    if isinstance(p, str) and re.fullmatch(r"-?\d+", p.strip()):
        return int(p)                                       # power is stored as a string ("2", "*", …)
    return None                                             # '*'/variable → no fixed power


def _face_types(face):
    tl = face.get("type_line") or {}
    return {"types": [t.lower() for t in tl.get("types", [])],
            "subtypes": [t.lower() for t in tl.get("subtypes", [])],
            "supertypes": [t.lower() for t in tl.get("supertypes", [])]}


def matches_card(sel: dict, face: dict) -> bool:
    t = _face_types(face)
    if not t["types"]:
        return False
    if sel["predicates"].get("token") and not sel["predicates"].get("nontoken"):
        return False                                       # a nontoken CARD cannot be a 'token' target
    if sel["card_types"]:
        if not any(ct in t["types"] for ct in sel["card_types"]):
            return False
    elif not sel["generic_permanent"] and not sel["subtypes"]:
        return False                                       # need SOME type/subtype constraint to match a card
    if sel["generic_permanent"] and not (set(t["types"]) & set(PERMANENT_TYPES)):
        return False
    if sel["subtypes"] and not (set(sel["subtypes"]) & set(t["subtypes"])):
        return False
    if sel["predicates"].get("flying") and not _kw(face, "flying"):
        return False
    pg = sel["predicates"].get("power_ge")
    if pg is not None and (_power(face) is None or _power(face) < pg):
        return False
    return True


def matches_token(sel: dict, tok: dict) -> bool:
    tl = tok.get("type_line") or {}
    types = [t.lower() for t in tl.get("types", [])]
    subs = [t.lower() for t in tl.get("subtypes", [])]
    if sel["predicates"].get("nontoken"):
        return False
    if sel["card_types"] and not any(ct in types for ct in sel["card_types"]):
        return False
    if sel["generic_permanent"] and not (set(types) & set(PERMANENT_TYPES)):
        return False
    if sel["subtypes"] and not (set(sel["subtypes"]) & set(subs)):
        return False
    if sel["predicates"].get("flying") and "flying" not in [k.lower() for k in (tok.get("keywords") or [])]:
        return False
    pg = sel["predicates"].get("power_ge")
    if pg is not None:
        pw = _power(tok)
        if pw is None or pw < pg:
            return False
    return True

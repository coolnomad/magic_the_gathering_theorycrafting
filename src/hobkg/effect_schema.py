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
_SUPERTYPES = ["legendary", "basic", "snow", "world"]
_PLURAL_SUB = {"wolves": "wolf", "elves": "elf", "dwarves": "dwarf"}
_VOCAB = {}


# Oracle-recognized subtypes that HOB REFERENCES but does not instantiate (review pt3): kept in the
# selector vocabulary even though the projection currently finds zero such objects.
_ORACLE_EXTRA_SUBTYPES = {"orc"}


def _subtype_vocab():
    """The subtype vocabulary = every subtype printed on a HOB face/token, PLUS Oracle-referenced but
    currently-uninstantiated subtypes (e.g. Orc) so 'target Goblin or Orc' stays semantically complete."""
    if "v" not in _VOCAB:
        from .pipeline import REPO, _load_dicts
        v = set(_ORACLE_EXTRA_SUBTYPES)
        for rel in ("data/normalized/faces.jsonl", "data/normalized/tokens.jsonl"):
            try:
                for r in _load_dicts(REPO / rel):
                    v |= {s.lower() for s in (r.get("type_line") or {}).get("subtypes", [])}
            except Exception:
                pass
        _VOCAB["v"] = v
    return _VOCAB["v"]


def _valid_subtypes(phrase: str):
    """Title-Case tokens VALIDATED against the subtype vocabulary (rejects syntax words like
    'Target', 'Until', 'Whenever', 'Each', 'Creatures', 'Landfall', 'Saga'). Plurals normalized."""
    vocab = _subtype_vocab()
    out = set()
    for m in _SUBTYPE_RE.finditer(phrase):
        w = m.group(1).lower()
        if w in _SUPERTYPES:
            continue
        cand = _PLURAL_SUB.get(w, w)
        if cand in vocab:
            out.add(cand)
        elif cand.rstrip("s") in vocab:
            out.add(cand.rstrip("s"))
    return out
_SUPER_RE = re.compile(r"\b(" + "|".join(_SUPERTYPES) + r")\b", re.I)
_NUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5}


def selector(phrase: str, var: str = "x", targeted=None, quantifier=None) -> dict:
    """Parse a post-'target'/'destroy' object phrase into a structured selector. `targeted` /
    `quantifier` can be passed by the caller when the governing verb already consumed 'target'/'each'
    /'all' (e.g. `_DESTROY_RE` strips 'target' before this sees the phrase)."""
    p = phrase.strip().rstrip(".")
    low = p.lower()
    types = sorted({m.group(1).lower() for m in _TYPES_RE.finditer(low)})
    generic_permanent = "permanent" in types
    types = [t for t in types if t != "permanent"]
    # OR vs AND: "artifact or enchantment" is a disjunction; "artifact creature" (adjacent, no 'or')
    # is a conjunction requiring BOTH types.
    # OR when "X or Y" OR when plural classes are joined by "and" ("artifacts and creatures" = union,
    # NOT the conjunction "artifact creature" which needs both) — review pt2 #8
    or_types = (bool(re.search(r"\b" + _TYPES_RE.pattern + r"\s+or\s+" + _TYPES_RE.pattern, low))
                or bool(re.search(r"\b\w+s\s+and\s+\w+s\b", low))) and len(types) >= 2
    supertypes = sorted({m.group(1).lower() for m in _SUPER_RE.finditer(low)})
    subtypes = sorted(_valid_subtypes(p))                   # vocabulary-validated (review pt2 #1)
    controller = "you" if "you control" in low else ("opponent" if re.search(r"opponent(?:s)? control|an opponent controls", low) else "any")
    owner = "you" if "you own" in low else ("opponent" if "opponent owns" in low else None)
    zone = _zone(low)
    if quantifier is None:
        if re.search(r"\beach\b", low):
            quantifier = "each"
        elif re.search(r"\ball\b", low):
            quantifier = "all"
        else:
            um = re.search(r"up to (\w+)", low)
            quantifier = (f"up_to_{_NUM.get(um.group(1), um.group(1))}" if um else ("target" if "target" in low else None))
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
    if re.search(r"\bnonland\b", low):
        preds["nonland"] = True
    cm = re.search(r"with (?:a|an|one or more) (\+1/\+1|\-1/\-1|\w+) counter", low)
    if cm:
        preds["has_counter"] = cm.group(1)                  # e.g. Great Ugly '… with a +1/+1 counter on it'
    is_target = ("target" in low) if targeted is None else bool(targeted)
    mass = quantifier in ("each", "all")
    return {"card_types": types, "or_types": or_types, "subtypes": subtypes, "supertypes": supertypes,
            "generic_permanent": generic_permanent, "controller": controller, "owner": owner,
            "zone": zone, "quantifier": quantifier, "exclusions": sorted(exclusions),
            "predicates": preds, "targeted": is_target, "affects_each": mass, "var": var}


def _zone(low: str) -> str:
    if "graveyard" in low:
        return "graveyard"
    if "in exile" in low or "from exile" in low:
        return "exile"
    if "in your hand" in low or "from your hand" in low:
        return "hand"
    if "library" in low:
        return "library"
    return "battlefield"                                    # permanents default to the battlefield


def participant(phrase: str) -> str:
    """Resolve the participant a clause acts on/through."""
    low = phrase.lower()
    if re.search(r"\beach opponent\b", low):
        return "each_opponent"
    if re.search(r"\beach player\b", low):
        return "each_player"
    if re.search(r"\btarget opponent\b", low):
        return "target_opponent"
    if re.search(r"\btarget player\b", low):
        return "target_player"
    if re.search(r"\bits controller\b|\bthat player\b", low):
        return "controller"
    if re.search(r"\bits owner\b|\bthat card's owner\b", low):
        return "owner"
    return "you"


def duration(text: str):
    low = text.lower()
    if "until end of turn" in low:
        return "until_end_of_turn"
    if "until your next turn" in low:
        return "until_your_next_turn"
    if "this turn" in low:
        return "this_turn"
    return None


def condition(text: str):
    """Classify a clause's condition. CRUCIAL taxonomy (review pt2b): an `intervening_if` is part of a
    TRIGGER clause ("Whenever X, if Y, do Z" — Y gates whether the ability triggers/resolves); an
    ordinary `If …` instruction evaluated during resolution is a `conditional_effect`. Misusing
    intervening_if would mislabel the many ordinary `if`s in later families."""
    low = text.lower()
    if re.search(r"\bif this spell was cast from a graveyard\b|\bcast from a graveyard\b", low):
        return {"kind": "cast_from_graveyard"}
    if re.search(r"\bif this spell was kicked\b|\bkicker\b", low):
        return {"kind": "kicker"}
    if re.search(r"as long as you have an enduring story", low):
        return {"kind": "gate", "gate": "enduring_story"}          # HOB Storied gate (review pt3 #1)
    m = re.search(r"as long as you control (?:another|an|a)\s+([A-Z][a-z]+)", text)
    if m:
        return {"kind": "controls_another", "subtype": m.group(1).lower()}
    if re.search(r"\bthreshold\b", low):
        return {"kind": "threshold", "detail": "seven_or_more_cards_in_graveyard"}
    if not re.search(r"\bif\b", low):
        return None
    # intervening-if only when the `if` sits inside a triggered-ability trigger clause
    trigger = re.match(r"\s*(?:when|whenever|at the beginning of)\b", low)
    inter = bool(trigger and re.search(r",\s*if\b", low))
    cond = {"kind": "intervening_if" if inter else "conditional_effect"}
    if "dealt damage this way" in low:
        cond["predicate"] = "dealt_damage_this_way"
    return cond


_EFFECT_REQUIRED = ("effect_id", "op", "relation", "participant", "selector", "mode", "targeted")


def selector_is_empty(sel: dict) -> bool:
    """An object selector is empty if it constrains no object at all (no type/subtype/supertype/
    generic-permanent) AND is not a self reference."""
    return not (sel.get("card_types") or sel.get("subtypes") or sel.get("supertypes")
                or sel.get("generic_permanent") or sel.get("self"))


def participant_selector(var: str = "p0") -> dict:
    """A participant-level record (draw / life / mill / etc.) acts on a PLAYER, not an object. It
    carries an intentionally empty object selector flagged `participant_level` so `validate_effect`
    does not demand an object binding and `build_effects` does not fan it out to card pairs."""
    return {"card_types": [], "or_types": [], "subtypes": [], "supertypes": [], "quantifier": None,
            "targeted": False, "var": var, "participant_level": True}


def validate_effect(rec: dict) -> list:
    """Return a list of schema violations for an effect record (empty = valid). An OBJECT-directed
    relation may not validate with an empty object selector unless an explicit self/antecedent binding
    supplies the object (review PHASE3 pt1 #6)."""
    errs = []
    for k in _EFFECT_REQUIRED:
        if k not in rec:
            errs.append(f"missing {k}")
    sel = rec.get("selector") or {}
    for k in ("card_types", "or_types", "subtypes", "supertypes", "quantifier", "targeted", "var"):
        if k not in sel:
            errs.append(f"selector missing {k}")
    mode = rec.get("mode")
    if not isinstance(mode, dict) or "kind" not in mode or "index" not in mode:
        errs.append("mode must be {kind, index}")
    if rec.get("targeted") not in (True, False):
        errs.append("targeted must be boolean")
    if rec.get("relation", "").startswith(("CAN_", "ADDS_", "MODIFIES_", "GRANTS_", "CHANGES_",
                                           "REMOVES_", "SETS_", "SWITCHES_", "GAINS_", "EXCHANGES_",
                                           "PREVENTS_")) and not sel.get("participant_level"):
        if selector_is_empty(sel) and not rec.get("binding") and not sel.get("self"):
            errs.append("object relation with empty object selector and no self/antecedent binding")
    # a participant-level record must name a participant and carry no object_var
    if sel.get("participant_level"):
        if not rec.get("participant"):
            errs.append("participant-level record missing participant")
        if rec.get("object_var") is not None:
            errs.append("participant-level record must not carry object_var")
    # the effect's object_var must match its selector's var (unless an explicit binding says otherwise)
    if "object_var" in rec and not rec.get("binding") and sel.get("var") not in (rec["object_var"], None):
        errs.append(f"object_var {rec['object_var']} != selector.var {sel.get('var')}")
    return errs


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


def _type_ok(sel, obj_types):
    """OR when or_types (disjunction: 'artifact or enchantment'); AND otherwise (conjunction:
    'artifact creature' requires BOTH)."""
    cts = sel["card_types"]
    if not cts:
        return True
    return any(ct in obj_types for ct in cts) if sel.get("or_types") else all(ct in obj_types for ct in cts)


def matches_card(sel: dict, face: dict) -> bool:
    t = _face_types(face)
    if not t["types"]:
        return False
    if sel.get("self"):
        return False                                       # self selectors project only source→source
    if sel["predicates"].get("token") and not sel["predicates"].get("nontoken"):
        return False                                       # a nontoken CARD cannot be a 'token' target
    if sel["predicates"].get("nonland") and "land" in t["types"]:
        return False                                       # 'nonland permanent' excludes lands
    if sel["card_types"]:
        if not _type_ok(sel, set(t["types"])):
            return False
    elif not sel["generic_permanent"] and not sel["subtypes"]:
        return False                                       # need SOME type/subtype constraint to match a card
    if sel["generic_permanent"] and not (set(t["types"]) & set(PERMANENT_TYPES)):
        return False
    if sel["subtypes"] and not (set(sel["subtypes"]) & set(t["subtypes"])):
        return False
    if sel.get("supertypes") and not (set(sel["supertypes"]) <= set(t["supertypes"])):
        return False                                       # supertypes are conjunctive (e.g. legendary)
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
    if sel["card_types"] and not _type_ok(sel, set(types)):
        return False
    if sel["generic_permanent"] and not (set(types) & set(PERMANENT_TYPES)):
        return False
    if sel["subtypes"] and not (set(sel["subtypes"]) & set(subs)):
        return False
    if sel.get("supertypes") and not (set(sel["supertypes"]) <= set(t.lower() for t in tl.get("supertypes", []))):
        return False
    if sel["predicates"].get("flying") and "flying" not in [k.lower() for k in (tok.get("keywords") or [])]:
        return False
    pg = sel["predicates"].get("power_ge")
    if pg is not None:
        pw = _power(tok)
        if pw is None or pw < pg:
            return False
    return True

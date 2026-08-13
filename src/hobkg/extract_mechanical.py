"""Exact syntactic extractions (spec Phase 1: "Exact syntactic extractions").

Conservative, high-precision regex over Oracle text. A primitive is emitted only
when the parse is unambiguous; a bare signal whose strict parse fails becomes an
UnresolvedExtraction queued for the Phase 3 LLM. We never guess a quantity or
object. This module does not build graph edges or expand mechanic templates.
"""

from __future__ import annotations

import re

from .models import (
    ConditionRecord,
    MechanicalExtraction,
    Provenance,
    UnresolvedExtraction,
)

_NUMWORDS = {
    "a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}


def _qty(word: str | None) -> int | None:
    if word is None:
        return None
    w = word.lower()
    if w.isdigit():
        return int(w)
    return _NUMWORDS.get(w)


# --- strict extraction patterns: (kind, regex, quantity_group_or_None) --------
_STRICT: list[tuple[str, re.Pattern, int | None]] = [
    ("draw", re.compile(r"\bdraws?\s+(a|one|two|three|four|five|\d+)\s+cards?\b", re.I), 1),
    ("discard", re.compile(r"\bdiscards?\s+(a|one|two|three|four|five|\d+)\s+cards?\b", re.I), 1),
    ("mill", re.compile(r"\bmills?\s+(a|one|two|three|four|five|\d+)\b(?:\s+cards?)?", re.I), 1),
    ("create_token", re.compile(r"\bcreates?\s+(a|an|one|two|three|four|five|\d+|X)\b[^.]{0,80}?\btokens?\b", re.I), 1),
    ("sacrifice", re.compile(r"\bsacrifices?\s+(a|an|this|that|those|your|one|two|three|\d+|X)\b[^.,;:()]{0,40}", re.I), None),
    ("add_mana", re.compile(r"\badds?\s+((?:\{[^}]+\})+)", re.I), None),
    ("add_mana", re.compile(r"\badds?\s+(one|two|three|\d+)\s+mana\b[^.]{0,30}", re.I), None),
    ("return_from_graveyard", re.compile(r"\breturns?\b[^.]{0,80}?\bfrom\b[^.]{0,40}?\bgraveyard\b[^.]{0,40}?\bto\b[^.]{0,30}?\b(battlefield|hand)\b", re.I), None),
    ("exile", re.compile(r"\bexiles?\s+(a|an|this|that|those|target|up to|all|each|\d+)\b[^.,;:()]{0,40}", re.I), None),
    ("trigger_etb", re.compile(r"\bwhen(?:ever)?\b[^.]{0,60}?\benters\b", re.I), None),
    ("trigger_dies", re.compile(r"\bwhen(?:ever)?\b[^.]{0,60}?\bdies\b", re.I), None),
    ("trigger_attacks", re.compile(r"\bwhen(?:ever)?\b[^.]{0,60}?\battacks\b", re.I), None),
    ("trigger_upkeep", re.compile(r"\bat the beginning of\b[^.]{0,40}?\bupkeep\b", re.I), None),
    ("trigger_end_step", re.compile(r"\bat the beginning of\b[^.]{0,40}?\bend step\b", re.I), None),
]

# put ... counter: needs the counter-type slot captured explicitly.
_RE_PUTCOUNTER = re.compile(
    r"\bputs?\s+(a|an|one|two|three|four|five|\d+|X)\s+([+\-0-9/A-Za-z]+)\s+counters?\b", re.I
)

# activated ability delimiter 'cost: effect' — validated to contain a real cost.
_RE_ACTIVATED = re.compile(r"(?m)^\s*(?P<cost>(?:\{[^}]+\}|[^:{}\n]){1,60}?):\s+(?P<effect>\S)")
_COST_WORDS = re.compile(r"(\{[^}]+\}|\bsacrifice\b|\bdiscard\b|\bpay\b|\bcrew\b|\bexert\b|\btap\b)", re.I)

# ambiguity roots: (signal, root regex, reason)
_ROOTS: list[tuple[str, re.Pattern, str]] = [
    ("draw", re.compile(r"\bdraws?\b(?!\s+step)", re.I), "non-literal or unparsed draw quantity"),
    ("discard", re.compile(r"\bdiscards?\b", re.I), "non-literal or unparsed discard object"),
    ("mill", re.compile(r"\bmills?\b", re.I), "non-literal or unparsed mill quantity"),
    ("create_token", re.compile(r"\bcreates?\b", re.I), "unparsed token specification"),
    ("add_mana", re.compile(r"\badds?\s+[^.]{0,20}?\bmana\b", re.I), "non-literal mana production"),
]

# qualifier flags
_QUALIFIERS: list[tuple[str, re.Pattern]] = [
    ("another", re.compile(r"\banother\b", re.I)),
    ("other", re.compile(r"\bother\b", re.I)),
    ("up_to", re.compile(r"\bup to\b", re.I)),
    ("may", re.compile(r"\bmay\b", re.I)),
    ("only_once_each_turn", re.compile(r"\bonly once each turn\b", re.I)),
]


def strip_reminders(text: str) -> str:
    """Blank out parenthetical reminder text, preserving character offsets.

    Reminder text has no rules meaning beyond the actual rules/keywords (CR 207.2).
    Extracting operations from it would misattribute token/keyword abilities to the
    producing card and duplicate the Phase 2 mechanic-template expansion, so the
    syntactic pass ignores it. Offsets are preserved (chars replaced with spaces)
    so provenance still indexes the original Oracle text.
    """
    out, depth = [], 0
    for ch in text:
        if ch == "(":
            depth += 1
            out.append(" ")
        elif ch == ")":
            if depth > 0:
                depth -= 1
            out.append(" ")
        else:
            out.append(" " if depth > 0 else ch)
    return "".join(out)


def _prov(card_id: str, face_id: str, m: re.Match) -> Provenance:
    return Provenance(
        card_id=card_id, face_id=face_id, source="scryfall.oracle_text",
        span=(m.start(), m.end()), text=m.group(0),
    )


def _qualifiers_in(text: str) -> list[str]:
    return [name for name, pat in _QUALIFIERS if pat.search(text)]


def _clause(text: str, pos: int) -> str:
    """The sentence/clause containing char offset `pos` (bounded by . ; newline).

    Qualifiers like 'another'/'up to' modify the effect within the same clause,
    not just the matched trigger/verb span, so we scan the whole clause.
    """
    b = max(text.rfind(".", 0, pos), text.rfind("\n", 0, pos), text.rfind(";", 0, pos))
    start = b + 1
    ends = [i for i in (text.find(".", pos), text.find("\n", pos), text.find(";", pos)) if i != -1]
    end = min(ends) if ends else len(text)
    return text[start:end]


def extract_face(face_id: str, card_id: str, oracle_text: str | None) -> tuple[
    list[MechanicalExtraction], list[UnresolvedExtraction], list[ConditionRecord]
]:
    extractions: list[MechanicalExtraction] = []
    unresolved: list[UnresolvedExtraction] = []
    conditions: list[ConditionRecord] = []
    if not oracle_text:
        return extractions, unresolved, conditions

    # Ignore parenthetical reminder text for the syntactic pass (see strip_reminders).
    text = strip_reminders(oracle_text)
    covered: dict[str, list[tuple[int, int]]] = {}

    def add(kind: str, m: re.Match, quantity: int | None = None, detail: dict | None = None):
        ex = MechanicalExtraction(
            id=f"ext:{face_id}:{kind}:{m.start()}",
            face_id=face_id, card_id=card_id, kind=kind,
            quantity=quantity, detail=detail or {},
            qualifiers=_qualifiers_in(_clause(text, m.start())),
            provenance=_prov(card_id, face_id, m),
        )
        extractions.append(ex)
        covered.setdefault(kind, []).append((m.start(), m.end()))

    for kind, pat, qgroup in _STRICT:
        for m in pat.finditer(text):
            q = _qty(m.group(qgroup)) if qgroup else None
            add(kind, m, quantity=q)

    for m in _RE_PUTCOUNTER.finditer(text):
        add("put_counter", m, quantity=_qty(m.group(1)), detail={"counter_type": m.group(2)})

    for m in _RE_ACTIVATED.finditer(text):
        cost = m.group("cost")
        if _COST_WORDS.search(cost):
            add("activated_ability", m, detail={"cost": cost.strip()})

    # ambiguity: signal roots not covered by any strict extraction of that kind
    for signal, root, reason in _ROOTS:
        spans = covered.get(signal, [])
        for m in root.finditer(text):
            pos = m.start()
            if any(s <= pos < e for s, e in spans):
                continue
            unresolved.append(
                UnresolvedExtraction(
                    id=f"unr:{face_id}:{signal}:{pos}",
                    face_id=face_id, card_id=card_id, signal=signal, reason=reason,
                    provenance=_prov(card_id, face_id, m),
                )
            )

    # deterministic condition/limit stubs
    for name, pat in (("only_once_each_turn", _QUALIFIERS[4][1]), ("up_to", _QUALIFIERS[2][1])):
        for m in pat.finditer(text):
            conditions.append(
                ConditionRecord(
                    condition_id=f"cond:{face_id}:{name}:{m.start()}",
                    face_id=face_id, card_id=card_id, kind=name,
                    human_readable=m.group(0),
                    provenance=_prov(card_id, face_id, m),
                )
            )

    return extractions, unresolved, conditions

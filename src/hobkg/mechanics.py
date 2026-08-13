"""Named-mechanic detection from Oracle text (spec Phase 1: "Keyword and
reminder-text handling").

We store Scryfall `keywords` verbatim (done in the pipeline) but do NOT assume
they are complete: HOB's new mechanics (Recruit, Storied, hone) live only in
Oracle text. This module detects the *presence* of named mechanics with
provenance. It deliberately does NOT expand them into rule templates — that is
Phase 2. No value judgments.
"""

from __future__ import annotations

import re

from .models import MechanicDetection, Provenance

# Mechanics that are frequently absent from Scryfall `keywords` and must be
# recovered from Oracle text. Patterns are conservative and case-sensitive where
# the mechanic is a capitalized keyword action/ability.
# Case-insensitive: in HOB the Recruit keyword action is written lowercase
# mid-sentence ("...enters, recruit.") and only capitalized where it begins a
# Saga chapter clause. Matching case-insensitively recovers all printings.
ORACLE_MECHANIC_LEXICON: dict[str, re.Pattern] = {
    "Recruit": re.compile(r"\brecruit\b", re.I),
    "Storied": re.compile(r"\bstoried\b", re.I),
    "Hone": re.compile(r"\bhone counter", re.I),
}


def detect_mechanics(face_id: str, card_id: str, oracle_text: str | None) -> list[MechanicDetection]:
    if not oracle_text:
        return []
    out: list[MechanicDetection] = []
    for mechanic, pat in ORACLE_MECHANIC_LEXICON.items():
        m = pat.search(oracle_text)
        if m:
            out.append(
                MechanicDetection(
                    face_id=face_id,
                    card_id=card_id,
                    mechanic=mechanic,
                    source="oracle_text",
                    provenance=Provenance(
                        card_id=card_id,
                        face_id=face_id,
                        source="scryfall.oracle_text",
                        span=(m.start(), m.end()),
                        text=m.group(0),
                    ),
                )
            )
    return out

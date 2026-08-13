"""Deterministic type-line parsing (spec Phase 1: "Type-line parsing").

Splits supertypes / card types / subtypes around the em-dash separator and
preserves the raw text. No inference beyond the controlled vocabularies.
"""

from __future__ import annotations

from .models import ParsedTypeLine

EM_DASH = "—"
SEP = f" {EM_DASH} "

KNOWN_SUPERTYPES = {"Basic", "Legendary", "Snow", "World", "Ongoing"}
KNOWN_TYPES = {
    "Artifact", "Battle", "Creature", "Enchantment", "Instant", "Kindred",
    "Land", "Planeswalker", "Sorcery", "Tribal",
}


def parse_type_line(text: str | None) -> ParsedTypeLine | None:
    """Parse a single face's type line (no ` // ` face separator expected).

    'Legendary Creature — Dwarf Scout' ->
        supertypes=['Legendary'], types=['Creature'], subtypes=['Dwarf','Scout']
    """
    if text is None:
        return None
    raw = text
    # A single face never contains the ' // ' card-face separator; guard anyway.
    if " // " in text:
        text = text.split(" // ", 1)[0]
    # Some token type lines are prefixed 'Token ' (e.g. 'Token Artifact — Treasure').
    left, _, right = text.partition(SEP)
    left_words = left.replace("Token ", "").split()
    supertypes = [w for w in left_words if w in KNOWN_SUPERTYPES]
    types = [w for w in left_words if w in KNOWN_TYPES]
    subtypes = right.split() if right else []
    return ParsedTypeLine(raw=raw, supertypes=supertypes, types=types, subtypes=subtypes)

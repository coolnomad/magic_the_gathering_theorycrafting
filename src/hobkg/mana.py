"""Deterministic mana parsing (spec Phase 1: "Mana parsing").

Parses mana symbols structurally and encodes payment capability as an explicit
rule. Critically (per the spec): colored mana pays its own pip + generic; a
colored pip is never satisfied by a different colored mana.
"""

from __future__ import annotations

import re

from .models import ManaCost, ManaSymbol

COLORS = ("W", "U", "B", "R", "G")
_SYMBOL_RE = re.compile(r"\{([^}]+)\}")


def classify_symbol(inner: str) -> ManaSymbol:
    """Classify one mana symbol given its inside-braces text (e.g. 'W', '2', 'W/U', '2/W', 'U/P', 'X', 'C')."""
    raw = "{" + inner + "}"
    s = inner.upper()

    if s.isdigit():
        return ManaSymbol(raw=raw, kind="generic", value=int(s))
    if s in {"X", "Y", "Z"}:
        return ManaSymbol(raw=raw, kind="variable")
    if s in COLORS:
        return ManaSymbol(raw=raw, kind="colored", colors=[s])
    if s == "C":
        return ManaSymbol(raw=raw, kind="colorless")
    if s == "S":
        return ManaSymbol(raw=raw, kind="snow")
    if s == "T":
        return ManaSymbol(raw=raw, kind="tap")
    if s == "Q":
        return ManaSymbol(raw=raw, kind="untap")
    if s == "E":
        return ManaSymbol(raw=raw, kind="energy")

    if "/" in s:
        parts = s.split("/")
        if "P" in parts:  # Phyrexian, e.g. W/P or 2/P
            cols = [p for p in parts if p in COLORS]
            return ManaSymbol(raw=raw, kind="phyrexian", colors=cols, phyrexian=True)
        if any(p.isdigit() for p in parts):  # monocolored hybrid, e.g. 2/W
            cols = [p for p in parts if p in COLORS]
            return ManaSymbol(raw=raw, kind="hybrid_mono", colors=cols)
        cols = [p for p in parts if p in COLORS]  # colored hybrid, e.g. W/U
        return ManaSymbol(raw=raw, kind="hybrid", colors=cols)

    return ManaSymbol(raw=raw, kind="other")


def parse_mana_cost(cost_string: str | None) -> ManaCost | None:
    """Parse a mana cost string into a structured ManaCost. Returns None for empty costs."""
    if not cost_string:
        return None
    symbols = [classify_symbol(m) for m in _SYMBOL_RE.findall(cost_string)]
    generic = sum(s.value or 0 for s in symbols if s.kind == "generic")
    pips: dict[str, int] = {}
    for s in symbols:
        if s.kind == "colored":
            pips[s.colors[0]] = pips.get(s.colors[0], 0) + 1
    has_variable = any(s.kind == "variable" for s in symbols)
    return ManaCost(
        raw=cost_string, symbols=symbols, generic=generic, pips=pips, has_variable=has_variable
    )


def payment_capabilities(produced_mana: list[str]) -> dict[str, list[str]]:
    """Map each produced mana letter to the payment demands it can satisfy.

    Colored mana -> its own colored pip and generic. Colorless -> {C} and generic.
    Never map a colored mana onto a *different* colored pip.
    """
    caps: dict[str, list[str]] = {}
    for m in produced_mana:
        m = m.upper()
        if m in COLORS:
            caps[m] = [f"pip:{m}", "generic"]
        elif m == "C":
            caps["C"] = ["pip:C", "generic"]
        else:
            caps[m] = ["generic"]
    return caps

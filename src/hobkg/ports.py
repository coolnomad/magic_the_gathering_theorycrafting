"""Layer 2: derive per-card port interface from reviewed extraction.

The deliverable is the derivation procedure. Port records are computed from
extraction data through declared mapping tables, not transcribed per card.

Usage:
    python -m hobkg.cli ports              # derive all pilot faces
    python -m hobkg.cli ports --face <id>  # derive specific face
    python -m hobkg.cli ports --validate   # validate outputs
"""

from __future__ import annotations

import json
import pathlib
import sys
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent


def read_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    """Read JSONL file, skip blank lines."""
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def write_jsonl(path: pathlib.Path, rows: list[dict[str, Any]]) -> None:
    """Write JSONL with sorted keys, LF endings."""
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")


def load_op_map(vocab_dir: pathlib.Path) -> dict[tuple[str, str], dict[str, Any]]:
    """Load effect verb -> port predicate mapping.

    Returns dict keyed by (verb, source_key), valued by full row.
    """
    rows = read_jsonl(vocab_dir / "op_map.jsonl")
    return {(r["verb"], r["source_key"]): r for r in rows}


def load_type_categories(vocab_dir: pathlib.Path) -> dict[str, list[dict[str, Any]]]:
    """Load type -> category mappings.

    Returns dict keyed by type name, valued by list of category rows.
    """
    rows = read_jsonl(vocab_dir / "type_categories.jsonl")
    result: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        result.setdefault(row["type"], []).append(row)
    return result


def load_concepts(vocab_dir: pathlib.Path) -> set[str]:
    """Load declared concept IDs."""
    rows = read_jsonl(vocab_dir / "concepts.jsonl")
    return {r["concept_id"] for r in rows}


def normalize_port_order(port: dict[str, Any]) -> dict[str, Any]:
    """Sort edge sections deterministically while preserving oracle order."""
    for section in ("properties", "installs", "consumes", "produces", "costs"):
        port[section] = sorted(
            port.get(section, []),
            key=lambda e: (
                e.get("oracle_span", [0, 0])[0],
                e.get("oracle_span", [0, 0])[1],
                e.get("predicate", ""),
                json.dumps(e, sort_keys=True, ensure_ascii=False),
            ),
        )
    modality = port.get("modality")
    if isinstance(modality, dict) and isinstance(modality.get("modes"), list):
        modes = sorted(
            modality["modes"],
            key=lambda m: (
                m.get("oracle_span", [0, 0])[0],
                m.get("oracle_span", [0, 0])[1],
                m.get("ability_id", ""),
                json.dumps(m, sort_keys=True, ensure_ascii=False),
            ),
        )
        for index, mode in enumerate(modes):
            mode["index"] = index
        modality["modes"] = modes
    return port


def span_overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    """Check if two character spans overlap."""
    return not (a[1] <= b[0] or b[1] <= a[0])


def join_by_span(
    census: list[dict[str, Any]], abilities: list[dict[str, Any]]
) -> dict[str, list[dict[str, Any]]]:
    """Join census clauses to abilities by oracle span overlap.

    Returns dict keyed by ability_id, valued by list of matching census rows.
    """
    result: dict[str, list[dict[str, Any]]] = {}
    for ab in abilities:
        ab_id = ab["ability_id"]
        result[ab_id] = []
        for span in ab.get("oracle_spans", []):
            if not isinstance(span, list) or len(span) != 2:
                continue
            ab_span = tuple(span)
            for census_row in census:
                cs = census_row.get("clause_span")
                if cs and isinstance(cs, list) and len(cs) == 2:
                    if span_overlap(ab_span, tuple(cs)):
                        result[ab_id].append(census_row)
    return result


def build_selector(effect: dict[str, Any]) -> dict[str, Any]:
    """Build selector from extraction effect entry."""
    selector: dict[str, Any] = {}

    # Controller
    ctrl = effect.get("controller")
    if ctrl:
        selector["controller"] = ctrl

    # Target count
    target_str = effect.get("target", "")
    if "up to two" in target_str or "up to 2" in target_str:
        selector.setdefault("target", {})["count"] = 2
        selector["target"]["optional"] = True
    elif "up to one" in target_str:
        selector.setdefault("target", {})["count"] = 1
        selector["target"]["optional"] = True
    elif "target" in target_str.lower():
        selector.setdefault("target", {})["count"] = 1

    # Restriction
    restrictions: list[dict[str, Any]] = []
    # "another" and " other " both mean the target excludes self (CR 109.2).
    # Space-guarded " other " avoids matching "mother", "otherwise", "other than".
    if "another" in target_str.lower() or " other " in target_str.lower():
        restrictions.append({"another": True})
    if "nonland" in target_str.lower():
        restrictions.append({"excludes_type": "Land"})
    if "token" in target_str.lower() and "artifact token" in target_str.lower():
        restrictions.append({"is_token": True})

    if restrictions:
        selector["restriction"] = restrictions

    return selector if selector else {}


# F5 gating: map a state-condition's "requirement" prose to a declared State
# concept id. Keep additions here rather than inline so the mapping is auditable
# and extendable per set.
STATE_REQUIREMENT_MAP: dict[str, str] = {
    "you have an enduring story": "state:enduring_story",
}


# Keyword-action verbs that appear as top-level *keys* in effect dicts
# (rather than as values on op/effect/action/type). Card 002.
KEYWORD_VERB_KEYS: tuple[str, ...] = ("amass",)


def load_token_specs(tokens_path: pathlib.Path) -> dict[str, dict[str, Any]]:
    """Load Scryfall token specs, indexed by lowercased token name.

    Card 002 (bucket 1): CREATES_TOKEN edges lift these into a `token`
    field so the graph carries the token's type_line / subtypes / power /
    toughness / colors / oracle_text, not just the token name.
    """
    if not tokens_path.exists():
        return {}
    raw = json.loads(tokens_path.read_text(encoding="utf-8"))
    out: dict[str, dict[str, Any]] = {}
    for tk in raw:
        name = (tk.get("name") or "").strip()
        if not name:
            continue
        spec = {
            "name": name,
            "type_line": tk.get("type_line"),
            "subtypes": [s for s in (tk.get("type_line", "") or "").split("—")[-1].split()
                          if s and s not in ("Token",)],
            "power": tk.get("power"),
            "toughness": tk.get("toughness"),
            "colors": tk.get("colors") or [],
            "oracle_text": tk.get("oracle_text") or "",
        }
        out[name.lower()] = spec
    return out


def derive_properties(
    face: dict[str, Any], type_categories: dict[str, list[dict[str, Any]]]
) -> list[dict[str, Any]]:
    """Derive IS_A edges from the type line.

    Walks all three sibling arrays on type_line -- supertypes (Legendary,
    Snow), types (Creature, Instant, Artifact ...), subtypes (Dwarf, Equipment,
    Saga, Adventure ...) -- and, for each primary type, appends the derived
    categorical concepts from type_categories (obj:category:permanent etc.).
    """
    edges: list[dict[str, Any]] = []
    type_line = face.get("type_line", {})
    if not type_line:
        return edges
    span = [0, len(face.get("oracle_text", ""))]

    # Supertypes (Legendary, Snow, ...)
    for st in type_line.get("supertypes", []) or []:
        edges.append({
            "predicate": "IS_A",
            "target": f"obj:supertype:{st.lower()}",
            "oracle_span": span,
            "note": "Printed supertype",
        })

    # Primary types plus their derived categories (permanent, spell, ...)
    for typ in type_line.get("types", []) or []:
        edges.append({
            "predicate": "IS_A",
            "target": f"obj:type:{typ.lower()}",
            "oracle_span": span,
            "note": "Printed type",
        })
        for cat_row in type_categories.get(typ, []):
            edges.append({
                "predicate": "IS_A",
                "target": cat_row["category"],
                "oracle_span": span,
                "note": f"Derived from {typ} ({cat_row['rule']})",
                "rule": cat_row["rule"],
            })

    # Subtypes (Dwarf, Equipment, Saga, Adventure, Bear, ...)
    for sub in type_line.get("subtypes", []) or []:
        edges.append({
            "predicate": "IS_A",
            "target": f"obj:subtype:{sub.lower()}",
            "oracle_span": span,
            "note": "Printed subtype",
        })

    # Baseline power/toughness. Present on every creature and vehicle (and
    # rarely on a few other permanents). Stored as strings on the face
    # because they may be non-numeric ("*", "X", "1+*") -- pass through
    # verbatim as the amount and coerce to int only when it parses cleanly.
    _power = face.get("power")
    _toughness = face.get("toughness")
    if _power is not None:
        try:
            _pv: int | str = int(str(_power))
        except (TypeError, ValueError):
            _pv = str(_power)
        edges.append({
            "predicate": "HAS_POWER",
            "target": "obj:power",
            "amount": _pv,
            "oracle_span": span,
            "note": "Printed power",
        })
    if _toughness is not None:
        try:
            _tv: int | str = int(str(_toughness))
        except (TypeError, ValueError):
            _tv = str(_toughness)
        edges.append({
            "predicate": "HAS_TOUGHNESS",
            "target": "obj:toughness",
            "amount": _tv,
            "oracle_span": span,
            "note": "Printed toughness",
        })

    return edges


def map_trigger_to_event(trigger: dict[str, Any]) -> str | None:
    """Map trigger dict to Event concept.

    Card 002: extended from the 001 pilot's 6-event map to cover the 89 distinct
    trigger phrases observed across all 210 faces. Ordering matters: more
    specific patterns must come before generic ones (e.g. saga-chapter before
    'lore counter', dwarf/equipment enters before 'this creature enters').
    """
    event = trigger.get("event", "")
    event_norm = event.replace(" ", "_").lower()
    event_lower = event.lower()

    # ---- Saga chapter (matches "lore counter reaches ...", "chapter") ----
    if "lore_count" in event_norm or "lore counter" in event_lower or event_norm == "chapter":
        return "event:saga-chapter"

    # ---- Phase / step triggers ----
    if "beginning_of_your_first_main_phase" in event_norm or "beginning of your first main phase" in event_lower:
        return "event:beginning-of-first-main-phase"
    if "beginning_of_your_upkeep" in event_norm or "beginning of your upkeep" in event_lower:
        return "event:beginning-of-your-upkeep"
    if event_norm == "upkeep" or "beginning of upkeep" in event_lower:
        return "event:beginning-of-upkeep"
    if "beginning_of_end_step" in event_norm or "beginning of end step" in event_lower:
        return "event:beginning-of-end-step"
    if "beginning_of_combat" in event_norm or "beginning of combat" in event_lower:
        return "event:beginning-of-combat"

    # ---- Attack triggers ----
    if ("total_power_12" in event_norm or "total power 12" in event_lower or
            ("attack_with_creatures" in event_norm and "power_12" in event_norm)):
        return "event:total-attack-power-12-or-greater"
    if event_norm == "you_attack" or event_lower.strip() == "you attack":
        return "event:you-attack"
    if event_norm == "this_creature_attacks" or "creature attacks" in event_lower:
        return "event:this-creature-attacks"
    # Bare "attacks" and subject-name self-references ("Dain attacks", "smaug_attacks")
    if event_norm == "attacks" or event_norm.endswith("_attacks") or event_lower.strip().endswith(" attacks"):
        return "event:this-creature-attacks"

    # ---- Combat damage ----
    if "equipped_creature_deals_combat_damage" in event_norm or "equipped creature deals combat damage" in event_lower:
        return "event:equipped-creature-deals-combat-damage-to-player"
    if ("deals_combat_damage_to_a_player" in event_norm or
            "deals combat damage to a player" in event_lower or
            "deals_combat_damage_to_player" in event_norm):
        return "event:this-creature-deals-combat-damage-to-player"

    # ---- Dies triggers ----
    if "one_or_more_other_creatures_die" in event_norm or "one or more other creatures die" in event_lower:
        return "event:one-or-more-other-creatures-die"
    if "nontoken_creature_you_control_dies" in event_norm or "nontoken creature you control dies" in event_lower:
        return "event:nontoken-creature-you-control-dies"
    if "another_creature_dies" in event_norm or "another creature dies" in event_lower:
        return "event:another-creature-dies"
    if ("this_artifact_is_put_into_a_graveyard" in event_norm or
            "artifact is put into a graveyard" in event_lower):
        return "event:this-artifact-dies"
    if event_norm in ("this_creature_dies", "creature_dies"):
        return "event:this-creature-dies"
    # Bare "dies" and subject-name self-references ("The Master of Lake-town dies")
    if event_norm == "dies" or event_norm.endswith("_dies") or event_lower.strip().endswith(" dies"):
        return "event:this-creature-dies"

    # ---- Enter-the-battlefield triggers (specific-subject variants first) ----
    # ---- Different-subject enter triggers (an X other than self) ----
    if ("another_dwarf_or_equipment" in event_norm) or (
        "dwarf you control enters" in event_lower
    ):
        return "event:another-dwarf-or-equipment-enters"
    # "a land you control enters" -- some other land, not this card.
    # A card that is ITSELF a land and self-refers "this land enters" is
    # handled below by the type-specific self-ETB branch.
    if (("land_enters" in event_norm or "land you control enters" in event_lower)
            and "this land" not in event_lower):
        return "event:land-enters-under-your-control"
    if (("artifact_you_control_enters" in event_norm
         or "artifact you control enters" in event_lower)
            and "this artifact" not in event_lower):
        return "event:artifact-enters-under-your-control"

    # ---- Text-first ETB classification (oracle wording is ground truth) ----
    #
    # The extractor sometimes over-normalises a plain "When <cardname>
    # enters" (Smaug, Bilbo) to event="this_creature_enters", inferring the
    # type from the card's type_line. That is wrong per the printed
    # wording: "When Smaug enters" fires whenever Smaug enters as any
    # permanent type, not only as a creature (relevant when other
    # effects change the card's types on entry).
    #
    # So when trigger.text names an "enters" clause, its wording wins.
    # If the text spells out a type word ("this creature enters", "this
    # enchantment enters", "as this enchantment enters"), use the narrow
    # event. If the text just says the card's name + "enters" (no type
    # word), use event:this-permanent-enters and short-circuit past the
    # event-normalized branches below.
    # Ground-truth signals from the extraction (oracle-derived, not
    # normalized): trigger.text (the raw clause), trigger.note (a comment
    # like "As this enchantment enters"), and trigger.subject (a subject
    # phrase the extractor split out, e.g. "this creature").
    _text_val = str(trigger.get("text") or "")
    _subject_val = str(trigger.get("subject") or "")
    _note_val = str(trigger.get("note") or "")
    _ground_hay = " ".join([_text_val, _subject_val, _note_val]).lower()
    if _ground_hay.strip() and (
        "enter" in _ground_hay or "battlefield" in _ground_hay
        or _subject_val.strip()  # subject alone is enough to classify
    ):
        for _tw in ("creature", "enchantment", "artifact", "aura",
                    "equipment", "land", "permanent"):
            if (f"this {_tw} enters" in _ground_hay
                    or f"as this {_tw} enters" in _ground_hay
                    or _subject_val.strip().lower() == f"this {_tw}"):
                return f"event:this-{_tw}-enters"
        # Ground-truth signals present but no type word -> broad self-ETB.
        # (E.g. "When Smaug enters" or "When Bilbo Baggins enters" -- only
        # the card name and "enters", so the trigger fires whenever the
        # card enters as any permanent type.)
        if "enter" in _ground_hay or "battlefield" in _ground_hay:
            return "event:this-permanent-enters"

    # ---- Enters-or-attacks (compound; creature-specific) ----
    if "enters_or_attacks" in event_norm or "enters or attacks" in event_lower:
        return "event:this-creature-enters-or-attacks"

    # ---- Self-ETB, type-specific ----
    #
    # A trigger like "When this enchantment enters" fires ONLY when the card
    # enters *as an enchantment*, not merely as any permanent. So each
    # printed subject type ("creature", "enchantment", "artifact", "aura",
    # "equipment", "land") gets its own narrower event concept. Consumers
    # gate on "any creature ETB" by looking for either
    # event:this-creature-enters (narrow, self must enter as a creature) or
    # event:this-permanent-enters (broad, self entering as any permanent)
    # AND properties.IS_A obj:type:creature.
    #
    # Also inspect trigger.note so replacement effects encoded as
    # {"event": "enters_the_battlefield", "note": "As this enchantment enters"}
    # (An Unexpected Party) get the correct type-specific event.
    _note_lower = str(trigger.get("note") or "").lower()
    _text_lower = str(trigger.get("text") or "").lower()
    _self_hay = " ".join([event_lower, _note_lower, _text_lower])
    _self_hay_norm = _self_hay.replace(" ", "_")
    _is_self_scoped_enter = (
        # explicit "this X enters" (any of the type words)
        any(x in _self_hay for x in (
            "this creature enters", "this enchantment enters",
            "this artifact enters", "this aura enters",
            "this equipment enters", "this land enters",
            "this permanent enters",
        ))
        or any(x in _self_hay_norm for x in (
            "this_creature_enters", "this_enchantment_enters",
            "this_artifact_enters", "this_aura_enters",
            "this_equipment_enters", "this_land_enters",
            "this_permanent_enters",
        ))
        # or "as this X enters" (replacement-effect phrasing)
        or any(x in _self_hay for x in (
            "as this creature enters", "as this enchantment enters",
            "as this artifact enters", "as this aura enters",
            "as this equipment enters", "as this land enters",
            "as this permanent enters",
        ))
    )

    def _self_etb_for(type_word: str) -> str:
        return f"event:this-{type_word}-enters"

    if _is_self_scoped_enter:
        for _tw in ("creature", "enchantment", "artifact", "aura",
                    "equipment", "land", "permanent"):
            if (f"this {_tw} enters" in _self_hay
                    or f"as this {_tw} enters" in _self_hay
                    or f"this_{_tw}_enters" in _self_hay_norm):
                return _self_etb_for(_tw)

    # Bare "creature enters" without "this" is treated as self-ETB narrower
    # to creature. Same for the other type words.
    for _tw in ("creature", "enchantment", "artifact", "aura",
                "equipment", "land"):
        if f"{_tw} enters" in event_lower or f"{_tw}_enters" == event_norm:
            return _self_etb_for(_tw)

    # ---- Self-ETB, generic (bare "enters", card-name self-reference,
    #      "enters_the_battlefield" with no type word) ----
    # No type word appeared anywhere -- the trigger fires whenever this
    # card enters as any permanent type. This is the broad ETB target.
    if event_norm in ("enters_the_battlefield", "enters"):
        return "event:this-permanent-enters"
    if (event_norm.endswith("_enters") or
            event_lower.strip().endswith("enters the battlefield") or
            event_lower.strip().endswith(" enters")):
        return "event:this-permanent-enters"

    # ---- Cast triggers ----
    if "you_cast_a_creature_spell" in event_norm or "you cast a creature spell" in event_lower:
        return "event:you-cast-creature-spell"
    if "you_cast_a_noncreature_spell" in event_norm or "you cast a noncreature spell" in event_lower:
        return "event:you-cast-noncreature-spell"
    if ("opponent_casts_spell" in event_norm or "opponent casts a spell" in event_lower or
            "an opponent casts a spell" in event_lower):
        return "event:opponent-casts-spell"
    if "cast" in event_lower and "spell" in event_lower:
        return "event:you-cast-spell"

    # ---- Draw / life / activate / target ----
    if ("you_draw_your_second_card" in event_norm or "you draw your second card" in event_lower or
            "draw_second_card" in event_norm):
        return "event:you-draw-second-card"
    if "you_draw_a_card" in event_norm or "you draw a card" in event_lower:
        return "event:you-draw-card"
    if "player_draws_card" in event_norm or "player draws" in event_lower:
        return "event:player-draws-card"
    if "player_loses_life" in event_norm or "player loses life" in event_lower:
        return "event:player-loses-life"
    if "activate" in event_lower and "creature" in event_lower:
        return "event:you-activate-creature-ability"
    if "becomes_the_target" in event_norm or "becomes the target" in event_lower:
        return "event:this-creature-becomes-target"

    # ---- Sacrifice / exile replacement ----
    if "you_sacrifice_a_token" in event_norm or "you sacrifice a token" in event_lower:
        return "event:you-sacrifice-token"
    if "you_sacrifice_a_creature_this_way" in event_norm or "you sacrifice a creature this way" in event_lower:
        return "event:you-sacrifice-creature-this-way"
    if "you_sacrifice_a_creature" in event_norm or "you sacrifice a creature" in event_lower:
        return "event:you-sacrifice-creature"
    if "you_exile_a_creature" in event_norm or "you exile a creature" in event_lower:
        return "event:you-exile-creature-replacement"

    # ---- Counters / equipment / graveyard-leave ----
    if "counters_placed" in event_norm or "counters placed" in event_lower:
        return "event:counters-placed"
    if ("equipment_become_attached" in event_norm or "equipment become attached" in event_lower or
            "equipment attached" in event_lower):
        return "event:equipment-attached-to-that-creature"
    if ("creature_card_leaves_your_graveyard" in event_norm or
            "creature card leaves your graveyard" in event_lower or
            "leaves your graveyard" in event_lower):
        return "event:creature-card-leaves-graveyard"

    return None


def derive_port(
    face: dict[str, Any],
    extraction: dict[str, Any] | None,
    census_by_ability: dict[str, list[dict[str, Any]]],
    op_map: dict[tuple[str, str], dict[str, Any]],
    type_categories: dict[str, list[dict[str, Any]]],
    declared_concepts: set[str],
    token_specs: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Derive port record for a single face."""
    face_id = face["id"]

    port: dict[str, Any] = {
        "face_id": face_id,
        "name": face["name"],
        "properties": derive_properties(face, type_categories),
        "installs": [],
        "consumes": [],
        "produces": [],
        "costs": [],
        "modality": None,
        "unresolved": [],
    }

    # Cast cost from the face's own mana_cost. Present on every non-land face
    # in the pilot. Costs section was empty on every non-Rampager/Stir face
    # before this lift -- layer 4 needs mana costs to compute deck capacity.
    mana_cost_raw = (face.get("mana_cost") or {}).get("raw")
    if mana_cost_raw:
        port["costs"].append({
            "predicate": "CONSUMES_MANA",
            "amount": mana_cost_raw,
            "class": "resource:mana",
            "purpose": "cast",
            "oracle_span": [0, 0],
        })

    if not extraction:
        # Vanilla creature or empty oracle
        return normalize_port_order(port)

    abilities = extraction.get("abilities", [])

    for ab in abilities:
        ab_id = ab.get("ability_id", "")
        # 'kind' from the extraction (static / triggered / activated / spell_effect /
        # replacement) is not currently branched on -- the disposition falls out of
        # the trigger, cost and effect shape. Kept out of the loop until we need it.

        # Card 002: lift ability-level costs into port.costs. The extraction
        # is schema-loose (costs may use `op:` or `type:` for the same idea)
        # and covers eight cost families across the set:
        #   mana:       {"op": "pay_mana", "amount": "{X}"} or {"type": "mana", "detail": "{X}"}
        #   sacrifice:  {"op": "sacrifice", ...} or {"type": "sacrifice", "detail": "..."}
        #   tap:        {"op": "tap"} or {"type": "tap"}
        #   life:       {"op": "pay_life", ...} or {"type": "life", "detail": "Pay N life"}
        #   discard:    {"op": "discard", ...} or {"type": "discard", ...}
        #   crew:       {"type": "crew", "value": N}
        #   restriction:{"op": "restriction", "detail": "..."}
        #   additional_cost: {"type": "additional_cost", "alternatives": [...]}
        # additional_cost is unpacked by the ADDITIONAL_COST branch in the
        # effect processor below (Stir Up Trouble); we skip it here.
        # Purpose is derived from ab.kind: spell_effect -> "cast" (an extra
        # cost to cast the spell); anything else -> "activation".
        _purpose = "cast" if ab.get("kind") == "spell_effect" else "activation"
        _ab_span = ab.get("oracle_spans", [[0, 0]])[0]

        def _mk(**fields):
            base = {"ability": ab_id, "purpose": _purpose, "oracle_span": _ab_span}
            base.update(fields)
            return base

        for _cost in ab.get("costs", []) or []:
            if not isinstance(_cost, dict):
                continue
            # The extraction uses two conflicting cost-field shapes:
            #   {"type": "mana", "cost": "{5}{G}{G}"}   -- `cost` holds the VALUE
            #   {"cost": "mana", "value": "{2}{W}"}      -- `cost` holds the OP name
            # Disambiguate: if `cost` looks like a mana-notation string
            # (starts with "{" or is a plain integer), treat it as the
            # value; otherwise treat it as an op/type name alongside
            # `op`/`type`.
            _cost_field = _cost.get("cost")
            _cost_is_mana_value = (
                isinstance(_cost_field, str)
                and (_cost_field.startswith("{") or _cost_field.isdigit())
            )
            _cop = _cost.get("op") or (
                _cost_field if not _cost_is_mana_value else None
            )
            _ctype = _cost.get("type") or (
                _cost_field if not _cost_is_mana_value else None
            )
            _detail = _cost.get("detail") or ""
            _detail_lower = str(_detail).lower()
            _camt = (
                _cost.get("amount")
                or _cost.get("value")
                or (_cost_field if _cost_is_mana_value else None)
                or _cost.get("symbol")
                or _cost.get("detail")
            )

            if _cop == "pay_mana" or _ctype == "mana":
                if _camt:
                    port["costs"].append(_mk(
                        predicate="CONSUMES_MANA",
                        amount=_camt,
                        **{"class": "resource:mana"},
                    ))

            elif _cop == "sacrifice" or _ctype == "sacrifice":
                # Classify subject of sacrifice from the detail clause. Card
                # 002: Allure of Power ("sacrifice a creature"), Laketown-in-
                # Peril ("Sacrifice this land"), Tom/Bert/William, etc.
                _classes: list[str] = []
                _subject = None
                if "this land" in _detail_lower or "this permanent" in _detail_lower or (
                    "sacrifice this" in _detail_lower and " creature" not in _detail_lower
                ):
                    _subject = "self"
                    _classes.append("obj:category:permanent")
                if "artifact" in _detail_lower and "obj:type:artifact" not in _classes:
                    _classes.append("obj:type:artifact")
                if "creature" in _detail_lower and "obj:type:creature" not in _classes:
                    _classes.append("obj:type:creature")
                if not _classes:
                    _classes.append("obj:category:permanent")
                for _cls in _classes:
                    _entry = _mk(
                        predicate="SACRIFICES",
                        selector={"controller": "you"},
                        **{"class": _cls},
                    )
                    if _subject == "self":
                        _entry["subject"] = "self"
                    port["costs"].append(_entry)

            elif _cop == "tap" or _ctype == "tap":
                port["costs"].append(_mk(
                    predicate="TAPS",
                    subject="self",
                    **{"class": "obj:category:permanent"},
                ))

            elif _cop == "pay_life" or _ctype == "life":
                import re as _re
                _m = _re.search(r"\d+", str(_camt) or "")
                _life = int(_m.group()) if _m else _camt
                port["costs"].append(_mk(
                    predicate="PAYS_LIFE",
                    amount=_life,
                    **{"class": "resource:life"},
                ))

            elif _cop == "discard" or _ctype == "discard":
                port["costs"].append(_mk(
                    predicate="DISCARDS",
                    **{"class": "obj:zone:hand"},
                ))

            elif _ctype == "crew":
                _n = _cost.get("value") or _cost.get("n") or _cost.get("amount")
                port["costs"].append(_mk(
                    predicate="CREW",
                    amount=_n,
                    **{"class": "resource:crew-power"},
                ))

            elif _cop == "restriction":
                port["costs"].append(_mk(
                    predicate="RESTRICTION",
                    detail=str(_detail),
                ))

            elif _ctype == "additional_cost":
                # Unpacked below by the ADDITIONAL_COST effect branch.
                continue

        # Map triggers.
        #
        # Two shapes share the same event vocabulary but emit different
        # edges:
        #   * kind == "triggered": a triggered ability that fires on the
        #     event. Emits consumes.TRIGGERS_ON.
        #   * kind == "replacement": a replacement effect that applies at
        #     the event's resolution (e.g. An Unexpected Party's "As this
        #     enchantment enters, choose a creature type"). It does not
        #     wait for the event to happen and produce a stack ability --
        #     it modifies HOW the event resolves. Emits
        #     installs.REPLACES_ON, so consumers can distinguish "reacts
        #     to the event" from "changes what the event does".
        trigger = ab.get("trigger")
        if trigger:
            # Bucket 4: a trigger may compress multiple events into one
            # clause. Split them into per-event edges so consumers can
            # query for either half:
            #   * "enters or attacks" (Bifur, Dwalin, Bard's Company) ->
            #     event:this-permanent-enters + event:this-creature-attacks
            #   * "Balin or another Dwarf enters" (Balin, Loremaster) ->
            #     event:this-permanent-enters + event:another-dwarf-or-equipment-enters
            _ev_text = " ".join([
                str(trigger.get("event") or ""),
                str(trigger.get("text") or ""),
                str(trigger.get("note") or ""),
            ]).lower()
            _event_ids: list[str] = []
            _primary = map_trigger_to_event(trigger)
            if _primary:
                _event_ids.append(_primary)
            # Compound: enters OR attacks
            if ("enters_or_attacks" in _ev_text.replace(" ", "_")
                    or "enters or attacks" in _ev_text):
                for _e in ("event:this-permanent-enters",
                           "event:this-creature-attacks"):
                    if _e not in _event_ids:
                        _event_ids.append(_e)
                # Drop the compound event id -- we have replaced it with
                # its two components.
                _event_ids = [e for e in _event_ids
                              if e != "event:this-creature-enters-or-attacks"]
            # Compound: self OR another X (e.g. "Balin or another Dwarf")
            elif " or another " in _ev_text:
                # Emit the broad self-enters trigger alongside whatever the
                # mapper produced for the "another X" half.
                _self_e = "event:this-permanent-enters"
                if _self_e not in _event_ids:
                    _event_ids.append(_self_e)

            for _eid in _event_ids:
                if _eid not in declared_concepts:
                    port["unresolved"].append({
                        "ability_id": ab_id,
                        "reason": f"Undeclared event concept: {_eid}",
                        "clause_text": trigger.get("text", str(trigger)),
                    })
                    continue
                if ab.get("kind") == "replacement":
                    port["installs"].append({
                        "predicate": "REPLACES_ON",
                        "target": _eid,
                        "oracle_span": ab.get("oracle_spans", [[0, 0]])[0],
                    })
                else:
                    _cons_entry: dict[str, Any] = {
                        "predicate": "TRIGGERS_ON",
                        "target": _eid,
                        "oracle_span": ab.get("oracle_spans", [[0, 0]])[0],
                    }
                    # Bucket 4b: lift trigger.condition / filter / subject
                    # onto the consumes edge so an event-gated trigger
                    # (Gleaming Splendor's "their second card each turn"
                    # on player-draws-card) doesn't lose its gate.
                    for _fld in ("condition", "filter", "subject",
                                  "controller", "timing", "frequency", "note"):
                        _fv = trigger.get(_fld)
                        if _fv is not None and _fld not in _cons_entry:
                            _cons_entry[_fld] = _fv
                    port["consumes"].append(_cons_entry)

        # Keyword abilities. When the keyword branch itself emits the semantic
        # action, record the verb so the effect loop below does not emit a
        # second, malformed edge for the same fact (F2 watcher.duplicate_install).
        # Card 002: also detect native keywords that the extraction schema-
        # laxly encodes inside an effect (kind=="static" with
        # {op:"keyword"} or {op:"grant_keyword"} and no target/subject).
        # These are native ("Trample" printed on the card), not grants of
        # a keyword to another creature -- Dori/Gollum/Smaug/etc. all have
        # this shape. Add both effect ops to consumed_verbs so the effect
        # loop below does not re-emit them as GRANTS.
        keyword = ab.get("keyword")
        native_keywords_from_effects: list[str] = []
        if not keyword and ab.get("kind") == "static":
            _tgt_keys = ("target", "targets", "subject", "affected",
                         "applies_to", "affects", "who", "scope")
            # Self-reference tokens: when the extraction's target IS the card
            # itself, the effect is still native ("this creature has trample"
            # == the card has trample). Bejeweled Warg encodes native Trample
            # as {"op":"grant_keyword","keyword":"trample","target":"this
            # creature"}; the "target" field is a self-ref, not a grant to
            # another permanent. Ori and Oin do the same with their own
            # card name in the target string.
            _face_name = (face.get("name") or "").lower()
            _face_first_word = _face_name.split(",")[0].split()[0] if _face_name else ""
            _self_target_strings = {"this creature", "this permanent",
                                     "this artifact", "this enchantment",
                                     "this land", "this card", "self", "~"}
            def _is_self_ref(v: object) -> bool:
                if not isinstance(v, str):
                    return False
                _vl = v.strip().lower()
                if _vl in _self_target_strings:
                    return True
                # Card-name self-reference: target equals the face's short
                # name or its first word (e.g. "Ori" for "Ori, Dwarven Miner").
                if _face_first_word and _vl == _face_first_word:
                    return True
                if _face_name and _vl == _face_name:
                    return True
                return False

            # Card 002: the extraction encodes native keywords in many
            # loose-schema shapes. Recognize all of them here:
            #   op:      keyword, keyword_ability, grant_keyword,
            #            grant_<specific-keyword> (e.g. grant_cast_permission
            #            for flash) when a keyword field is present
            #   effect:  grants_keyword, grant_keyword, keyword_ability, keyword
            #   type:    grant_keyword
            # Old Thrush, Bofur, Long-Bodied Grey Dog, Ori, Beorn, and 13 more
            # faces all encode a native keyword through one of these shapes.
            _KW_EFFECT_VALUES = {"grants_keyword", "grant_keyword",
                                  "keyword_ability", "keyword"}
            _KW_OP_VALUES = {"keyword", "keyword_ability", "grant_keyword"}
            _KW_TYPE_VALUES = {"grant_keyword"}

            def _is_keyword_effect(_eff: dict[str, Any]) -> bool:
                if _eff.get("op") in _KW_OP_VALUES:
                    return True
                if _eff.get("effect") in _KW_EFFECT_VALUES:
                    return True
                if _eff.get("type") in _KW_TYPE_VALUES:
                    return True
                # Fallback: op starts with "grant_" and there's a keyword
                # field naming the granted ability. Catches Bard's Company's
                # "grant_cast_permission" -> flash and any future
                # grant_hexproof / grant_unblockable / etc. shape.
                _op = _eff.get("op")
                if isinstance(_op, str) and _op.startswith("grant_") and (
                    isinstance(_eff.get("keyword"), str)
                    or (isinstance(_eff.get("keywords"), list) and _eff["keywords"])
                ):
                    return True
                return False

            for _eff in ab.get("effects", []) or []:
                if not isinstance(_eff, dict):
                    continue
                if not _is_keyword_effect(_eff):
                    continue
                # A target field present and non-self-referential means this
                # is a real grant (to equipped/enchanted creature, to each
                # creature you control, to a targeted permanent). Skip.
                _has_non_self_target = False
                for _k in _tgt_keys:
                    if _k not in _eff:
                        continue
                    if not _is_self_ref(_eff[_k]):
                        _has_non_self_target = True
                        break
                if _has_non_self_target:
                    continue
                # Read both the singular `keyword` and plural `keywords` slots;
                # some extraction shapes (Bard the Bowman, Woodland Weavemaster)
                # use the plural list even for a single keyword.
                _kws_here: list[str] = []
                _kw = _eff.get("keyword")
                if isinstance(_kw, str) and _kw:
                    _kws_here.append(_kw)
                _kw_list = _eff.get("keywords")
                if isinstance(_kw_list, list):
                    for _k in _kw_list:
                        if isinstance(_k, str) and _k:
                            _kws_here.append(_k)
                native_keywords_from_effects.extend(_kws_here)

        consumed_verbs: set[str] = set()
        _all_keywords_for_ab = ([keyword] if keyword else []) + native_keywords_from_effects
        for _kw in _all_keywords_for_ab:
            kw_lower = _kw.lower()
            kw_id = f"keyword:{kw_lower}"
            if kw_lower == "storied":
                port["installs"].append({
                    "predicate": "INSTALLS_WATCHER",
                    "target": "gate:storied",
                    "oracle_span": ab.get("oracle_spans", [[0, 0]])[0],
                    "note": "Storied keyword installs watcher",
                })
                consumed_verbs.add("storied")
            elif kw_id in declared_concepts:
                port["properties"].append({
                    "predicate": "HAS_KEYWORD",
                    "target": kw_id,
                    "oracle_span": ab.get("oracle_spans", [[0, 0]])[0],
                })
        # When native keywords came from effects, mark the wide set of
        # keyword-carrying verbs consumed so the effect loop below does not
        # re-emit these as GRANTS. The verb is whatever the op/effect/type
        # slot happened to hold; consuming a superset is safe because these
        # verbs only ever carry keyword semantics.
        if native_keywords_from_effects:
            for _v in ("keyword", "grant_keyword", "keyword_ability",
                        "grants_keyword", "grant_cast_permission",
                        "grant_hexproof", "grant_unblockable",
                        "grant_permission", "grant_ability"):
                consumed_verbs.add(_v)

        # Card 002: Storied detector for the extraction shapes that don't
        # promote "Storied" to ab.keyword or a keyword_ability op. Bifur is
        # the canonical case (already handled above); the other 7 storied
        # cards (Balin, Bombur, Dain, Fili, Kili, Oin, Thorin) encode the
        # Storied gain-designation ability through one of these shapes:
        #   {"op": "storied", ...}
        #   {"effect": "storied", "references_rule": "gate:storied", ...}
        #   {"op": "gain_designation", "designation": "enduring story", ...}
        #   {"effect": "gain_enduring_story_designation", ...}
        # In every case, the semantic is the same: the card has the Storied
        # keyword. Route them all to installs.INSTALLS_WATCHER gate:storied
        # (same as Bifur) and add the effect verbs to consumed_verbs so the
        # effect loop doesn't re-emit a GAINS_DESIGNATION or similar edge.
        _has_storied_watcher = any(
            e.get("predicate") == "INSTALLS_WATCHER"
            and e.get("target") == "gate:storied"
            and e.get("oracle_span") == ab.get("oracle_spans", [[0, 0]])[0]
            for e in port["installs"]
        )
        if not _has_storied_watcher:
            _storied_verbs_here: list[tuple[str, str]] = []
            for _eff in ab.get("effects", []) or []:
                if not isinstance(_eff, dict):
                    continue
                _op = _eff.get("op")
                _ev = _eff.get("effect")
                _des = str(_eff.get("designation") or "").lower()
                _refs = str(_eff.get("references_rule") or "").lower()
                _is_storied = False
                if _op == "storied" or _ev == "storied":
                    _is_storied = True
                elif _ev == "gain_enduring_story_designation":
                    _is_storied = True
                elif (_op == "gain_designation" or _ev == "gain_designation")                         and ("enduring story" in _des or "storied" in _des):
                    _is_storied = True
                elif _refs == "gate:storied":
                    _is_storied = True
                if _is_storied:
                    if _op:
                        _storied_verbs_here.append((_op, "op"))
                    if _ev:
                        _storied_verbs_here.append((_ev, "effect"))
            if _storied_verbs_here:
                port["installs"].append({
                    "predicate": "INSTALLS_WATCHER",
                    "target": "gate:storied",
                    "oracle_span": ab.get("oracle_spans", [[0, 0]])[0],
                    "note": "Storied keyword installs watcher",
                })
                for _v, _sk in _storied_verbs_here:
                    consumed_verbs.add(_v)

        # Process effects
        for effect in ab.get("effects", []):
            # Find verb. Standard source_keys hold the verb as a *value*
            # (e.g. {"op": "draw_cards"}). Card 002: some Magic keyword-actions
            # come through with the verb as a top-level *key* whose value is
            # the parameter block (e.g.
            # {"amass": {"army_subtype": "Goblins", "n": 2}}). Those are
            # treated as source_key == verb; op_map declares them the same way
            # ({"verb": "amass", "source_key": "amass"}).
            verb = None
            source_key = None
            for key in ["op", "effect", "action", "type"]:
                if key in effect:
                    verb = effect[key]
                    source_key = key
                    break

            if verb is None:
                for kw_key in KEYWORD_VERB_KEYS:
                    if kw_key in effect:
                        verb = kw_key
                        source_key = kw_key
                        break

            if not verb:
                port["unresolved"].append({
                    "ability_id": ab_id,
                    "reason": "No effect verb found",
                    "clause_text": json.dumps(effect, sort_keys=True),
                })
                continue

            # F2: if the keyword branch above already emitted the semantic edge
            # for this verb (e.g. "storied" -> INSTALLS_WATCHER gate:storied),
            # skip re-emitting it here as a targetless duplicate.
            if isinstance(verb, str) and verb.lower() in consumed_verbs:
                continue

            # Look up predicate. Coerce to str for the dict key -- verb comes
            # from json.loads (Any-typed) and source_key is str | None; we only
            # got here because verb is truthy, so it is a real string.
            if not isinstance(verb, str) or source_key is None:
                port["unresolved"].append({
                    "ability_id": ab_id,
                    "reason": f"Non-string verb {verb!r} on key {source_key!r}",
                    "clause_text": json.dumps(effect, sort_keys=True),
                })
                continue
            map_entry = op_map.get((verb, source_key))
            if not map_entry:
                port["unresolved"].append({
                    "ability_id": ab_id,
                    "reason": f"Unmapped verb: {verb} (key: {source_key})",
                    "clause_text": json.dumps(effect, sort_keys=True),
                })
                continue

            predicate = map_entry["predicate"]

            # Build port entry
            entry: dict[str, Any] = {
                "predicate": predicate,
                "oracle_span": ab.get("oracle_spans", [[0, 0]])[0],
            }

            # Card 002: name WHAT a REPLACES edge replaces. Every
            # replacement verb collapses to the REPLACES predicate; the
            # `replaces` field carries the affected event so consumers can
            # distinguish "replaces a draw" (Bard #1) from "replaces token
            # creation" (Bard #2) from "replaces going to graveyard"
            # (Bilbo, Thief in the Night, Head of the Hunt).
            if predicate == "REPLACES":
                _REPLACES_VERB_MAP = {
                    "replace_draw": "event:you-draw-card",
                    "replace_token_creation": "event:token-creation",
                    "replace_token_created": "event:token-creation",
                    "exile_instead_of_graveyard": "event:go-to-graveyard",
                }
                _r = _REPLACES_VERB_MAP.get(str(verb))
                if _r is None:
                    # Generic {"op": "replacement", ...}: infer from zone
                    # movement fields. Accept both from_zone/to_zone and
                    # the zone_from/zone_to spelling.
                    _fz = effect.get("from_zone") or effect.get("zone_from")
                    _tz = effect.get("to_zone") or effect.get("zone_to")
                    _note_l = str(
                        effect.get("note") or effect.get("detail") or ""
                    ).lower()
                    if _fz == "battlefield" and _tz == "exile":
                        _r = "event:go-to-graveyard"
                    elif _tz == "exile" and (_fz or "").lower() in (
                        "graveyard", "hand", "library"
                    ):
                        _r = f"event:{_fz}-to-exile"
                    elif _tz and _fz:
                        _r = f"event:{_fz}-to-{_tz}"
                    elif _tz == "exile" and (
                        "graveyard" in _note_l or "put into" in _note_l
                    ):
                        _r = "event:go-to-graveyard"
                if _r:
                    entry["replaces"] = _r

            # Add selector if applicable
            if "target" in effect or "affects" in effect:
                selector = build_selector(effect)
                if selector:
                    entry["selector"] = selector

            # Add amount/quantity if present
            if "amount" in effect:
                entry["amount"] = effect["amount"]
            if "quantity" in effect or "count" in effect:
                entry["quantity"] = effect.get("quantity", effect.get("count"))

            # Card 002 (bucket 2/3): lift descriptor fields the extraction
            # carries into port edges so downstream consumers see WHICH
            # thing was acted on and under WHAT condition. Every field
            # below has caused a "blank endpoint" or "missing gate" issue
            # on some card in the manual review.
            _counter_type = effect.get("counter_type") or effect.get("counter")
            if isinstance(_counter_type, str) and _counter_type:
                entry["counter_type"] = _counter_type
            _duration = effect.get("duration")
            if isinstance(_duration, str) and _duration:
                entry["duration"] = _duration
            _token_ref = (effect.get("token") or effect.get("token_ref")
                          or effect.get("token_type"))
            if isinstance(_token_ref, str) and _token_ref:
                entry["token_ref"] = _token_ref
            # Bucket 2: lift the subject (who is affected), adds_type
            # (Bear-addition on Beorn), detail (natural-language descriptor),
            # note (extractor annotation), text (raw clause), keyword_ability
            # (specific keyword being granted or gated), permission (for
            # "may cast" grants). Any of these fills a formerly blank
            # endpoint with the extraction's own descriptor.
            for _fld, _dst in (
                ("subject", "subject"),
                ("adds_type", "adds_type"),
                ("detail", "detail"),
                ("note", "note"),
                ("text", "text"),
                ("keyword_ability", "keyword_ability"),
                ("permission", "permission"),
                ("granted_text", "granted_text"),
                ("granted_ability", "granted_ability"),
                ("ability", "ability_text"),  # e.g. "ward {1}" from grant_ability
                ("restriction", "restriction"),
                ("scales_with", "scales_with"),
                ("scope", "scope"),
                ("controller", "controller"),
                ("filter", "filter"),
                ("mode", "mode"),
                ("value", "value"),
                ("x_definition", "x_definition"),
                ("state", "state"),
                ("multiplier", "multiplier"),
                # Mana-generation descriptors (Forest, Elvenking's Halls, ...)
                ("mana", "mana"),
                ("color", "color"),
                ("colors", "colors"),
                ("options", "options"),
                # Damage-distribution descriptor (Gandalf, Spark Starter)
                ("distribution", "distribution"),
                # Counter/replacement descriptors
                ("unless", "unless"),
                ("references_rule", "references_rule"),
                # Return/exile/search/zone descriptors
                ("to_zone", "to_zone"),
                ("from_zone", "from_zone"),
                ("under_control", "under_control"),
                ("enters_tapped", "enters_tapped"),
                ("searched_type", "searched_type"),
                # Modification descriptors
                ("modification", "modification"),
                ("power", "power_delta"),
                ("toughness", "toughness_delta"),
                ("delta", "delta"),
            ):
                if _fld in effect and _dst not in entry:
                    _v = effect[_fld]
                    if _v is None:
                        continue
                    entry[_dst] = _v

            # Lift the raw target string when the entry has no concept-id
            # target. Gone Fishing's "two target creatures and/or lands",
            # Gandalf's "each opponent", etc. -- keeps the endpoint from
            # rendering blank. class= (structural) and target_text=
            # (descriptor) can coexist.
            _raw_target = effect.get("target")
            if isinstance(_raw_target, str) and _raw_target and "target_text" not in entry:
                entry["target_text"] = _raw_target

            # Card 002: grant_unblockable / grant_cant_block / grant_hexproof
            # ops -> tag the GRANTS edge with the corresponding keyword
            # target so consumers see "grants unblockable" as a named
            # ability grant. "can't be blocked" isn't a formal MTG
            # keyword but the graph treats it as one for uniformity.
            _GRANT_OP_TO_KEYWORD = {
                "grant_unblockable": "keyword:cant-be-blocked",
                "grant_cant_be_blocked": "keyword:cant-be-blocked",
                "grant_cant_block": "keyword:cant-block",
                "grant_hexproof": "keyword:hexproof",
                "grant_shroud": "keyword:shroud",
                "grant_indestructible": "keyword:indestructible",
                "grant_lifelink": "keyword:lifelink",
                "grant_menace": "keyword:menace",
                "grant_trample": "keyword:trample",
                "grant_flying": "keyword:flying",
                "grant_reach": "keyword:reach",
                "grant_deathtouch": "keyword:deathtouch",
                "grant_vigilance": "keyword:vigilance",
                "grant_haste": "keyword:haste",
                "grant_first_strike": "keyword:first strike",
                "grant_double_strike": "keyword:double strike",
                "grant_flash": "keyword:flash",
            }
            if predicate == "GRANTS" and "target" not in entry:
                _grant_kw = _GRANT_OP_TO_KEYWORD.get(str(verb))
                if _grant_kw and _grant_kw in declared_concepts:
                    entry["target"] = _grant_kw
                # Note-based inference: "can't be blocked" -> keyword:cant-be-blocked
                if "target" not in entry:
                    _note_src = (
                        str(entry.get("note") or "")
                        + " " + str(entry.get("detail") or "")
                        + " " + str(entry.get("text") or "")
                    ).lower()
                    if "can\'t be blocked" in _note_src or "can't be blocked" in _note_src or "cannot be blocked" in _note_src:
                        entry["target"] = "keyword:cant-be-blocked"
                    elif "can\'t block" in _note_src or "can't block" in _note_src:
                        entry["target"] = "keyword:cant-block"
                # Fallback: op == grant_ability with ability_text like
                # "ward {1}" -- parse the leading word as the keyword
                # and stash the amount when it's a mana cost. Thorin
                # Oakenshield's ward {1} and Dwarven Mattock's ward {1}
                # both land here.
                if "target" not in entry:
                    _abt = entry.get("ability_text")
                    if isinstance(_abt, str) and _abt:
                        import re as _re_ab
                        _first_word_m = _re_ab.match(r"\s*([a-zA-Z][a-zA-Z-]+)", _abt)
                        if _first_word_m:
                            _first_word = _first_word_m.group(1).lower()
                            _try_ids = [f"keyword:{_first_word}"]
                            for _cw in ("double strike", "first strike"):
                                if _abt.lower().startswith(_cw):
                                    _try_ids.insert(0, f"keyword:{_cw}")
                            for _kw_id in _try_ids:
                                if _kw_id in declared_concepts:
                                    entry["target"] = _kw_id
                                    # Parse a trailing {N} mana cost as amount
                                    _amt_m = _re_ab.search(r"\{[^}]+\}", _abt)
                                    if _amt_m and "amount" not in entry:
                                        entry["amount"] = _amt_m.group(0)
                                    break

            # Card 002: normalize MODIFIES_PT amount. The extraction uses
            # several field names for the P/T change:
            #   amount:         "+2/+2"  (Dwarven Mattock)
            #   delta:          "+1/+1"  (Wargling, Eagle's Rescue, Bard's Company)
            #   value:          "+1/+1"  (Most Decrepit Old Bird)
            #   power/toughness: numeric split (Crude Bent Blade "+2/+1"
            #                    from power=2 toughness=1 -- lifted above
            #                    as power_delta / toughness_delta)
            # Synthesize a single canonical `amount` string so every
            # MODIFIES_PT edge is comparable across cards.
            if predicate == "MODIFIES_PT" and "amount" not in entry:
                _pt_amt = (entry.get("delta") or entry.get("value")
                           or effect.get("modification"))
                if not _pt_amt:
                    _pd = entry.get("power_delta")
                    _td = entry.get("toughness_delta")
                    if _pd is not None and _td is not None:
                        def _fmt(v: object) -> str:
                            s = str(v)
                            if not s.startswith(("+", "-")):
                                try:
                                    return f"{int(s):+d}"
                                except (TypeError, ValueError):
                                    return s
                            return s
                        _pt_amt = f"{_fmt(_pd)}/{_fmt(_td)}"
                if not _pt_amt:
                    # Final fallback: parse a P/T pattern out of the raw
                    # text or detail. Desert Were-Worm's "+2/+0 for each
                    # Mountain you control" lands via this path; scales
                    # remain expressed in `text` / `scales_with`.
                    import re as _re
                    _src = str(entry.get("text") or entry.get("detail") or "")
                    _m = _re.search(r"([+-]\d+)/([+-]\d+)", _src)
                    if _m:
                        _pt_amt = f"{_m.group(1)}/{_m.group(2)}"
                if _pt_amt:
                    entry["amount"] = _pt_amt

            # Bucket 3: effect-level `condition` (singular). Merge into a
            # `conditions` list on the entry so gating info from the
            # effect itself (not just ability-level ab.conditions) is
            # preserved. Beorn's conditional_draw is the pilot case.
            _eff_cond = effect.get("condition")
            if _eff_cond is not None:
                _existing = entry.get("conditions") or []
                if not isinstance(_existing, list):
                    _existing = [_existing]
                _existing = list(_existing)
                _existing.append(_eff_cond)
                entry["conditions"] = _existing

            # Bucket 1: resolve the token reference against Scryfall token
            # specs and attach the full token block. At the Door's "X 2/2
            # red Dwarf tokens", Bejeweled Warg's Treasure, Chief Warg's
            # Company's 2/2 Wolf all get their P/T, subtypes, colors, and
            # oracle text attached rather than just a bare token_ref.
            if (predicate in ("CREATES_TOKEN", "GIFTS", "CREATES_OBJECT")
                    and token_specs):
                # The raw token field can hold either the token id string
                # ("token:wolf"), the token name ("Treasure"), a slug with
                # dashes ("token:bird-soldier" -> "Bird Soldier"), a
                # descriptive phrase ("2/2 red Dwarf creature token"), or
                # a copy phrase ("copies of The Notary Hobbits" -> Copy).
                _lookup_keys: list[str] = []
                for _fld in ("token_ref", "token", "gift_object", "token_type",
                              "creates", "spawn"):
                    _v = effect.get(_fld)
                    if not isinstance(_v, str) or not _v:
                        continue
                    # strip a "token:" prefix if present
                    _stripped = _v[6:] if _v.startswith("token:") else _v
                    _s_lower = _stripped.lower()
                    _lookup_keys.append(_s_lower)
                    # dashes-to-spaces: "bird-soldier" -> "bird soldier"
                    if "-" in _s_lower:
                        _lookup_keys.append(_s_lower.replace("-", " "))
                    # last non-generic word in a descriptive phrase
                    _tail = [w for w in _stripped.split()
                             if w.lower() not in ("token", "creature", "artifact",
                                                    "enchantment", "colorless",
                                                    "white", "blue", "black",
                                                    "red", "green")]
                    if _tail:
                        _lookup_keys.append(_tail[-1].lower())
                    # "copies of X" phrase -> Copy token
                    if "cop" in _s_lower and " of " in _s_lower:
                        _lookup_keys.append("copy")
                for _key in _lookup_keys:
                    if _key in token_specs:
                        entry["token"] = token_specs[_key]
                        break

            # Add target class if present
            target = effect.get("target", "")
            if "creature" in target.lower():
                entry["class"] = "obj:type:creature"
            elif "artifact" in target.lower():
                entry["class"] = "obj:type:artifact"

            # Add conditions
            conditions = ab.get("conditions", [])
            if conditions:
                entry["conditions"] = conditions
                # F5: promote state-typed conditions to a machine-readable
                # gated_on: state:<id>. Lets layer 4 see that Bifur's a3
                # duplicate_trigger fires only when state:enduring_story is on.
                _state_gates = []
                for _c in conditions:
                    if isinstance(_c, dict) and _c.get("type") == "state":
                        _req = (_c.get("requirement") or "").strip().lower()
                        _sid = STATE_REQUIREMENT_MAP.get(_req)
                        if _sid and _sid in declared_concepts:
                            _state_gates.append(_sid)
                if _state_gates:
                    entry["gated_on"] = (
                        _state_gates[0] if len(_state_gates) == 1 else _state_gates
                    )

            # F6: for an ADDITIONAL_COST effect, unpack the ability's
            # costs.alternatives array into a `branches` field on the entry.
            # Stir Up Trouble's "sacrifice X or pay {4}" becomes two typed
            # branches with a `choose: 1` marker rather than an opaque node id.
            # Card 002: for a MODAL_MARKER, unpack `options` (each option is
            # itself a mini-effect dict) into a `branches` field on the
            # entry, so consumers see WHAT each mode does rather than an
            # opaque marker. Bejeweled Warg's "choose one -- +1/+1 counter
            # on target Wolf OR create a Treasure token" becomes two
            # branch entries with their own predicate, target, and any
            # descriptor fields the sub-effect carries. Sub-effects go
            # through the same op_map lookup so the branch predicates match
            # what the top-level loop would have emitted.
            if predicate == "MODAL_MARKER":
                _options = effect.get("options") or []
                _mode_branches: list[dict[str, Any]] = []
                for _opt in _options:
                    if not isinstance(_opt, dict):
                        continue
                    _sub_verb = None
                    _sub_key = None
                    for _k in ("op", "effect", "action", "type"):
                        if _k in _opt:
                            _sub_verb = _opt[_k]
                            _sub_key = _k
                            break
                    if _sub_verb is None:
                        for _kw_k in KEYWORD_VERB_KEYS:
                            if _kw_k in _opt:
                                _sub_verb = _kw_k
                                _sub_key = _kw_k
                                break
                    _sub_map = None
                    if isinstance(_sub_verb, str) and _sub_key:
                        _sub_map = op_map.get((_sub_verb, _sub_key))
                    _branch: dict[str, Any] = {
                        "predicate": _sub_map["predicate"] if _sub_map else "OPTION",
                    }
                    # Lift the same descriptor fields onto the branch.
                    for _fld in ("amount", "quantity", "count", "counter_type",
                                  "counter", "duration", "token", "token_ref",
                                  "gift_object", "subject", "adds_type",
                                  "detail", "note", "text", "target",
                                  "keyword_ability", "granted_text",
                                  "permission", "restriction", "condition"):
                        if _fld in _opt and _opt[_fld] is not None:
                            _dst = "counter_type" if _fld == "counter" else _fld
                            _branch[_dst] = _opt[_fld]
                    # Resolve token spec if this branch creates one.
                    if (_branch["predicate"] in ("CREATES_TOKEN", "GIFTS",
                                                  "CREATES_OBJECT")
                            and token_specs):
                        _keys: list[str] = []
                        for _fld2 in ("token_ref", "token", "gift_object"):
                            _v2 = _opt.get(_fld2)
                            if not isinstance(_v2, str) or not _v2:
                                continue
                            _stripped = _v2[6:] if _v2.startswith("token:") else _v2
                            _keys.append(_stripped.lower())
                            _tail = [w for w in _stripped.split()
                                     if w.lower() not in ("token", "creature",
                                                            "artifact", "enchantment",
                                                            "colorless", "white",
                                                            "blue", "black",
                                                            "red", "green")]
                            if _tail:
                                _keys.append(_tail[-1].lower())
                        for _k2 in _keys:
                            if _k2 in token_specs:
                                _branch["token"] = token_specs[_k2]
                                break
                    _mode_branches.append(_branch)
                if _mode_branches:
                    entry["branches"] = _mode_branches
                    entry["choose"] = 1 if effect.get("mode") == "one" else effect.get("mode")

            if predicate == "ADDITIONAL_COST":
                _branches: list[dict[str, Any]] = []
                for _cost in ab.get("costs", []) or []:
                    if not isinstance(_cost, dict):
                        continue
                    if _cost.get("type") != "additional_cost":
                        continue
                    for _alt in _cost.get("alternatives", []) or []:
                        if not isinstance(_alt, dict):
                            continue
                        _atype = _alt.get("type")
                        if _atype == "sacrifice":
                            _det = (_alt.get("detail") or "").lower()
                            _classes = []
                            if "artifact" in _det:
                                _classes.append("obj:type:artifact")
                            if "creature" in _det:
                                _classes.append("obj:type:creature")
                            if not _classes:
                                _classes.append("obj:category:permanent")
                            for _cls in _classes:
                                _branches.append({
                                    "predicate": "SACRIFICES",
                                    "class": _cls,
                                    "selector": {"controller": "you"},
                                })
                        elif _atype == "mana":
                            _amt = _alt.get("amount")
                            if _amt:
                                _branches.append({
                                    "predicate": "CONSUMES_MANA",
                                    "amount": _amt,
                                    "class": "resource:mana",
                                })
                if _branches:
                    entry["branches"] = _branches
                    entry["choose"] = 1

            # Card 002: canonicalize amount/quantity for predicates where
            # both fields mean the same count. If one is present and the
            # other isn't, mirror. Applies to DRAWS, ADDS_COUNTER,
            # CREATES_TOKEN, PRODUCES_MANA, DEALS_DAMAGE, DISCARDS.
            _MIRROR_PREDS = (
                "DRAWS", "ADDS_COUNTER", "CREATES_TOKEN",
                "PRODUCES_MANA", "DEALS_DAMAGE", "DISCARDS",
            )
            if predicate in _MIRROR_PREDS:
                _amt = entry.get("amount")
                _qty = entry.get("quantity")
                if _amt is not None and _qty is None:
                    entry["quantity"] = _amt
                elif _qty is not None and _amt is None:
                    entry["amount"] = _qty
                # PRODUCES_MANA default: if mana is set but neither amount
                # nor quantity, assume single-unit ("Add {R}." = amount 1).
                if (predicate == "PRODUCES_MANA"
                        and entry.get("amount") is None
                        and entry.get("mana")):
                    entry["amount"] = 1
                    entry["quantity"] = 1
                # CREATES_TOKEN default: if a token is resolved but
                # quantity is None, assume "a token" -> 1.
                if (predicate == "CREATES_TOKEN"
                        and entry.get("token") is not None
                        and entry.get("quantity") is None):
                    entry["quantity"] = 1
                    if entry.get("amount") is None:
                        entry["amount"] = 1
                # DRAWS / DEALS_DAMAGE default: parse "X" from text as
                # a symbolic amount so Balin, Loremaster's "X damage /
                # Draw X cards" edges carry an amount rather than being
                # empty.
                if (predicate in ("DRAWS", "DEALS_DAMAGE")
                        and entry.get("amount") is None
                        and entry.get("quantity") is None):
                    _txt = str(entry.get("text") or entry.get("detail")
                                or entry.get("note") or "")
                    if _txt:
                        import re as _re_x
                        if _re_x.search(r"\bX\b", _txt):
                            entry["amount"] = "X"
                            entry["quantity"] = "X"

            # Card 002: MODAL_MARKER with no `options` list from
            # verb == "choose" is a parameter selection ("Choose a
            # creature type" on Orcrist, followed by a create_token
            # effect scaled to that type), not a mode choice. Skip
            # emitting a bare marker in that case; the subsequent
            # effects carry the selection via target_text /
            # scales_with / detail. Real modal ops (choose_mode,
            # modal) keep their MODAL_MARKER even when the extraction
            # didn't inline options -- for Gnashing of Teeth and
            # Reverent Howl the modes live in separate abilities.
            if predicate == "MODAL_MARKER" and not entry.get("branches"):
                if str(verb) == "choose":
                    continue

            # Categorize by predicate. CONSUMES_MANA / ADDITIONAL_COST from
            # the effect loop belong in costs. SACRIFICES from the effect
            # loop is a sacrifice-as-effect ("You may sacrifice another
            # creature. If you do, ...") -- distinct from sacrifice-as-cost
            # which comes through the ability-level cost lift and appends
            # directly to port["costs"] with purpose set. Route it to
            # produces here.
            if predicate in ("CONSUMES_MANA", "ADDITIONAL_COST"):
                port["costs"].append(entry)
            elif predicate == "INSTALLS_WATCHER":
                port["installs"].append(entry)
            elif predicate == "GRANTS":
                # F3: every GRANTS edge names the specific keyword(s). The
                # extraction uses either `keyword` (single string) or `keywords`
                # (plural array); Concerted Care uses the plural form to grant
                # both hexproof and indestructible in one clause.
                _kws = effect.get("keywords")
                if _kws is None:
                    _kw = effect.get("keyword")
                    _kws = [_kw] if _kw else []
                if _kws:
                    for _kw in _kws:
                        _target = f"keyword:{str(_kw).lower()}"
                        _e = dict(entry)
                        _e["target"] = _target
                        port["produces"].append(_e)
                else:
                    port["produces"].append(entry)
            else:
                port["produces"].append(entry)

    # F4: detect modality when the extraction did not emit it. Signal: two or
    # more spell_effect abilities on the same face share a leading oracle span
    # (the "Choose one" / "Choose one or both" preamble). Read that shared
    # span from the face's oracle text to name the modality kind, and each
    # ability becomes a mode.
    if port["modality"] is None and abilities and len(abilities) >= 2:
        _kinds = {a.get("kind") for a in abilities}
        if _kinds == {"spell_effect"}:
            _first_spans = [
                tuple((a.get("oracle_spans") or [[0, 0]])[0]) for a in abilities
            ]
            if all(s == _first_spans[0] and s != (0, 0) for s in _first_spans):
                _preamble = _first_spans[0]
                _oracle = face.get("oracle_text", "")
                _ptxt = _oracle[_preamble[0]:_preamble[1]].strip().lower()
                _kind = None
                if "choose one or both" in _ptxt:
                    _kind = "choose_one_or_both"
                elif "choose two" in _ptxt:
                    _kind = "choose_two"
                elif "choose one" in _ptxt:
                    _kind = "choose_one"
                if _kind:
                    _modes = []
                    for _i, _a in enumerate(abilities):
                        _spans = _a.get("oracle_spans") or [[0, 0]]
                        _mode_span = _spans[1] if len(_spans) > 1 else _spans[0]
                        _modes.append({
                            "index": _i,
                            "ability_id": _a.get("ability_id"),
                            "oracle_span": list(_mode_span),
                        })
                    port["modality"] = {
                        "kind": _kind,
                        "preamble_span": list(_preamble),
                        "modes": _modes,
                    }

    # Card 002: parse token-creation text out of grant_ability effects.
    # Some abilities grant a triggered ability whose payload creates a
    # token (Down in the Valley's Saga chapter II: gains "Landfall —
    # Whenever a land you control enters, create a 1/1 green Elf
    # creature token."). The extraction stores that whole granted ability
    # as a free-form `granted` string, so the token creation never lands
    # as a CREATES_TOKEN edge. Sweep those strings and lift a
    # CREATES_TOKEN edge with the resolved token spec so the graph
    # captures what the granted ability produces.
    if extraction is not None and token_specs:
        import re as _re2
        _existing_token_names = {
            (e.get("token") or {}).get("name")
            for e in port.get("produces", [])
            if e.get("predicate") == "CREATES_TOKEN"
        }
        for _ab in extraction.get("abilities", []) or []:
            _ab_span = _ab.get("oracle_spans", [[0, 0]])[0]
            for _eff in _ab.get("effects", []) or []:
                if not isinstance(_eff, dict):
                    continue
                _op = _eff.get("op") or _eff.get("effect") or _eff.get("type")
                if not (isinstance(_op, str) and _op.startswith("grant_")):
                    continue
                _granted = str(_eff.get("granted") or _eff.get("granted_text")
                                or _eff.get("granted_ability") or "")
                if not _granted:
                    continue
                # Look for "create ... N/N ... <color> <SubType> ... token"
                # Match any known token name.
                _lower = _granted.lower()
                if "token" not in _lower or "create" not in _lower:
                    continue
                for _tk_name, _spec in token_specs.items():
                    if _tk_name in _lower and _spec.get("name") not in _existing_token_names:
                        port["produces"].append({
                            "predicate": "CREATES_TOKEN",
                            "token": _spec,
                            "quantity": 1,
                            "amount": 1,
                            "oracle_span": _ab_span,
                            "note": f"token creation embedded in granted ability text",
                            "conditions": [{
                                "condition": "granted ability trigger fires",
                                "type": "grant_dependent",
                            }],
                        })
                        _existing_token_names.add(_spec.get("name"))
                        break

    # Card 002: face-level keyword-involvement sweep. Any effect field
    # that names a keyword ability -- ab.keyword, effect.keyword,
    # effect.keywords (plural), effect.ability, effect.granted_ability
    # -- surfaces the keyword on properties.HAS_KEYWORD so consumers
    # looking for "cards that touch <keyword>" find every card that
    # grants, temporarily gives, or otherwise references it. Native
    # keywords are already emitted through the ab.keyword branch;
    # granted-only cases (Goblin Plate Mail's menace on equipped
    # creature, Dwarven Mattock's ward, Bard the Bowman's temporary
    # lifelink) are picked up here.
    if extraction is not None:
        _existing_kw_props = {
            e.get("target") for e in port["properties"]
            if e.get("predicate") == "HAS_KEYWORD"
        }
        import re as _re4
        def _yield_keywords(_obj):
            if isinstance(_obj, str):
                # ability_text like "ward {1}" -> pull leading word
                _m = _re4.match(r"\s*([a-zA-Z][a-zA-Z-]+)", _obj)
                if _m:
                    yield _m.group(1)
                return
            if not isinstance(_obj, list):
                return
            for _v in _obj:
                if isinstance(_v, str):
                    yield _v
        for _ab in extraction.get("abilities", []) or []:
            _ab_span = _ab.get("oracle_spans", [[0, 0]])[0]
            for _eff in _ab.get("effects", []) or []:
                if not isinstance(_eff, dict):
                    continue
                _cand: list[str] = []
                for _k in ("keyword", "keywords", "ability",
                            "granted_ability", "granted_text",
                            "keyword_ability"):
                    _v = _eff.get(_k)
                    if isinstance(_v, str):
                        _cand.append(_v)
                    elif isinstance(_v, list):
                        for _x in _v:
                            if isinstance(_x, str):
                                _cand.append(_x)
                # Known compound keyword names: prefer full match over
                # first-word truncation. "Double strike" and "First strike"
                # would otherwise land as keyword:double / keyword:first.
                _COMPOUND_KWS = (
                    "double strike", "first strike", "long strike",
                    "banding with other", "banding",
                )
                for _c in _cand:
                    _c_norm = _c.strip().lower().rstrip(",;.:")
                    if not _c_norm:
                        continue
                    _kw_target = None
                    # Try compound match at the start of the phrase.
                    for _comp in _COMPOUND_KWS:
                        if _c_norm.startswith(_comp):
                            _kw_target = f"keyword:{_comp}"
                            break
                    if _kw_target is None:
                        _first = _c_norm.split()[0]
                        _kw_target = f"keyword:{_first}"
                    if _kw_target in _existing_kw_props:
                        continue
                    if _kw_target in declared_concepts:
                        port["properties"].append({
                            "predicate": "HAS_KEYWORD",
                            "target": _kw_target,
                            "oracle_span": _ab_span,
                            "note": f"{_kw_target.split(':',1)[1].capitalize()} keyword (referenced via ability text)",
                        })
                        _existing_kw_props.add(_kw_target)

    # Also sweep the port's own produces list: any GRANTS edge whose
    # target is a keyword:X concept implies the card involves that
    # keyword, so surface it on properties.HAS_KEYWORD too. Catches
    # cases where the involvement came from op -> keyword mapping
    # (grant_unblockable -> keyword:cant-be-blocked) rather than an
    # explicit keyword field on the effect.
    _existing_kw_props2 = {
        e.get("target") for e in port["properties"]
        if e.get("predicate") == "HAS_KEYWORD"
    }
    for _pe in list(port["produces"]):
        if _pe.get("predicate") != "GRANTS":
            continue
        _t = _pe.get("target")
        if isinstance(_t, str) and _t.startswith("keyword:") and _t not in _existing_kw_props2:
            if _t in declared_concepts:
                port["properties"].append({
                    "predicate": "HAS_KEYWORD",
                    "target": _t,
                    "oracle_span": _pe.get("oracle_span", [0, 0]),
                    "note": f"{_t.split(':',1)[1].capitalize()} keyword (granted by this card)",
                })
                _existing_kw_props2.add(_t)

    # Card 002: face-level "Choose one/two/one or both" modal detector.
    # Some modal cards split the mode effects into separate ability
    # objects with no shared preamble, so neither the extraction's own
    # modal op nor F4's synthesis fires. Sweep the oracle text (outside
    # quoted grants) for a "Choose X —" preamble and emit a
    # MODAL_MARKER edge in produces with the detected mode.
    import re as _re
    _oracle_text = face.get("oracle_text") or ""
    _oracle_for_choose = _re.sub(r'"[^"]*"', "", _oracle_text)
    _existing_modal = any(
        e.get("predicate") == "MODAL_MARKER" for e in port["produces"]
    )
    _choose_match = _re.search(
        r"choose (one or both|one|two|three)\s*[—\-]",
        _oracle_for_choose, _re.IGNORECASE,
    )
    _synth_mod = port.get("modality") if isinstance(port.get("modality"), dict) else None
    if not _existing_modal and (_choose_match or _synth_mod):
        _mode_word = _choose_match.group(1).lower() if _choose_match else (
            (_synth_mod.get("kind") or "").replace("choose_", "").replace("_", " ")
            if _synth_mod else "one"
        )
        _entry: dict[str, Any] = {
            "predicate": "MODAL_MARKER",
            "mode": _mode_word,
            "oracle_span": [0, len(_oracle_text)],
        }
        # Attach mode metadata from the synthesized modality if present.
        if _synth_mod:
            _entry["mode_kind"] = _synth_mod.get("kind")
            if _synth_mod.get("modes"):
                _entry["mode_count"] = len(_synth_mod["modes"])
        port["produces"].append(_entry)

    # Card 002: face-level named-ability-word keyword detector. Some
    # keyword abilities and ability words (per CR 207.2c) appear only as
    # italicised markers in the oracle text -- "Landfall — Whenever a
    # land you control enters, ...", "Ferocious — Whenever this creature
    # attacks while you control a creature with power 4+, ...",
    # "Threshold — ...". The extraction sometimes represents the trigger
    # but not the marker itself, so the port ends up carrying the
    # triggered edge without the HAS_KEYWORD property. Sweep the oracle
    # text (with quoted grants stripped so a Saga's granted landfall
    # doesn't attribute native landfall to the Saga) and emit
    # HAS_KEYWORD for every marker found.
    import re as _re
    # Note: we do NOT strip quoted text here. A card that grants a keyword
    # ability inside a quoted string ("Landfall — Whenever ...") still
    # deserves the HAS_KEYWORD tag on its port because consumers looking
    # for "cards with Landfall in their ability text" want to find it.
    # Down in the Valley (Saga chapter II gains "Landfall — ...") is the
    # canonical case.
    _oracle_text = face.get("oracle_text") or ""
    _NAMED_ABILITY_WORDS = ("landfall", "ferocious", "threshold")
    # Flashback marker: "Flashback {N}{X}" -- word followed by mana cost.
    # (Kicker uses the same pattern; both are keyword abilities that pair
    # with a mana cost rather than the "— text" ability-word format.)
    # Keywords that pair with a mana cost in the oracle text:
    #   "Flashback {2}{U}", "Kicker {1}", "Equip {3}", "Equip—{2}, Pay 2 life.",
    #   "Ward {1}" -- all match "<keyword> [{mana}]" or "<keyword>—{mana}".
    _KEYWORD_WITH_MANA_MARKER = ("flashback", "kicker", "equip", "ward")
    _existing_kw_targets = {
        e.get("target") for e in port["properties"]
        if e.get("predicate") == "HAS_KEYWORD"
    }
    for _aw in _NAMED_ABILITY_WORDS:
        _kw_id = f"keyword:{_aw}"
        if _kw_id in _existing_kw_targets:
            continue
        if _re.search(rf"\b{_aw}\s*[—\-]", _oracle_text, _re.IGNORECASE):
            if _kw_id in declared_concepts:
                port["properties"].append({
                    "predicate": "HAS_KEYWORD",
                    "target": _kw_id,
                    "oracle_span": [0, len(_oracle_text)],
                    "note": f"{_aw.capitalize()} ability word",
                })
    for _aw in _KEYWORD_WITH_MANA_MARKER:
        _kw_id = f"keyword:{_aw}"
        if _kw_id in _existing_kw_targets:
            continue
        # Match "Flashback {2}{U}" or "Flashback—{4}{B}" etc.
        if _re.search(rf"\b{_aw}\s*[—\-]?\s*\{{", _oracle_text, _re.IGNORECASE):
            if _kw_id in declared_concepts:
                port["properties"].append({
                    "predicate": "HAS_KEYWORD",
                    "target": _kw_id,
                    "oracle_span": [0, len(_oracle_text)],
                    "note": f"{_aw.capitalize()} keyword",
                })

    # Card 002: predicate-implies-keyword sweep. Any edge whose predicate
    # is itself a named keyword ability implies HAS_KEYWORD keyword:X.
    # RECRUIT -> keyword:recruit, AMASS -> keyword:amass, FLASHBACK ->
    # keyword:flashback, TYPECYCLING -> keyword:cycling, BEHOLDS ->
    # keyword:beholds. INSTALLS_WATCHER gate:storied -> keyword:storied
    # for the 7 storied cards that don't also emit HAS_KEYWORD via
    # ab.keyword (Balin, Bombur, Dain, Fili, Kili, Oin, Thorin).
    _PREDICATE_TO_KEYWORD = {
        "RECRUIT": "keyword:recruit",
        "AMASS": "keyword:amass",
        "FLASHBACK": "keyword:flashback",
        "TYPECYCLING": "keyword:cycling",
        "BEHOLDS": "keyword:beholds",
    }
    _existing_kw3 = {
        e.get("target") for e in port["properties"]
        if e.get("predicate") == "HAS_KEYWORD"
    }
    for _pe in port["produces"] + port["installs"]:
        _pred = _pe.get("predicate")
        _kw_id = _PREDICATE_TO_KEYWORD.get(str(_pred))
        # Special-case: gate:storied install implies keyword:storied
        if (_pred == "INSTALLS_WATCHER" and
                _pe.get("target") == "gate:storied"):
            _kw_id = "keyword:storied"
        if _kw_id and _kw_id not in _existing_kw3 and _kw_id in declared_concepts:
            port["properties"].append({
                "predicate": "HAS_KEYWORD",
                "target": _kw_id,
                "oracle_span": _pe.get("oracle_span", [0, 0]),
                "note": f"{_kw_id.split(':',1)[1].capitalize()} keyword (implied by {_pred} edge)",
            })
            _existing_kw3.add(_kw_id)

    # Card 002: "Enchant creature" / "Enchant permanent" style keywords.
    # Aura cards print "Enchant <type>" as their enchant keyword.
    import re as _re5
    if _re5.search(r"\benchant\s+(creature|permanent|artifact|land|player)", _oracle_text, _re5.IGNORECASE):
        _kw = "keyword:enchant"
        if _kw not in {e.get("target") for e in port["properties"]
                        if e.get("predicate") == "HAS_KEYWORD"}:
            if _kw in declared_concepts:
                port["properties"].append({
                    "predicate": "HAS_KEYWORD",
                    "target": _kw,
                    "oracle_span": [0, len(_oracle_text)],
                    "note": "Enchant keyword",
                })

# Card 002 axis 3: classify every non-mana `amount` field so    # Card 002 axis 3: classify every non-mana `amount` field so
    # consumers can distinguish literal counts from symbolic (X, *) and
    # scaling ("one per Halfling you control", "equal to the sacrificed
    # creature\'s power") values. Adds `amount_kind` alongside amount.
    # Mana amounts on CONSUMES_MANA / PRODUCES_MANA are self-identified
    # (they carry `class: resource:mana` or `mana` field) and skip this
    # tagging.
    def _classify_amount(v: object) -> str | None:
        if isinstance(v, (int, float)):
            return "literal"
        if not isinstance(v, str):
            return None
        s = v.strip()
        if not s:
            return None
        # Mana notation like "{2}{W}" -- leave alone.
        if s.startswith("{") and s.endswith("}"):
            return None
        # Single symbol X / N / Y or literal "*".
        if s in ("*", "X", "N", "Y") or (len(s) == 1 and s.isalpha()):
            return "variable"
        # Signed P/T like "+1/+1" -- literal delta.
        import re as _re_am
        if _re_am.match(r"^[+-]?\d+/[+-]?\d+$", s):
            return "literal"
        # Digit-only string.
        if s.isdigit():
            return "literal"
        # Anything with scaling language.
        if any(kw in s.lower() for kw in (
            "per ", "for each", "equal to", "where x", "number of",
            "amount of", "cards in", "power", "toughness",
        )):
            return "scaling"
        # Fallback: descriptive expression.
        return "expression"

    for _sec in ("properties", "installs", "consumes", "produces", "costs"):
        for _e in port[_sec]:
            if "amount_kind" in _e or "amount" not in _e:
                continue
            # Skip mana-notation amounts (they're self-identified).
            if (_e.get("class") == "resource:mana"
                    or _e.get("mana") is not None
                    or (isinstance(_e.get("amount"), str)
                        and _e["amount"].startswith("{"))):
                continue
            _kind = _classify_amount(_e.get("amount"))
            if _kind is not None:
                _e["amount_kind"] = _kind

    # Card 002 axis 1: consolidate low-count predicate aliases into their    # Card 002 axis 1: consolidate low-count predicate aliases into their
    # canonical high-count cousins, lifting the distinguishing info into
    # structured fields (from_zone / to_zone / subject / state) so the
    # semantic difference is preserved as data. Reduces predicate churn
    # in the graph without losing information.
    _ALIAS_CONSOLIDATION = {
        # Singular / generic / partial-move all fold to MOVES_CARDS.
        # to_zone / from_zone are already lifted; nothing else to add.
        "MOVES_CARD": ("MOVES_CARDS", {}),
        "MOVES_ZONE": ("MOVES_CARDS", {}),
        "MOVES_REST": ("MOVES_CARDS", {"subject_scope": "rest"}),
        "MOVES_TO_HAND": ("MOVES_CARDS", {"to_zone": "hand"}),
        "MOVES_TO_LIBRARY": ("MOVES_CARDS", {"to_zone": "library"}),
        # Exile variants fold to EXILES, with the modifier lifted.
        "EXILES_FROM_LIBRARY": ("EXILES", {"from_zone": "library"}),
        "EXILES_FACE_DOWN": ("EXILES", {"state": "face_down"}),
        "EXILES_SELF": ("EXILES", {"subject": "self"}),
        # Reveal variants all fold to REVEALS with a mode/subject/flag.
        "REVEALS_HAND": ("REVEALS", {"subject": "hand"}),
        "REVEALS_UNTIL": ("REVEALS", {"mode": "until"}),
        "REVEALS_AND_TAKES": ("REVEALS", {"and_takes": True}),
        # Return variants fold to RETURNS with from_zone/to_zone.
        "RETURNS_FROM_EXILE": ("RETURNS", {"from_zone": "exile"}),
        "RETURNS_FROM_GRAVEYARD": ("RETURNS", {"from_zone": "graveyard"}),
        "RETURNS_TO_HAND": ("RETURNS", {"to_zone": "hand"}),
        # Shuffle variants fold to SHUFFLES with to_zone.
        "SHUFFLES_INTO_LIBRARY": ("SHUFFLES", {"to_zone": "library"}),
        # Type-modification family: ADDS_TYPE (in addition to), SETS_TYPE
        # (replaces), CHANGES_TYPE (unspecified), CHANGES_CHARACTERISTICS
        # (broader). Fold the last three into CHANGES_TYPE with a `mode`
        # field naming the specific kind of change.
        "SETS_TYPE": ("CHANGES_TYPE", {"mode": "set"}),
        "CHANGES_CHARACTERISTICS": ("CHANGES_TYPE", {"mode": "characteristics"}),
    }
    for _sec in ("properties", "installs", "consumes", "produces", "costs"):
        for _e in port[_sec]:
            _p = _e.get("predicate")
            if _p in _ALIAS_CONSOLIDATION:
                _canonical, _extra = _ALIAS_CONSOLIDATION[_p]
                _e["predicate"] = _canonical
                for _k, _v in _extra.items():
                    if _k not in _e:
                        _e[_k] = _v

    # Card 002 axis 4: canonicalize endpoint shape. Each non-property
    # edge should have either a concept-id `target` or a natural-language
    # `target_text` describing what it operates on. The extraction
    # sometimes leaves both empty for player-scoped effects (DRAWS,
    # GAINS_LIFE, LOSES_LIFE, MILLS, SCRIES with an implicit "you"
    # subject) and for self-scoped effects (MODIFIES_PT of "this
    # creature", SETS_PT, TAPS with subject=self). Fill in the implicit
    # target_text so consumers see the same shape everywhere:
    #   * subject field present -> mirror to target_text
    #   * player-scoped predicate with no target -> default target_text="you"
    #   * scope field present -> mirror to target_text
    _PLAYER_SCOPED_PREDS = (
        "DRAWS", "GAINS_LIFE", "LOSES_LIFE", "MILLS", "SCRIES",
    )
    _LIBRARY_SCOPED_PREDS = ("TUTORS", "SHUFFLES", "LOOKS_AT")
    _HAND_SCOPED_PREDS = ("DISCARDS",)
    for _sec in ("properties", "installs", "consumes", "produces", "costs"):
        for _e in port[_sec]:
            if _e.get("target_text") or _e.get("target"):
                continue
            _subj = _e.get("subject")
            _scope = _e.get("scope")
            if isinstance(_subj, str) and _subj:
                _e["target_text"] = _subj
            elif isinstance(_scope, str) and _scope:
                _e["target_text"] = _scope
            elif _e.get("predicate") in _PLAYER_SCOPED_PREDS:
                _e["target_text"] = _e.get("controller") or "you"
            elif _e.get("predicate") in _LIBRARY_SCOPED_PREDS:
                _e["target_text"] = "your library"
            elif _e.get("predicate") in _HAND_SCOPED_PREDS:
                # Discard is a cost paid from hand.
                _e["target_text"] = "your hand"

    # Card 002 axis 7: infer a structured `selector` from `target_text`
    # when one isn't already present. Consumers filtering by
    # "target-scoped edges" or "each-scoped edges" get a machine-
    # readable answer instead of having to parse natural language.
    #
    # Heuristics from the target_text:
    #   "target ..."                -> selector.target.count = 1
    #   "each ..." / "all ..."      -> selector.scope = "each"
    #   "you control"               -> selector.controller = "you"
    #   "an opponent controls"      -> selector.controller = "opponent"
    #   "opponents control"         -> selector.controller = "opponent"
    #   "your opponents control"    -> selector.controller = "opponent"
    def _infer_selector(_tt: str) -> dict[str, Any] | None:
        _sel: dict[str, Any] = {}
        _lt = _tt.lower()
        if "target " in _lt:
            _sel["target"] = {"count": 1}
        if "each " in _lt or _lt.startswith("all "):
            _sel["scope"] = "each"
        if "you control" in _lt:
            _sel["controller"] = "you"
        elif ("an opponent controls" in _lt
              or "opponents control" in _lt
              or _lt.strip() == "each opponent"
              or "your opponents" in _lt):
            _sel["controller"] = "opponent"
        return _sel or None

    _TARGET_PHRASES = ("target ", "each ", "all creatures", "each opponent")
    for _sec in ("properties", "installs", "consumes", "produces", "costs"):
        for _e in port[_sec]:
            _tt2 = _e.get("target_text")
            if not isinstance(_tt2, str) or not _tt2:
                continue
            if _e.get("selector") is not None:
                continue
            if not any(w in _tt2.lower() for w in _TARGET_PHRASES):
                continue
            _inferred = _infer_selector(_tt2)
            if _inferred:
                _e["selector"] = _inferred

    return normalize_port_order(port)


def derive_all(
    face_ids: list[str] | None = None,
    all_faces: bool = False,
    data_dir: pathlib.Path = ROOT / "data",
    vocab_dir: pathlib.Path = ROOT / "data" / "vocabulary",
) -> list[dict[str, Any]]:
    """Derive port records.

    Modes (mutually exclusive; first-truthy wins):
      * all_faces=True   -> derive for every face in normalized/faces.jsonl,
                            using the full Phase-3 extraction (llm_accepted.jsonl).
                            This is the Card 002 whole-set mode.
      * face_ids=[...]   -> derive for the specified normalized face ids only.
      * default          -> pilot slice (11 faces from data/pilot/).
    """

    pilot_faces = read_jsonl(data_dir / "pilot" / "faces.jsonl")

    # Determine which faces to process
    if all_faces:
        faces = read_jsonl(data_dir / "normalized" / "faces.jsonl")
        extraction_path = data_dir / "review" / "llm_accepted.jsonl"
    elif face_ids:
        all_normalized = read_jsonl(data_dir / "normalized" / "faces.jsonl")
        faces = [f for f in all_normalized if f["id"] in face_ids]
        extraction_path = data_dir / "review" / "llm_accepted.jsonl"
    else:
        faces = pilot_faces
        extraction_path = data_dir / "pilot" / "llm_accepted.jsonl"

    # Load extraction
    extractions = read_jsonl(extraction_path)
    extraction_by_face = {e["face_id"]: e for e in extractions}

    # Load census (full-set path when running --all or with explicit face_ids)
    census_path = (
        data_dir / "pilot" / "effect_census.jsonl"
        if (not face_ids and not all_faces)
        else data_dir / "graph_global" / "effect_census.jsonl"
    )
    census = read_jsonl(census_path) if census_path.exists() else []

    # Load vocabularies
    op_map = load_op_map(vocab_dir)
    type_categories = load_type_categories(vocab_dir)
    declared_concepts = load_concepts(vocab_dir)
    token_specs = load_token_specs(data_dir / "raw" / "scryfall_hob_tokens.json")

    # Derive ports
    ports = []
    for face in faces:
        face_id = face["id"]
        extraction = extraction_by_face.get(face_id)

        # Join census by span if available
        census_by_ability: dict[str, list[dict[str, Any]]] = {}
        if extraction and census:
            census_by_ability = join_by_span(
                [c for c in census if c.get("face_id") == face_id],
                extraction.get("abilities", []),
            )

        port = derive_port(
            face, extraction, census_by_ability, op_map, type_categories,
            declared_concepts, token_specs=token_specs,
        )
        ports.append(port)

    return ports


def validate_ports(ports: list[dict[str, Any]], vocab_dir: pathlib.Path) -> dict[str, Any]:
    """Validate port records and return stats."""
    declared_concepts = load_concepts(vocab_dir)
    stats: dict[str, Any] = {
        "total_ports": len(ports),
        "total_edges": 0,
        "undeclared_concepts": [],
        "unresolved_abilities": 0,
        "selector_in_name": [],
    }

    selector_patterns = [
        "target-creature",
        "creature-you-control",
        "up-to-one",
        "another-creature",
        "equipped-creature",
    ]

    for port in ports:
        for section in ["properties", "installs", "consumes", "produces", "costs"]:
            for edge in port.get(section, []):
                stats["total_edges"] += 1
                target = edge.get("target", "")

                # Check for selector-in-name anti-pattern. Event concepts are
                # exempt: CR-defined trigger predicates legitimately embed a
                # subject qualifier ("nontoken creature you control dies",
                # "equipped creature deals combat damage") and are single,
                # well-defined trigger patterns rather than compound ObjectClass
                # names.
                if not target.startswith("event:") and any(
                    pattern in target for pattern in selector_patterns
                ):
                    stats["selector_in_name"].append({
                        "face": port["face_id"],
                        "target": target,
                    })

                # Check if concept is declared
                if target and target not in declared_concepts:
                    # Skip derived types - they come from type_categories
                    if not target.startswith("obj:type:"):
                        stats["undeclared_concepts"].append({
                            "face": port["face_id"],
                            "concept": target,
                        })

        stats["unresolved_abilities"] += len(port.get("unresolved", []))

    return stats


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    argv = argv if argv is not None else sys.argv[1:]

    if "--validate" in argv:
        output_path = ROOT / "data" / "graph_global" / "card_ports.jsonl"
        if not output_path.exists():
            print(f"No output to validate: {output_path}", file=sys.stderr)
            return 1

        ports = read_jsonl(output_path)
        stats = validate_ports(ports, ROOT / "data" / "vocabulary")
        print(json.dumps(stats, indent=2))

        if stats["selector_in_name"]:
            print("\nERROR: Selector-in-name anti-pattern detected", file=sys.stderr)
            return 1
        if stats["undeclared_concepts"]:
            print("\nERROR: Undeclared concepts found", file=sys.stderr)
            return 1

        return 0

    # Parse --face and --all arguments
    face_ids = []
    all_faces = False
    i = 0
    while i < len(argv):
        if argv[i] == "--face" and i + 1 < len(argv):
            face_ids.append(argv[i + 1])
            i += 2
        elif argv[i] == "--all":
            all_faces = True
            i += 1
        else:
            i += 1

    if all_faces and face_ids:
        print("--all and --face are mutually exclusive", file=sys.stderr)
        return 2

    # Derive ports
    ports = derive_all(face_ids if face_ids else None, all_faces=all_faces)

    # Write output
    output_path = ROOT / "data" / "graph_global" / "card_ports.jsonl"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_path, ports)

    print(f"Derived {len(ports)} port records -> {output_path}")

    # Print tally
    total_unresolved = sum(len(p.get("unresolved", [])) for p in ports)
    print(f"Unresolved abilities: {total_unresolved}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

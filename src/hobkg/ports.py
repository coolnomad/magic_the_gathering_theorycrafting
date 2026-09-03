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
    if ("another_dwarf_or_equipment" in event_norm) or ("dwarf you control enters" in event_lower):
        return "event:another-dwarf-or-equipment-enters"
    if "land_enters" in event_norm or "land you control enters" in event_lower:
        return "event:land-enters-under-your-control"
    if "artifact_you_control_enters" in event_norm or "artifact you control enters" in event_lower:
        return "event:artifact-enters-under-your-control"
    # This-permanent (equipment / artifact / enchantment / aura) enters
    if any(x in event_norm for x in (
        "this_permanent_enters", "permanent_enters",
        "this_equipment_enters", "this_artifact_enters",
        "this_enchantment_enters", "this_aura_enters",
    )):
        return "event:this-permanent-enters"
    if any(x in event_lower for x in (
        "this equipment enters", "this artifact enters",
        "this enchantment enters", "this aura enters",
    )):
        return "event:this-permanent-enters"
    # Enters-or-attacks
    if "enters_or_attacks" in event_norm or "enters or attacks" in event_lower:
        return "event:this-creature-enters-or-attacks"
    # This-creature enters (explicit)
    if event_norm in ("this_creature_enters", "creature_enters",
                      "enters_the_battlefield", "enters"):
        return "event:this-creature-enters"
    if "this creature enters" in event_lower or "creature enters" in event_lower:
        return "event:this-creature-enters"
    # Subject-name enters (self-reference: "Dain enters the battlefield", "thorin_enters")
    if (event_norm.endswith("_enters") or
            event_lower.strip().endswith("enters the battlefield") or
            event_lower.strip().endswith(" enters")):
        return "event:this-creature-enters"

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
        return port

    abilities = extraction.get("abilities", [])

    for ab in abilities:
        ab_id = ab.get("ability_id", "")
        # 'kind' from the extraction (static / triggered / activated / spell_effect /
        # replacement) is not currently branched on -- the disposition falls out of
        # the trigger, cost and effect shape. Kept out of the loop until we need it.

        # Lift ability-level mana costs (activated abilities' mana costs like
        # Wizard's Staff's two equip costs {1} and {3}, or Glamdring's equip
        # {2}). The extraction is schema-loose here -- costs use either
        #   {"op": "pay_mana", "amount": "{X}"}    (Wizard's Staff shape)
        #   {"type": "mana",   "detail": "{X}"}    (Glamdring shape)
        # -- so we accept either. Sacrifice costs and additional_cost
        # definitions are handled by the effect processor further down; here
        # we only surface the mana entries the effect loop doesn't touch.
        for _cost in ab.get("costs", []) or []:
            if not isinstance(_cost, dict):
                continue
            _cop = _cost.get("op")
            _ctype = _cost.get("type")
            _camt = _cost.get("amount") or _cost.get("detail")
            _is_mana = (_cop == "pay_mana") or (_ctype == "mana")
            if _is_mana and _camt:
                port["costs"].append({
                    "predicate": "CONSUMES_MANA",
                    "amount": _camt,
                    "class": "resource:mana",
                    "purpose": "activation",
                    "ability": ab_id,
                    "oracle_span": ab.get("oracle_spans", [[0, 0]])[0],
                })

        # Map triggers to consumes
        trigger = ab.get("trigger")
        if trigger:
            event_id = map_trigger_to_event(trigger)
            if event_id:
                if event_id not in declared_concepts:
                    port["unresolved"].append({
                        "ability_id": ab_id,
                        "reason": f"Undeclared event concept: {event_id}",
                        "clause_text": trigger.get("text", str(trigger)),
                    })
                else:
                    port["consumes"].append({
                        "predicate": "TRIGGERS_ON",
                        "target": event_id,
                        "oracle_span": ab.get("oracle_spans", [[0, 0]])[0],
                    })

        # Keyword abilities. When the keyword branch itself emits the semantic
        # action, record the verb so the effect loop below does not emit a
        # second, malformed edge for the same fact (F2 watcher.duplicate_install).
        keyword = ab.get("keyword")
        consumed_verbs: set[str] = set()
        if keyword:
            kw_lower = keyword.lower()
            kw_id = f"keyword:{kw_lower}"
            if kw_lower == "storied":
                # Storied installs watcher
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

            # Add selector if applicable
            if "target" in effect or "affects" in effect:
                selector = build_selector(effect)
                if selector:
                    entry["selector"] = selector

            # Add amount/quantity if present
            if "amount" in effect:
                entry["amount"] = effect["amount"]
            if "quantity" in effect:
                entry["quantity"] = effect["quantity"]

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

            # Categorize by predicate.
            if predicate in ("CONSUMES_MANA", "SACRIFICES", "ADDITIONAL_COST"):
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

    return port


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
            face, extraction, census_by_ability, op_map, type_categories, declared_concepts
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

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
    """Map trigger dict to Event concept."""
    event = trigger.get("event", "")

    # Normalize: handle both underscore and space variants
    event_norm = event.replace(" ", "_").lower()

    if event_norm == "this_creature_attacks" or "creature attacks" in event.lower():
        return "event:this-creature-attacks"
    if event_norm == "this_creature_dies" or "creature dies" in event.lower():
        return "event:this-creature-dies"
    if event_norm == "this_creature_enters" or "enters" in event.lower():
        return "event:this-creature-enters"
    if "enters_or_attacks" in event_norm or "enters or attacks" in event.lower():
        return "event:this-creature-enters-or-attacks"
    if "cast" in event.lower() and "spell" in event.lower():
        return "event:you-cast-spell"
    if "activate" in event.lower() and "creature" in event.lower():
        return "event:you-activate-creature-ability"
    # F3 saga.silent_chapter_loss: Saga chapter abilities trigger when a lore
    # counter causes the chapter to become current (CR 714.3a).
    if "lore_count_reaches" in event_norm or "lore counter" in event.lower():
        return "event:saga-chapter"

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
            # Find verb
            verb = None
            source_key = None
            for key in ["op", "effect", "action", "type"]:
                if key in effect:
                    verb = effect[key]
                    source_key = key
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
    data_dir: pathlib.Path = ROOT / "data",
    vocab_dir: pathlib.Path = ROOT / "data" / "vocabulary",
) -> list[dict[str, Any]]:
    """Derive port records for pilot faces or specified faces."""

    # Load pilot face set. face_ids-arg mode falls through to the full-set
    # faces.jsonl below, so we do not need a per-slice id filter here.
    pilot_faces = read_jsonl(data_dir / "pilot" / "faces.jsonl")

    # Determine which faces to process
    if face_ids:
        # Load from full sources
        all_faces = read_jsonl(data_dir / "normalized" / "faces.jsonl")
        faces = [f for f in all_faces if f["id"] in face_ids]
        extraction_path = data_dir / "review" / "llm_accepted.jsonl"
    else:
        # Use pilot slices
        faces = pilot_faces
        extraction_path = data_dir / "pilot" / "llm_accepted.jsonl"

    # Load extraction
    extractions = read_jsonl(extraction_path)
    extraction_by_face = {e["face_id"]: e for e in extractions}

    # Load census
    census_path = (
        data_dir / "pilot" / "effect_census.jsonl"
        if not face_ids
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

                # Check for selector-in-name anti-pattern
                for pattern in selector_patterns:
                    if pattern in target:
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

    # Parse --face arguments
    face_ids = []
    i = 0
    while i < len(argv):
        if argv[i] == "--face" and i + 1 < len(argv):
            face_ids.append(argv[i + 1])
            i += 2
        else:
            i += 1

    # Derive ports
    ports = derive_all(face_ids if face_ids else None)

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

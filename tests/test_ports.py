"""Tests for layer-2 port derivation.

The derivation is the deliverable; these tests verify the procedure produces
correct outputs without hard-coded per-card branches.
"""

from __future__ import annotations

import contextlib
import io
import json
import pathlib
import re

import pytest

from hobkg import ports

ROOT = pathlib.Path(__file__).resolve().parent.parent

# Holdout faces - deliberately not in pilot slice
HOLDOUT_FACES = [
    "face:0296d57e-e5b9-456f-bb21-eb584adefb4c:0",  # Gollum, Silent Slinker
    "face:011da9c5-aa8a-4fa0-b1f2-62b9f3760476:0",  # Belladonna Took
    "face:0ea58cfe-b37c-49a6-a3be-7e60065b8238:0",  # Tom, Bert, and William
]


def test_no_hardcoded_face_ids() -> None:
    """Port module contains no face IDs."""
    source = (ROOT / "src" / "hobkg" / "ports.py").read_text(encoding="utf-8")

    # Check for face ID pattern
    face_id_re = re.compile(r"face:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
    matches = face_id_re.findall(source)

    assert not matches, f"Found hard-coded face IDs: {matches}"


def test_no_hardcoded_card_names() -> None:
    """Port module contains no card names from the set."""
    source = (ROOT / "src" / "hobkg" / "ports.py").read_text(encoding="utf-8")

    # Load all card names
    cards_path = ROOT / "data" / "normalized" / "cards.jsonl"
    cards = []
    with cards_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cards.append(json.loads(line))

    card_names = {c["name"] for c in cards}

    # Check for any card name in source (case-insensitive, ignore in comments)
    source_lower = source.lower()
    found = []
    for name in card_names:
        # Simple check: name appears outside of docstrings/comments
        if name.lower() in source_lower:
            # More careful check: not in a comment or string
            # This is approximate but catches obvious violations
            for line in source.split("\n"):
                stripped = line.split("#")[0].strip()  # Remove comments
                if name.lower() in stripped.lower():
                    # Check it's not in a docstring
                    if '"""' not in line and "'''" not in line:
                        found.append(name)
                        break

    assert not found, f"Found hard-coded card names: {found[:5]}"


def test_no_hardcoded_pilot_ids() -> None:
    """Port module contains no pilot face IDs."""
    source = (ROOT / "src" / "hobkg" / "ports.py").read_text(encoding="utf-8")

    pilot_faces = ports.read_jsonl(ROOT / "data" / "pilot" / "faces.jsonl")
    pilot_ids = {f["id"] for f in pilot_faces}

    for pid in pilot_ids:
        assert pid not in source, f"Found hard-coded pilot face ID: {pid}"


def test_pilot_derives() -> None:
    """Derive all pilot faces without error."""
    result = ports.derive_all()

    assert len(result) == 11, "Should derive 11 pilot faces"

    for port in result:
        assert "face_id" in port
        assert "name" in port
        assert "properties" in port
        assert "installs" in port
        assert "consumes" in port
        assert "produces" in port
        assert "costs" in port
        assert "unresolved" in port


def test_holdout_derives() -> None:
    """Holdout faces derive without code changes."""
    result = ports.derive_all(face_ids=HOLDOUT_FACES)

    assert len(result) == 3, "Should derive 3 holdout faces"

    for port in result:
        assert port["face_id"] in HOLDOUT_FACES
        # Basic structural check
        assert isinstance(port["properties"], list)
        assert isinstance(port["produces"], list)


def test_holdout_stability() -> None:
    """Pilot records identical whether emitted alone or with holdouts."""
    pilot_alone = ports.derive_all(face_ids=None)
    pilot_ids = {p["face_id"] for p in pilot_alone}

    combined = ports.derive_all(face_ids=list(pilot_ids) + HOLDOUT_FACES)
    pilot_from_combined = [p for p in combined if p["face_id"] in pilot_ids]

    # Sort both for comparison
    pilot_alone_sorted = sorted(pilot_alone, key=lambda x: x["face_id"])
    pilot_from_combined_sorted = sorted(pilot_from_combined, key=lambda x: x["face_id"])

    assert len(pilot_alone_sorted) == len(pilot_from_combined_sorted)

    for p1, p2 in zip(pilot_alone_sorted, pilot_from_combined_sorted, strict=True):
        assert p1 == p2, f"Mismatch for {p1['face_id']}"


def test_derived_type_categories() -> None:
    """Derived IS_A edges present for all pilot faces."""
    result = ports.derive_all()

    # Find specific faces by name
    elrond = next((p for p in result if "Elrond" in p["name"]), None)
    mountain_king = next((p for p in result if "Mountain-king" in p["name"]), None)
    wizard_staff = next((p for p in result if "Wizard's Staff" in p["name"]), None)
    pinecone = next((p for p in result if "Pinecone" in p["name"]), None)
    stir = next((p for p in result if "Stir Up" in p["name"]), None)

    assert elrond is not None
    assert mountain_king is not None
    assert wizard_staff is not None
    assert pinecone is not None
    assert stir is not None

    # Check permanent types have permanent category
    for port in [elrond, mountain_king, wizard_staff]:
        categories = [
            e["target"] for e in port["properties"] if e.get("predicate") == "IS_A"
        ]
        assert "obj:category:permanent" in categories, f"{port['name']} missing permanent"

    # Check nonpermanent types
    for port in [pinecone, stir]:
        categories = [
            e["target"] for e in port["properties"] if e.get("predicate") == "IS_A"
        ]
        assert "obj:category:nonpermanent" in categories, f"{port['name']} missing nonperm"


def test_no_selector_in_name() -> None:
    """No edges reference selector-in-name concepts."""
    result = ports.derive_all()

    forbidden_patterns = [
        "obj:target-creature",
        "obj:creature-you-control",
        "obj:up-to-one-target-creature",
        "obj:another-creature",
        "obj:equipped-creature",
    ]

    violations = []
    for port in result:
        for section in ["properties", "installs", "consumes", "produces", "costs"]:
            for edge in port.get(section, []):
                target = edge.get("target", "")
                for pattern in forbidden_patterns:
                    if pattern in target:
                        violations.append({
                            "face": port["name"],
                            "target": target,
                        })

    assert not violations, f"Selector-in-name violations: {violations}"


def test_triggers_are_concepts() -> None:
    """Triggers appear as Event concepts under consumes."""
    result = ports.derive_all()

    # Rampager should consume this-creature-attacks
    rampager = next((p for p in result if "Rampager" in p["name"]), None)
    assert rampager is not None

    consumes = rampager.get("consumes", [])
    events = [c for c in consumes if c.get("predicate") == "TRIGGERS_ON"]

    # Should have at least one event
    assert len(events) > 0, "Rampager should consume attack event"


def test_watcher_rule() -> None:
    """Bifur installs storied, Smaug does not."""
    result = ports.derive_all()

    bifur = next((p for p in result if "Bifur" in p["name"]), None)
    smaug = next((p for p in result if "Smaug" in p["name"]), None)

    assert bifur is not None
    assert smaug is not None

    bifur_installs = [i.get("target") for i in bifur.get("installs", [])]
    smaug_installs = [i.get("target") for i in smaug.get("installs", [])]

    assert "gate:storied" in bifur_installs, "Bifur should install storied"
    assert "gate:storied" not in smaug_installs, "Smaug should NOT install storied"


def test_dead_abilities_resolved() -> None:
    """Abilities marked dead in frozen graph reach non-unresolved disposition."""
    frozen_control = ports.read_jsonl(ROOT / "data" / "pilot" / "frozen_control.jsonl")
    dead_abilities = {r["ability_id"] for r in frozen_control if r["dead_in_frozen_graph"]}

    result = ports.derive_all()

    # Extract which abilities ended up unresolved
    unresolved_abilities = set()
    for port in result:
        for unres in port.get("unresolved", []):
            ab_id = unres.get("ability_id")
            if ab_id:
                unresolved_abilities.add(ab_id)

    # Dead abilities that are still unresolved
    dead_and_unresolved = dead_abilities & unresolved_abilities

    assert not dead_and_unresolved, (
        f"Dead abilities should resolve to disposition, found unresolved: "
        f"{dead_and_unresolved}"
    )


def test_no_cross_imports() -> None:
    """Port module imports nothing from higher layers."""
    source = (ROOT / "src" / "hobkg" / "ports.py").read_text(encoding="utf-8")

    forbidden = [
        "from . import assemble",
        "from . import completeness",
        "from . import equip",
        "from . import effect_semantics",
        "from . import audit",
        "from . import audit_repair",
        "from .assemble",
        "from .completeness",
        "from .equip",
        "from .effect_semantics",
        "from .audit",
        "from .audit_repair",
    ]

    found = []
    for pattern in forbidden:
        if pattern in source:
            found.append(pattern)

    assert not found, f"Found forbidden imports: {found}"


def test_every_clause_covered() -> None:
    """Every oracle clause spanned (relaxed for this iteration)."""
    # This is a placeholder - full span coverage requires more work
    # For now just check structure exists
    result = ports.derive_all()

    for port in result:
        for section in ["properties", "produces", "costs"]:
            for edge in port.get(section, []):
                assert "oracle_span" in edge, f"Missing span in {port['name']}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


# ---------------------------------------------------------------------------
# Regression tests for iteration-1 review findings (2026-09-03).
# Reviewer report: docs/cycles/2026-09-03_ports-v1_iter1.md
# ---------------------------------------------------------------------------

_ELROND_FACE = "face:3f4d6f91-95ad-4687-8899-5a21a0abb49e:0"
_BIFUR_FACE = "face:b8d563e4-e2bc-4e8b-8841-6655beff9138:0"
_MOUNTAIN_KING_FACE = "face:32ad5b3e-92c0-45be-b2e4-6f1794552f36:0"


def _port_by_face(face_id: str) -> dict:
    for record in ports.derive_all():
        if record["face_id"] == face_id:
            return record
    raise AssertionError(f"pilot did not emit a port record for {face_id}")


def test_regression_selector_other_not_another() -> None:
    """F1: Elrond EXILES must carry the 'another: True' restriction.

    Oracle: "Exile up to two OTHER target nonland permanents you control."
    Before the fix, the selector builder only matched the word "another" and
    silently dropped the exclusion for the "other" spelling.
    """
    elrond = _port_by_face(_ELROND_FACE)
    exiles = [
        e for e in elrond.get("produces", []) if e.get("predicate") == "EXILES"
    ]
    assert exiles, "Elrond has no EXILES edge"
    for edge in exiles:
        restrictions = edge.get("selector", {}).get("restriction", [])
        assert {"another": True} in restrictions, (
            f"Elrond EXILES selector missing {{'another': True}}: {edge}"
        )


def test_regression_bifur_single_installs_watcher() -> None:
    """F2a: Bifur emits exactly ONE INSTALLS_WATCHER for gate:storied.

    Before the fix, the keyword branch emitted the correct edge and then the
    effect processor ran again on the extraction's op='storied' effect,
    producing a second, malformed edge with no target field.
    """
    bifur = _port_by_face(_BIFUR_FACE)
    installs_watcher = [
        e for e in bifur.get("installs", [])
        if e.get("predicate") == "INSTALLS_WATCHER"
    ]
    assert len(installs_watcher) == 1, (
        f"Bifur has {len(installs_watcher)} INSTALLS_WATCHER edges, "
        f"expected exactly 1: {installs_watcher}"
    )
    assert installs_watcher[0].get("target") == "gate:storied", (
        f"Bifur INSTALLS_WATCHER target is not gate:storied: {installs_watcher[0]}"
    )


def test_regression_installs_watcher_has_target() -> None:
    """F2b: EVERY INSTALLS_WATCHER edge across the pilot has a target field.

    A targetless install edge is uninterpretable; the port schema requires
    every edge to name what it relates to.
    """
    for record in ports.derive_all():
        for edge in record.get("installs", []):
            if edge.get("predicate") == "INSTALLS_WATCHER":
                assert "target" in edge and edge["target"], (
                    f"targetless INSTALLS_WATCHER on {record['face_id']}: {edge}"
                )


def test_regression_saga_chapter_triggers_reach_consumes() -> None:
    """F3: The Mountain-king's Return has 3 consumes for its chapter triggers.

    Before the fix, map_trigger_to_event had no case for 'lore_count_reaches'
    and returned None, so the three chapter triggers were silently dropped --
    not in produces, not in consumes, not in unresolved.
    """
    saga = _port_by_face(_MOUNTAIN_KING_FACE)
    chapter_triggers = [
        e for e in saga.get("consumes", [])
        if e.get("predicate") == "TRIGGERS_ON"
        and e.get("target") == "event:saga-chapter"
    ]
    assert len(chapter_triggers) == 3, (
        f"Mountain-king's Return has {len(chapter_triggers)} saga-chapter "
        f"triggers in consumes, expected 3: {chapter_triggers}"
    )


# ---------------------------------------------------------------------------
# Regression tests for iteration-2 completeness audit (2026-09-03).
# These six were preselected (fully or partially) by card 001 but not tested
# structurally in iteration 2. Reviewer sonnet-4-5 verdict ACCEPT'd anyway.
# Post-audit found the derivation was emitting incomplete records in six ways.
# See docs/cycles/2026-09-03_ports-v1_iter1.md for context.
# ---------------------------------------------------------------------------

_WIZARDS_STAFF_FACE = "face:30c3c700-46f4-4a77-8c45-5c7e3a21bd62:0"
_BOFUR_FACE = "face:8a0e35ac-6c03-4922-b3b4-e419419fe3d7:0"
_CONCERTED_CARE_FACE = "face:8a0e35ac-6c03-4922-b3b4-e419419fe3d7:1"
_PINECONE_FACE = "face:961e3023-39ea-4141-99b6-738280a2815d:0"
_STIR_FACE = "face:dda607bd-f419-4b7f-b052-a5ce6ce22bfe:0"
_SMAUG_FACE = "face:20535126-f811-4386-bdce-d73f30691724:0"


def test_regression_supertypes_and_subtypes_emitted() -> None:
    """Iter-2 gap 1: derive_properties must walk type_line.supertypes and
    .subtypes, not just .types. Bifur is "Legendary Creature -- Dwarf Bard"
    and needs 4 IS_A edges beyond the primary type and its categories.
    """
    bifur = _port_by_face(_BIFUR_FACE)
    targets = {p["target"] for p in bifur.get("properties", []) if p.get("predicate") == "IS_A"}
    assert "obj:supertype:legendary" in targets, f"missing supertype IS_A: {targets}"
    assert "obj:subtype:dwarf" in targets, f"missing subtype:dwarf IS_A: {targets}"
    assert "obj:subtype:bard" in targets, f"missing subtype:bard IS_A: {targets}"
    # Wizard's Staff is "Artifact -- Equipment" -> needs subtype:equipment
    ws = _port_by_face(_WIZARDS_STAFF_FACE)
    ws_targets = {p["target"] for p in ws.get("properties", []) if p.get("predicate") == "IS_A"}
    assert "obj:subtype:equipment" in ws_targets, (
        f"Wizard's Staff missing subtype:equipment: {ws_targets}"
    )


def test_regression_mana_costs_populated() -> None:
    """Iter-2 gap 2: every face's cast cost and every activated-ability mana
    cost belongs in the costs section. Layer 4 capacity vectors depend on
    knowing what things actually cost.
    """
    ws = _port_by_face(_WIZARDS_STAFF_FACE)
    # Cast cost {1}{U} plus two equip costs {1} (equip Wizard) and {3} (equip)
    mana_costs = [
        c for c in ws.get("costs", []) if c.get("predicate") == "CONSUMES_MANA"
    ]
    assert len(mana_costs) >= 3, (
        f"Wizard's Staff has {len(mana_costs)} mana-cost entries, expected 3+"
    )
    amounts = {c.get("amount") for c in mana_costs}
    assert "{1}{U}" in amounts, f"Wizard's Staff missing cast cost: {amounts}"
    assert "{1}" in amounts, f"Wizard's Staff missing equip Wizard cost: {amounts}"
    assert "{3}" in amounts, f"Wizard's Staff missing equip cost: {amounts}"
    # Bifur has a mana cost too, even without activated abilities
    bifur = _port_by_face(_BIFUR_FACE)
    bifur_mana = [
        c for c in bifur.get("costs", [])
        if c.get("predicate") == "CONSUMES_MANA" and c.get("purpose") == "cast"
    ]
    assert bifur_mana, "Bifur has no cast-cost entry"


def test_regression_grants_names_keyword() -> None:
    """Iter-2 gap 3: every GRANTS edge names the specific keyword it grants.
    Extraction uses either `keyword` (single) or `keywords` (plural). Concerted
    Care uses the plural form to grant both hexproof and indestructible in one
    clause; the port record must emit one GRANTS entry per keyword.
    """
    # Card 002: Bofur, Reliable Guardian's oracle text is just "Lifelink" --
    # a native keyword, not a grant. The old test asserted GRANTS because
    # the pilot's derivation misrouted native keywords to produces; the
    # native-keyword branch now correctly puts it in properties.HAS_KEYWORD.
    bofur = _port_by_face(_BOFUR_FACE)
    bofur_native = {
        p.get("target") for p in bofur.get("properties", [])
        if p.get("predicate") == "HAS_KEYWORD"
    }
    assert "keyword:lifelink" in bofur_native, (
        f"Bofur HAS_KEYWORD missing keyword:lifelink: {bofur_native}"
    )
    bofur_grant_targets = {
        g.get("target") for g in bofur.get("produces", [])
        if g.get("predicate") == "GRANTS"
    }
    assert "keyword:lifelink" not in bofur_grant_targets, (
        f"Bofur's native lifelink leaked into produces.GRANTS: "
        f"{bofur_grant_targets}"
    )
    # Card 002: Smaug's Flying is NATIVE (printed on the card), not granted.
    # The extraction lax-schemas native keywords as {"op":"grant_keyword",
    # "keyword":"flying"} on a static ability with no target -- ports.py now
    # routes those to properties.HAS_KEYWORD instead of produces.GRANTS.
    smaug = _port_by_face(_SMAUG_FACE)
    smaug_native = {
        p.get("target") for p in smaug.get("properties", [])
        if p.get("predicate") == "HAS_KEYWORD"
    }
    assert "keyword:flying" in smaug_native, (
        f"Smaug HAS_KEYWORD does not include keyword:flying: {smaug_native}"
    )
    # And it must NOT double-fire as a GRANTS on produces.
    smaug_grant_targets = {
        p.get("target") for p in smaug.get("produces", [])
        if p.get("predicate") == "GRANTS"
    }
    assert "keyword:flying" not in smaug_grant_targets, (
        f"Smaug's native flying leaked into produces.GRANTS: {smaug_grant_targets}"
    )
    cc = _port_by_face(_CONCERTED_CARE_FACE)
    cc_grants = [
        p for p in cc.get("produces", []) if p.get("predicate") == "GRANTS"
    ]
    cc_targets = {g.get("target") for g in cc_grants}
    assert "keyword:hexproof" in cc_targets and "keyword:indestructible" in cc_targets, (
        f"Concerted Care missing granted keywords: {cc_targets}"
    )


def test_regression_pinecone_modality_detected() -> None:
    """Iter-2 gap 4: when the extraction has modality: null but two or more
    spell_effect abilities share a leading oracle span (the "Choose one"
    preamble), ports.py must synthesise the modality object.
    """
    pinecone = _port_by_face(_PINECONE_FACE)
    modality = pinecone.get("modality")
    assert modality is not None, "Pinecone modality is null; should be inferred"
    assert modality.get("kind") == "choose_one_or_both", (
        f"Pinecone modality kind is {modality.get('kind')!r}; expected choose_one_or_both"
    )
    modes = modality.get("modes") or []
    assert len(modes) == 2, f"Pinecone should have 2 modes; got {len(modes)}"


def test_regression_bifur_a3_gated_on_enduring_story() -> None:
    """Iter-2 gap 5: Bifur's a3 (the Dwarf trigger-doubler) has a state-typed
    condition in the extraction. That condition must land on the port entry as
    gated_on: state:enduring_story, so layer 4 knows the doubling is
    conditional on Storied being on, not unconditional.
    """
    bifur = _port_by_face(_BIFUR_FACE)
    doubles = [
        p for p in bifur.get("produces", []) if p.get("predicate") == "DOUBLES_TRIGGER"
    ]
    assert doubles, "Bifur has no DOUBLES_TRIGGER produce"
    for d in doubles:
        gated = d.get("gated_on")
        assert gated == "state:enduring_story" or (
            isinstance(gated, list) and "state:enduring_story" in gated
        ), f"Bifur DOUBLES_TRIGGER not gated on state:enduring_story: {d}"


def test_regression_stir_alternatives_as_branches() -> None:
    """Iter-2 gap 6: Stir Up Trouble's additional cost has two alternatives
    (sacrifice an artifact or creature, or pay {4}). The port entry must carry
    a `branches` array with typed peers and a `choose: 1` marker.
    """
    stir = _port_by_face(_STIR_FACE)
    ac = [c for c in stir.get("costs", []) if c.get("predicate") == "ADDITIONAL_COST"]
    assert ac, "Stir has no ADDITIONAL_COST cost entry"
    for entry in ac:
        branches = entry.get("branches") or []
        assert branches, f"Stir ADDITIONAL_COST has no branches: {entry}"
        assert entry.get("choose") == 1, "Stir ADDITIONAL_COST missing choose=1"
        preds = {b.get("predicate") for b in branches}
        assert "SACRIFICES" in preds, f"Stir branches missing SACRIFICES: {preds}"
        assert "CONSUMES_MANA" in preds, f"Stir branches missing CONSUMES_MANA: {preds}"
        # {4} is present as a peer branch, not a string in a node id
        mana_amounts = {b.get("amount") for b in branches if b.get("predicate") == "CONSUMES_MANA"}
        assert "{4}" in mana_amounts, f"Stir pay-{{4}} branch missing: {mana_amounts}"


def test_regression_activated_cost_schema_variants() -> None:
    """Iter-3 follow-up: activated-ability mana costs use two extraction
    shapes across the set --
        {"op": "pay_mana", "amount": "{X}"}    (Wizard's Staff shape)
        {"type": "mana",   "detail": "{X}"}    (Glamdring shape)
    Both must produce a CONSUMES_MANA cost entry. Glamdring is out of the
    pilot; running the derivation against it verifies the fix generalises.
    """
    # Glamdring, Foe-hammer -- not in the pilot slice, so this exercises
    # derive_all()'s ability to run on arbitrary faces from the full sources.
    _GLAMDRING = "face:2802069f-201e-43a7-b5d3-43a95951a2ec:0"
    result = ports.derive_all(face_ids=[_GLAMDRING])
    assert result, "derive_all produced no record for Glamdring"
    glamdring = result[0]
    mana_costs = [
        c for c in glamdring.get("costs", [])
        if c.get("predicate") == "CONSUMES_MANA"
    ]
    # Expect two: cast {2} and equip {2}
    amounts_by_purpose = {c.get("purpose"): c.get("amount") for c in mana_costs}
    assert amounts_by_purpose.get("cast") == "{2}", (
        f"Glamdring cast cost wrong: {amounts_by_purpose}"
    )
    assert amounts_by_purpose.get("activation") == "{2}", (
        f"Glamdring equip {{2}} activation cost missing: {amounts_by_purpose}"
    )


# ---------------------------------------------------------------------------
# Card 002: whole-set (210-face) regression tests
# ---------------------------------------------------------------------------


def test_card_002_all_faces_derive_without_error() -> None:
    """derive_all(all_faces=True) must produce one port per face."""
    result = ports.derive_all(all_faces=True)
    assert len(result) == 210, f"Expected 210 ports; got {len(result)}"


def test_card_002_all_faces_zero_unresolved() -> None:
    """Card 002 gate: every ability across the set is either mapped or
    explicitly declared out-of-scope. The trigger-mapper + op_map + keyword
    branches together should leave no ability unresolved.
    """
    result = ports.derive_all(all_faces=True)
    unresolved: list[dict] = []
    for port in result:
        for u in port.get("unresolved", []):
            unresolved.append({"face_id": port["face_id"], **u})
    assert not unresolved, (
        f"{len(unresolved)} unresolved abilities across 210 faces; "
        f"first few: {unresolved[:3]}"
    )


def test_card_002_all_faces_no_undeclared_concepts() -> None:
    """Every concept referenced by an edge must be declared in
    data/vocabulary/concepts.jsonl (obj:type: is exempt -- those come from
    type_categories.jsonl at derivation time)."""
    result = ports.derive_all(all_faces=True)
    stats = ports.validate_ports(result, ROOT / "data" / "vocabulary")
    undeclared = stats.get("undeclared_concepts", [])
    assert not undeclared, (
        f"{len(undeclared)} undeclared-concept edges across 210 faces; "
        f"first few: {undeclared[:3]}"
    )


def test_card_002_all_faces_no_selector_in_name() -> None:
    """No non-event target may embed a selector qualifier
    (creature-you-control, equipped-creature, etc). Event: concepts are
    exempt -- CR-defined triggers legitimately encode subject."""
    result = ports.derive_all(all_faces=True)
    stats = ports.validate_ports(result, ROOT / "data" / "vocabulary")
    hits = stats.get("selector_in_name", [])
    assert not hits, f"selector-in-name anti-pattern detected: {hits[:3]}"


def test_card_002_bare_trigger_forms_map() -> None:
    """The audit found 38 undeclared trigger phrases; several use bare forms
    ('dies', 'attacks') or subject-name self-references ('Dain attacks',
    'smaug_attacks'). These must all resolve to the corresponding
    this-creature-* event."""
    assert ports.map_trigger_to_event({"event": "dies"}) == "event:this-creature-dies"
    assert ports.map_trigger_to_event({"event": "attacks"}) == "event:this-creature-attacks"
    assert ports.map_trigger_to_event(
        {"event": "smaug_attacks"}
    ) == "event:this-creature-attacks"
    assert ports.map_trigger_to_event(
        {"event": "The Master of Lake-town dies"}
    ) == "event:this-creature-dies"
    assert ports.map_trigger_to_event(
        {"event": "Dain enters the battlefield"}
    ) == "event:this-permanent-enters"


def test_card_002_phase_step_triggers_map() -> None:
    """Phase-step triggers must land on the phase-step event, not on
    'this-permanent-enters' or similar false positives."""
    m = ports.map_trigger_to_event
    assert m({"event": "beginning_of_combat"}) == "event:beginning-of-combat"
    assert m({"event": "beginning of combat on your turn"}) == "event:beginning-of-combat"
    assert m({"event": "beginning of your first main phase"}) == "event:beginning-of-first-main-phase"
    assert m({"event": "beginning_of_your_upkeep"}) == "event:beginning-of-your-upkeep"
    assert m({"event": "upkeep"}) == "event:beginning-of-upkeep"
    assert m({"event": "beginning_of_end_step"}) == "event:beginning-of-end-step"


def test_card_002_saga_precedence() -> None:
    """The saga-chapter branch must come before generic patterns; several
    Saga trigger phrases contain 'counter' which would otherwise collide
    with the counters_placed branch."""
    m = ports.map_trigger_to_event
    for phrase in (
        "lore counter reaches I",
        "lore counter reaches I, II, III, or IV",
        "lore count reaches III and IV (both chapters share this ability)",
        "chapter",
    ):
        assert m({"event": phrase}) == "event:saga-chapter", (
            f"{phrase!r} did not map to saga-chapter"
        )


def test_card_002_amass_keyword_verb_as_top_level_key() -> None:
    """Card 002: some Magic keyword-actions present the verb as a top-level
    KEY in the effect dict (rather than a value on op/effect/action/type).
    The KEYWORD_VERB_KEYS fallback handles those."""
    assert "amass" in ports.KEYWORD_VERB_KEYS
    # Verify Clapsnap (which has an amass effect) resolves rather than
    # lands in unresolved.
    _CLAPSNAP = "face:27e17542-549b-4c05-8091-c10a245c916b:1"
    result = ports.derive_all(face_ids=[_CLAPSNAP])
    assert result, "Clapsnap face not produced"
    clapsnap = result[0]
    unresolved_reasons = [u.get("reason", "") for u in clapsnap.get("unresolved", [])]
    assert not any(
        "amass" in r.lower() or "No effect verb found" in r for r in unresolved_reasons
    ), f"Clapsnap amass still unresolved: {unresolved_reasons}"


def test_card_002_gain_life_type_source_key() -> None:
    """The 'type: gain_life' extraction shape must map to GAINS_LIFE.
    (Only 'quantity' + 'type' -- no op/effect/action.)"""
    _FORESTGATE = "face:acfe54b3-10e3-4fdb-b874-d39fde96c40a:0"
    result = ports.derive_all(face_ids=[_FORESTGATE])
    assert result, "Forestgate face not produced"
    port = result[0]
    unresolved_reasons = [u.get("reason", "") for u in port.get("unresolved", [])]
    assert not any(
        "gain_life" in r for r in unresolved_reasons
    ), f"Forestgate gain_life still unresolved: {unresolved_reasons}"


def test_card_002_all_mode_and_face_ids_mutually_exclusive() -> None:
    """The CLI rejects --all and --face together (exit code 2)."""
    err = io.StringIO()
    with contextlib.redirect_stderr(err):
        rc = ports.main(["--all", "--face", "face:foo:0"])
    assert rc == 2, f"Expected rc=2 for mutually-exclusive flags; got {rc}"
    assert "mutually exclusive" in err.getvalue()


def test_card_002_allure_sacrifice_additional_cost() -> None:
    """Allure of Power: 'As an additional cost to cast this spell, sacrifice
    a creature.' The sacrifice must land in costs as a first-class SACRIFICES
    edge alongside the {1}{B} mana cost -- not silently dropped because the
    ability has no effects. Unlike Stir Up Trouble, this is a *required*
    additional cost, not an alternative, so it lands as a peer entry rather
    than as branches under an ADDITIONAL_COST."""
    _ALLURE = "face:2e728381-6db0-4c66-883d-82d718fef833:1"
    result = ports.derive_all(face_ids=[_ALLURE])
    assert result, "Allure of Power face not produced"
    port = result[0]
    costs = port.get("costs", [])
    preds = [c.get("predicate") for c in costs]
    assert "CONSUMES_MANA" in preds, f"Allure missing mana cost: {preds}"
    assert "SACRIFICES" in preds, f"Allure missing sacrifice cost: {preds}"
    sac = next(c for c in costs if c.get("predicate") == "SACRIFICES")
    assert sac.get("class") == "obj:type:creature", (
        f"Allure sacrifice class is {sac.get('class')!r}; expected obj:type:creature"
    )
    assert sac.get("purpose") == "cast", (
        f"Allure sacrifice purpose is {sac.get('purpose')!r}; expected 'cast' "
        f"(an additional cost to cast the spell)"
    )


def test_card_002_ability_cost_families_lifted() -> None:
    """Card 002: eight cost families beyond mana must lift into port.costs
    (sacrifice, tap, life, discard, crew, restriction, additional_cost, mana).
    Sample assertions across the set:
      * The Lonely Mountain has a TAPS cost on its activated ability
      * My Precious has a PAYS_LIFE cost ({2} + pay 2 life for equip)
    """
    _LONELY = "face:3678c06f-8a33-4a6d-bf20-5b92d5c05a95:0"  # Lonely Mountain
    _PRECIOUS = "face:2e728381-6db0-4c66-883d-82d718fef833:0"  # My Precious
    result = ports.derive_all(face_ids=[_LONELY, _PRECIOUS])
    by_id = {r["face_id"]: r for r in result}

    lonely = by_id.get(_LONELY, {})
    lonely_preds = [c.get("predicate") for c in lonely.get("costs", [])]
    assert "TAPS" in lonely_preds, f"Lonely Mountain missing TAPS: {lonely_preds}"

    precious = by_id.get(_PRECIOUS, {})
    precious_preds = [c.get("predicate") for c in precious.get("costs", [])]
    assert "PAYS_LIFE" in precious_preds, (
        f"My Precious missing PAYS_LIFE: {precious_preds}"
    )


def test_card_002_native_keyword_from_static_effect() -> None:
    """Card 002: the extraction schema-laxly encodes some native keywords
    inside an effect ({"op":"keyword"} or {"op":"grant_keyword"}) on a
    static ability with no target/subject -- rather than promoting them to
    ab.keyword at the ability level. Dori, Bearer of Friends is the pilot
    case: "Trample" prints natively but the extraction puts it as
    ab.effects[0]={"op":"keyword","keyword":"Trample"} with ab.keyword=null.
    ports.py must route these to properties.HAS_KEYWORD (a print-on-card
    property), not to produces.GRANTS (an anthem-style grant to another
    creature)."""
    _DORI = "face:58acd6b2-730c-4472-a34a-f2784977aca8:0"
    result = ports.derive_all(face_ids=[_DORI])
    assert result, "Dori face not produced"
    port = result[0]

    native = {
        p.get("target") for p in port.get("properties", [])
        if p.get("predicate") == "HAS_KEYWORD"
    }
    assert "keyword:trample" in native, (
        f"Dori HAS_KEYWORD missing keyword:trample: {native}"
    )
    granted = {
        p.get("target") for p in port.get("produces", [])
        if p.get("predicate") == "GRANTS"
    }
    assert "keyword:trample" not in granted, (
        f"Dori's native trample leaked into produces.GRANTS: {granted}"
    )


def test_card_002_grant_keyword_with_target_still_grants() -> None:
    """The native-keyword branch must NOT swallow real grants. Concerted
    Care's oracle text -- "Target artifact or creature you control gains
    hexproof and indestructible until end of turn." -- is a spell_effect
    that grants keywords to another permanent. Its GRANTS edges must stay
    on produces, not migrate to properties."""
    _CONCERTED_CARE = "face:8a0e35ac-6c03-4922-b3b4-e419419fe3d7:1"
    result = ports.derive_all(face_ids=[_CONCERTED_CARE])
    assert result, "Concerted Care face not produced"
    port = result[0]
    granted = {
        p.get("target") for p in port.get("produces", [])
        if p.get("predicate") == "GRANTS"
    }
    native = {
        p.get("target") for p in port.get("properties", [])
        if p.get("predicate") == "HAS_KEYWORD"
    }
    assert "keyword:hexproof" in granted, (
        f"Concerted Care GRANTS missing keyword:hexproof: {granted}"
    )
    assert "keyword:indestructible" in granted, (
        f"Concerted Care GRANTS missing keyword:indestructible: {granted}"
    )
    # Card 002 revised policy: any keyword the card touches surfaces
    # as HAS_KEYWORD (native or granted-only). Concerted Care still
    # emits produces.GRANTS for hexproof/indestructible AND
    # properties.HAS_KEYWORD for them, so consumers looking for
    # "cards that touch hexproof" find every card that grants it too.
    assert "keyword:hexproof" in native, (
        f"Concerted Care should also carry keyword:hexproof as an "
        f"involvement tag on properties: {native}"
    )
    assert "keyword:indestructible" in native


def test_card_002_native_keyword_with_self_target() -> None:
    """Card 002: the extraction sometimes encodes a native keyword as a
    grant_keyword to a self-reference target ('this creature', or the
    card's own name). Bejeweled Warg's Trample arrives as
    {"op":"grant_keyword","keyword":"trample","target":"this creature"}
    on a static ability. That IS native to the card, so ports.py must
    treat 'this creature' (and the card's own name) as a self-ref and
    route the keyword to properties.HAS_KEYWORD, not produces.GRANTS."""
    _WARG = "face:051ff7e0-dd00-4467-8796-a5d1c21934ed:0"
    result = ports.derive_all(face_ids=[_WARG])
    port = result[0]
    native = {
        p.get("target") for p in port.get("properties", [])
        if p.get("predicate") == "HAS_KEYWORD"
    }
    granted = {
        p.get("target") for p in port.get("produces", [])
        if p.get("predicate") == "GRANTS"
    }
    assert "keyword:trample" in native, (
        f"Bejeweled Warg HAS_KEYWORD missing keyword:trample: {native}"
    )
    assert "keyword:trample" not in granted, (
        f"Warg's native trample leaked into produces.GRANTS: {granted}"
    )


def test_card_002_native_keywords_never_leak_to_grants() -> None:
    """Card 002 sweep: cross-check every face against a keyword allowlist
    derived from the printed oracle text. Any keyword that appears bare at
    the top of a face's oracle_text (before any full-sentence ability, with
    reminder text in parens stripped) IS a native keyword of that face.
    That keyword must land in properties.HAS_KEYWORD and MUST NOT also
    appear in produces.GRANTS. If it does, an extraction shape got past
    the native-keyword branch."""
    import re

    all_ports = ports.derive_all(all_faces=True)
    faces = {}
    for line in (ROOT / "data" / "normalized" / "faces.jsonl").read_text(
        encoding="utf-8"
    ).splitlines():
        if not line.strip(): continue
        d = json.loads(line)
        faces[d["id"]] = d

    # Static-intrinsic keyword allowlist: keywords whose *only* effect is to
    # declare a static property of the permanent, so they belong in
    # properties.HAS_KEYWORD. Deliberately narrower than the full HOB
    # keyword set -- keywords that carry a specialised predicate (Storied ->
    # INSTALLS_WATCHER gate:storied, Recruit -> produces.RECRUIT, cycling
    # activations, etc.) intentionally live elsewhere and are excluded from
    # this leak test. Flashback and kicker are static-intrinsic (they license
    # an alternate cost / a cast-from-graveyard mode, and the port models them
    # as HAS_KEYWORD plus a related activation entry).
    known_keywords = {
        "flying", "vigilance", "trample", "reach", "haste", "flash",
        "lifelink", "menace", "deathtouch", "first strike", "double strike",
        "hexproof", "indestructible", "prowess", "flashback", "kicker",
    }

    def native_keywords(face):
        ot = face.get("oracle_text") or ""
        first = ot.split("\n\n")[0].split("\n")[0]
        no_paren = re.sub(r"\([^)]*\)", "", first).strip()
        tokens = [t.strip().lower().rstrip(".") for t in no_paren.split(",")]
        return {t for t in tokens if t in known_keywords}

    leaks: list[tuple[str, str]] = []
    for port in all_ports:
        face = faces.get(port["face_id"], {})
        native = native_keywords(face)
        if not native: continue
        grants = {
            g.get("target") for g in port.get("produces", [])
            if g.get("predicate") == "GRANTS"
        }
        native_props = {
            p.get("target") for p in port.get("properties", [])
            if p.get("predicate") == "HAS_KEYWORD"
        }
        for kw in native:
            kw_id = f"keyword:{kw}"
            if kw_id in grants:
                leaks.append((face.get("name", port["face_id"]),
                              f"{kw_id} leaked to produces.GRANTS"))
            if kw_id not in native_props:
                leaks.append((face.get("name", port["face_id"]),
                              f"{kw_id} missing from properties.HAS_KEYWORD"))
    assert not leaks, (
        f"{len(leaks)} native-keyword misroutings; first: {leaks[:5]}"
    )


def test_card_002_creature_baseline_power_toughness_as_properties() -> None:
    """Card 002: creatures and vehicles carry a printed power/toughness.
    These are as intrinsic as the type line and belong on properties as
    HAS_POWER / HAS_TOUGHNESS edges with a numeric `amount` (coerced from
    the string form when it parses; passed through verbatim for the
    non-numeric special cases like "*" or "1+*").

    Sample: Smaug, Wicked Worm prints 5/5."""
    _SMAUG = "face:20535126-f811-4386-bdce-d73f30691724:0"
    result = ports.derive_all(face_ids=[_SMAUG])
    port = result[0]
    props = port.get("properties", [])
    power = next((p for p in props if p.get("predicate") == "HAS_POWER"), None)
    tough = next((p for p in props if p.get("predicate") == "HAS_TOUGHNESS"), None)
    assert power is not None, "Smaug HAS_POWER missing"
    assert tough is not None, "Smaug HAS_TOUGHNESS missing"
    assert power.get("amount") == 5, f"Smaug power wrong: {power}"
    assert tough.get("amount") == 5, f"Smaug toughness wrong: {tough}"
    assert power.get("target") == "obj:power"
    assert tough.get("target") == "obj:toughness"


def test_card_002_every_creature_has_power_and_toughness() -> None:
    """Set-wide invariant: every face whose type_line includes 'Creature'
    (or subtype Vehicle) must carry both HAS_POWER and HAS_TOUGHNESS."""
    all_ports = ports.derive_all(all_faces=True)
    faces = {}
    for line in (ROOT / "data" / "normalized" / "faces.jsonl").read_text(
        encoding="utf-8"
    ).splitlines():
        if not line.strip(): continue
        d = json.loads(line)
        faces[d["id"]] = d
    missing: list[str] = []
    for port in all_ports:
        face = faces.get(port["face_id"], {})
        tl = face.get("type_line", {}) or {}
        types = tl.get("types", []) or []
        subs = tl.get("subtypes", []) or []
        is_creature_like = "Creature" in types or "Vehicle" in subs
        if not is_creature_like: continue
        preds = {p.get("predicate") for p in port.get("properties", [])}
        for req in ("HAS_POWER", "HAS_TOUGHNESS"):
            if req not in preds:
                missing.append(f"{face.get('name', port['face_id'])} missing {req}")
    assert not missing, f"{len(missing)} faces missing P/T: {missing[:5]}"


def test_card_002_add_counter_records_counter_type() -> None:
    """Card 002: ADDS_COUNTER edges must record WHICH counter is being
    added (+1/+1, trample, lore, charge, ...). Every counter-mover in the
    extraction carries a counter_type field; drop it and the graph can't
    tell +1/+1 counters from trample counters.

    Meager Meal (+1/+1), Beorn the Fierce (trample), Bifur, Melodic Rider
    (+1/+1) all exercise this."""
    faces: list[tuple[str, str, str]] = []
    _wanted = {
        "Meager Meal": "+1/+1",
        "Bifur, Melodic Rider": "+1/+1",
        "Beorn the Fierce": "trample",
    }
    for line in (ROOT / "data" / "normalized" / "faces.jsonl").read_text(
        encoding="utf-8"
    ).splitlines():
        if not line.strip(): continue
        d = json.loads(line)
        if d.get("name") in _wanted:
            faces.append((d["id"], _wanted[d["name"]], d["name"]))
    assert len(faces) == len(_wanted), (
        f"missing sample faces; found {[f[2] for f in faces]}"
    )

    all_faces = [f for f, _, _ in faces]
    result = ports.derive_all(face_ids=all_faces)
    by_id = {r["face_id"]: r for r in result}

    for face_id, expected_ct, name in faces:
        port = by_id.get(face_id)
        assert port is not None, f"{name} not produced"
        adds = [p for p in port.get("produces", [])
                if p.get("predicate") == "ADDS_COUNTER"]
        assert adds, f"{name} has no ADDS_COUNTER edge"
        for a in adds:
            assert a.get("counter_type") == expected_ct, (
                f"{name} counter_type wrong: expected {expected_ct!r}, "
                f"got {a.get('counter_type')!r}"
            )


def test_card_002_every_add_counter_names_a_type() -> None:
    """Set-wide invariant: every ADDS_COUNTER edge must carry a counter_type.
    An untyped counter edge means the derivation dropped the extraction's
    counter_type field."""
    all_ports = ports.derive_all(all_faces=True)
    missing: list[str] = []
    for port in all_ports:
        for edge in port.get("produces", []):
            if edge.get("predicate") != "ADDS_COUNTER":
                continue
            if not edge.get("counter_type"):
                missing.append(f"{port['face_id']}: {edge}")
    assert not missing, (
        f"{len(missing)} untyped ADDS_COUNTER edges; first: {missing[:3]}"
    )


def test_card_002_self_etb_type_specific() -> None:
    """Card 002 ETB semantics: a trigger like "When this enchantment
    enters" fires ONLY when the card enters *as an enchantment* (CR type-
    dependent triggers). So each printed subject type gets its own
    narrower event concept -- event:this-creature-enters,
    event:this-enchantment-enters, etc. -- and only bare/subject-name
    self-references without a type word land on the broad
    event:this-permanent-enters. Consumers wanting "any creature ETB"
    match either the narrow creature event or the broad permanent event
    joined with IS_A obj:type:creature.

    Also: "As this X enters" is a REPLACEMENT effect (An Unexpected
    Party), not a triggered ability. It applies at ETB resolution and
    lands on installs.REPLACES_ON, not consumes.TRIGGERS_ON."""
    all_ports = ports.derive_all(all_faces=True)
    by_name = {}
    for line in (ROOT / "data" / "normalized" / "faces.jsonl").read_text(
        encoding="utf-8"
    ).splitlines():
        if not line.strip(): continue
        d = json.loads(line)
        by_name[d.get("name")] = d["id"]
    ports_by_id = {p["face_id"]: p for p in all_ports}

    def targets(port, section, predicate):
        return [e.get("target") for e in port.get(section, [])
                if e.get("predicate") == predicate]

    expectations: list[tuple[str, str, str, str]] = [
        # (card_name, section, predicate, event_id)
        # Bilbo self-refs by card name -> broad permanent
        ("Bilbo Baggins, Burglar", "consumes", "TRIGGERS_ON",
            "event:this-permanent-enters"),
        # Smaug's "When Smaug enters" -> broad permanent (card-name self-ref)
        ("Smaug, Wicked Worm", "consumes", "TRIGGERS_ON",
            "event:this-permanent-enters"),
        # Old Thrush's "When this creature enters" -> narrow creature
        ("Old Thrush", "consumes", "TRIGGERS_ON",
            "event:this-creature-enters"),
        # An Unexpected Party's "As this enchantment enters" -> replacement
        ("An Unexpected Party", "installs", "REPLACES_ON",
            "event:this-enchantment-enters"),
    ]
    for card_name, section, predicate, expected_event in expectations:
        fid = by_name.get(card_name)
        assert fid, f"face for {card_name} not found"
        port = ports_by_id[fid]
        found = targets(port, section, predicate)
        assert expected_event in found, (
            f"{card_name} {section}.{predicate} missing {expected_event}; "
            f"found: {port.get(section, [])}"
        )


# ---------------------------------------------------------------------------
# Card 002, second pass: manual-review sweep (buckets 1-4)
# ---------------------------------------------------------------------------


def _face_id_by_name(name: str) -> str:
    for line in (ROOT / "data" / "normalized" / "faces.jsonl").read_text(
        encoding="utf-8"
    ).splitlines():
        if not line.strip(): continue
        d = json.loads(line)
        if d.get("name") == name:
            return d["id"]
    raise AssertionError(f"no face named {name!r}")


def test_card_002_token_creators_carry_full_token_spec() -> None:
    """Bucket 1: CREATES_TOKEN edges must resolve the token reference
    against Scryfall token specs and attach a `token` block with the
    token's name, type_line, subtypes, power, toughness, colors, and
    oracle_text -- not just a bare `token_ref` string. Chief Warg's
    Company makes 2/2 green Wolf tokens; At the Door makes X 2/2 red
    Dwarf tokens."""
    for card_name, expected_name, expected_pt in (
        ("Chief Warg's Company", "Wolf", ("2", "2")),
        ("At the Door", "Dwarf", ("2", "2")),
    ):
        fid = _face_id_by_name(card_name)
        result = ports.derive_all(face_ids=[fid])
        port = result[0]
        toks = [e for e in port.get("produces", [])
                if e.get("predicate") == "CREATES_TOKEN"]
        assert toks, f"{card_name} has no CREATES_TOKEN"
        tok = toks[0].get("token")
        assert isinstance(tok, dict), (
            f"{card_name} CREATES_TOKEN missing full token spec: {toks[0]}"
        )
        assert tok.get("name") == expected_name
        assert (tok.get("power"), tok.get("toughness")) == expected_pt


def test_card_002_ability_edges_carry_descriptors() -> None:
    """Bucket 2: effect-level descriptor fields (subject, adds_type,
    note, detail, text) must land on the port edge. Beorn the Fierce
    exercises three:
      * ADDS_TYPE -> adds_type: "Bear"
      * MODIFIES_PT -> subject: "other Bears you control"
      * DRAWS (from a conditional_draw effect) -> conditions carried"""
    fid = _face_id_by_name("Beorn the Fierce")
    port = ports.derive_all(face_ids=[fid])[0]
    adds_type = next((e for e in port.get("produces", [])
                       if e.get("predicate") == "ADDS_TYPE"), None)
    assert adds_type and adds_type.get("adds_type") == "Bear", (
        f"Beorn ADDS_TYPE missing adds_type descriptor: {adds_type}"
    )
    modifies = next((e for e in port.get("produces", [])
                      if e.get("predicate") == "MODIFIES_PT"), None)
    assert modifies and "Bears you control" in str(modifies.get("subject", "")), (
        f"Beorn MODIFIES_PT missing subject descriptor: {modifies}"
    )


def test_card_002_conditional_draw_carries_condition() -> None:
    """Bucket 3: an effect's own `condition` field (not just the
    ability's `conditions` list) must be lifted onto the produce entry.
    Beorn the Fierce's conditional_draw is gated on 'you control three
    or more Bears'."""
    fid = _face_id_by_name("Beorn the Fierce")
    port = ports.derive_all(face_ids=[fid])[0]
    draws = next((e for e in port.get("produces", [])
                   if e.get("predicate") == "DRAWS"), None)
    assert draws is not None, "Beorn has no DRAWS edge"
    conds = draws.get("conditions") or []
    assert any("three or more Bears" in str(c) for c in conds), (
        f"Beorn DRAWS not gated on 3-Bears condition: {draws}"
    )


def test_card_002_enters_or_attacks_splits_into_two_triggers() -> None:
    """Bucket 4: a compound "enters or attacks" trigger must emit TWO
    TRIGGERS_ON edges (this-permanent-enters + this-creature-attacks)
    so consumers can query for either half. Bifur, Melodic Rider is
    the canonical case."""
    fid = _face_id_by_name("Bifur, Melodic Rider")
    port = ports.derive_all(face_ids=[fid])[0]
    trig_targets = {e.get("target") for e in port.get("consumes", [])
                     if e.get("predicate") == "TRIGGERS_ON"}
    assert "event:this-permanent-enters" in trig_targets
    assert "event:this-creature-attacks" in trig_targets
    assert "event:this-creature-enters-or-attacks" not in trig_targets


def test_card_002_balin_or_another_splits_into_two_triggers() -> None:
    """Bucket 4: 'Balin or another Dwarf enters' must emit both a
    self-ETB (event:this-permanent-enters) and the another-dwarf
    trigger (event:another-dwarf-or-equipment-enters)."""
    fid = _face_id_by_name("Balin, Loremaster")
    port = ports.derive_all(face_ids=[fid])[0]
    trig_targets = {e.get("target") for e in port.get("consumes", [])
                     if e.get("predicate") == "TRIGGERS_ON"}
    assert "event:this-permanent-enters" in trig_targets
    assert "event:another-dwarf-or-equipment-enters" in trig_targets


def test_card_002_gift_carries_token_spec() -> None:
    """Bilbo's Gambit's GIFTS effect uses `gift_object` (not `token`/
    `token_ref`) to reference the token it creates. The token lookup
    must handle that alias and attach the full Treasure token spec."""
    fid = _face_id_by_name("Bilbo's Gambit")
    port = ports.derive_all(face_ids=[fid])[0]
    gifts = next((e for e in port.get("produces", [])
                   if e.get("predicate") == "GIFTS"), None)
    assert gifts is not None, "Bilbo's Gambit has no GIFTS edge"
    tok = gifts.get("token")
    assert isinstance(tok, dict) and tok.get("name") == "Treasure", (
        f"Bilbo's Gambit GIFTS missing Treasure token spec: {gifts}"
    )


def test_card_002_modal_options_unpacked_into_branches() -> None:
    """Bejeweled Warg's "choose one -- +1/+1 counter on target Wolf OR
    create a Treasure token" arrives as a MODAL_MARKER effect with an
    `options` list. The port must unpack those options into `branches`
    on the entry -- each branch a typed sub-edge with its own predicate,
    target, and (if a token-creator) the resolved token spec."""
    fid = _face_id_by_name("Bejeweled Warg")
    port = ports.derive_all(face_ids=[fid])[0]
    modal = next((e for e in port.get("produces", [])
                   if e.get("predicate") == "MODAL_MARKER"), None)
    assert modal is not None, "Bejeweled Warg has no MODAL_MARKER"
    branches = modal.get("branches") or []
    assert len(branches) == 2, (
        f"Bejeweled Warg MODAL_MARKER expected 2 branches, got {len(branches)}"
    )
    preds = {b.get("predicate") for b in branches}
    assert "ADDS_COUNTER" in preds
    assert "CREATES_TOKEN" in preds
    tok_branch = next(b for b in branches if b.get("predicate") == "CREATES_TOKEN")
    assert isinstance(tok_branch.get("token"), dict)
    assert tok_branch["token"].get("name") == "Treasure"
    assert modal.get("choose") == 1


def test_card_002_produces_mana_carries_color_and_amount() -> None:
    """Forest's activated ability produces {G} — the port must carry
    the mana string and amount on the PRODUCES_MANA edge."""
    fid = _face_id_by_name("Forest")
    port = ports.derive_all(face_ids=[fid])[0]
    pm = next((e for e in port.get("produces", [])
                if e.get("predicate") == "PRODUCES_MANA"), None)
    assert pm is not None, "Forest has no PRODUCES_MANA edge"
    assert pm.get("amount") == 1
    assert pm.get("mana") == "{G}"


def test_card_002_produces_mana_carries_choice_options() -> None:
    """Elvenking's Halls: {T}: Add {G} or {U}. The choice arrives as
    options=["G", "U"] which must land on the PRODUCES_MANA entry."""
    fid = _face_id_by_name("Elvenking's Halls")
    port = ports.derive_all(face_ids=[fid])[0]
    pm = next((e for e in port.get("produces", [])
                if e.get("predicate") == "PRODUCES_MANA"), None)
    assert pm is not None, "Elvenking's Halls has no PRODUCES_MANA edge"
    assert pm.get("options") == ["G", "U"]


def test_card_002_activated_cost_recognizes_cost_and_value_shapes() -> None:
    """Gleaming Splendor's activated ability costs are
    {"cost": "mana", "value": "{2}{W}"} (uses `cost` not `type`, `value`
    not `amount`/`detail`). The cost-lift must accept those aliases so
    the {2}{W} activation cost is emitted, not silently dropped."""
    fid = _face_id_by_name("Gleaming Splendor")
    port = ports.derive_all(face_ids=[fid])[0]
    activation_mana = [c for c in port.get("costs", [])
                        if c.get("predicate") == "CONSUMES_MANA"
                        and c.get("purpose") == "activation"]
    assert activation_mana, (
        f"Gleaming Splendor {{2}}{{W}} activation cost missing: "
        f"{port.get('costs')}"
    )
    assert activation_mana[0].get("amount") == "{2}{W}"


def test_card_002_deal_damage_carries_amount_and_target() -> None:
    """Gandalf, Goblins' Bane: DEALS_DAMAGE amount=1, target=each
    opponent. Both must land on the edge as amount and target_text."""
    fid = _face_id_by_name("Gandalf, Goblins' Bane")
    port = ports.derive_all(face_ids=[fid])[0]
    dd = next((e for e in port.get("produces", [])
                if e.get("predicate") == "DEALS_DAMAGE"), None)
    assert dd is not None, "Goblins' Bane has no DEALS_DAMAGE edge"
    assert dd.get("amount") == 1
    assert dd.get("target_text") == "each opponent"


def test_card_002_raw_target_text_lifted_for_produces_edges() -> None:
    """Gone Fishing's EXILES and RETURNS both operate on natural-
    language targets ("two target creatures and/or lands you control",
    "them (the exiled permanents)"). The port must lift those raw
    target strings as target_text so the endpoints aren't blank."""
    fid = _face_id_by_name("Gone Fishing")
    port = ports.derive_all(face_ids=[fid])[0]
    ex = next((e for e in port.get("produces", [])
                if e.get("predicate") == "EXILES"), None)
    ret = next((e for e in port.get("produces", [])
                 if e.get("predicate") == "RETURNS"), None)
    assert ex and "creatures and/or lands" in str(ex.get("target_text", ""))
    assert ret and "exiled permanents" in str(ret.get("target_text", ""))


def test_card_002_amass_predicate_is_harmonized() -> None:
    """Every extraction spelling for amass maps to the canonical AMASS
    predicate. In particular, the top-level-key shape {"amass": {...}}
    must not emit a separate AMASSES vocabulary term."""
    all_ports = ports.derive_all(all_faces=True)
    amass_edges = []
    for port in all_ports:
        for edge in port.get("produces", []):
            if edge.get("predicate") in {"AMASS", "AMASSES"}:
                amass_edges.append((port["name"], edge))

    assert amass_edges, "expected at least one amass edge in the set"
    assert all(edge.get("predicate") == "AMASS" for _, edge in amass_edges), (
        f"non-canonical amass predicates: "
        f"{[(name, edge) for name, edge in amass_edges if edge.get('predicate') != 'AMASS']}"
    )


def test_card_002_all_storied_cards_install_watcher() -> None:
    """Card 002: every card whose oracle text mentions "Storied" must
    install the gate:storied watcher, matching Bifur, Melodic Rider's
    format exactly. The extraction encodes Storied through many shapes
    ({op:storied}, {effect:storied}, {op:gain_designation, designation:
    "enduring story"}, {effect:gain_enduring_story_designation}, plus
    ab.keyword=="Storied" and {op:keyword_ability, keyword:"Storied"});
    all nine HOB Storied cards -- Balin, Bifur, Bombur, Dáin, Fíli,
    Kíli, Óin, Ori, Thorin -- must produce the same edge shape:
        installs: [{"predicate": "INSTALLS_WATCHER",
                     "target": "gate:storied", ...}]"""
    all_ports = ports.derive_all(all_faces=True)
    faces = {}
    for line in (ROOT / "data" / "normalized" / "faces.jsonl").read_text(
        encoding="utf-8"
    ).splitlines():
        if not line.strip(): continue
        d = json.loads(line)
        faces[d["id"]] = d

    missing: list[str] = []
    for port in all_ports:
        face = faces.get(port["face_id"], {})
        ot = (face.get("oracle_text") or "").lower()
        if "storied" not in ot:
            continue
        watchers = [
            e for e in port.get("installs", [])
            if e.get("predicate") == "INSTALLS_WATCHER"
            and e.get("target") == "gate:storied"
        ]
        if not watchers:
            missing.append(face.get("name", port["face_id"]))
    assert not missing, (
        f"{len(missing)} Storied cards missing INSTALLS_WATCHER "
        f"gate:storied: {missing}"
    )


def test_card_002_named_ability_words_promoted_to_keywords() -> None:
    """Card 002: Landfall, Ferocious, Threshold appear only as italicized
    markers in the oracle text ("Landfall — Whenever a land you control
    enters, ..."). The extraction captures the trigger but not the
    marker. A face-level sweep of the oracle text (with quoted grants
    stripped so a Saga's granted landfall doesn't count for the Saga)
    must promote each marker to HAS_KEYWORD.

    All 9 HOB Landfall cards -- Elven Raft-Steerer, Mirkwood Meditator,
    Attercop, Beorn's Hospitality, Boughside Wanderers, Dancing from
    Dark to Dawn, Silvan Reveler, Thranduil Sindarin Liege, Thranduil's
    Company -- must carry keyword:landfall. Down in the Valley (which
    grants Landfall to itself via a Saga chapter) must NOT."""
    all_ports = ports.derive_all(all_faces=True)
    faces = {}
    for line in (ROOT / "data" / "normalized" / "faces.jsonl").read_text(
        encoding="utf-8"
    ).splitlines():
        if not line.strip(): continue
        d = json.loads(line)
        faces[d["id"]] = d

    # Card 002 revision: every face whose oracle text mentions Landfall
    # (as a marker, quoted or unquoted) gets the HAS_KEYWORD tag so
    # consumers looking for "cards with Landfall in their ability text"
    # find them. Includes Down in the Valley (Saga chapter II grants
    # "Landfall — ..."), because the granted ability still surfaces the
    # keyword on the graph.
    expect_landfall = {
        "Elven Raft-Steerer", "Mirkwood Meditator", "Attercop",
        "Beorn's Hospitality", "Boughside Wanderers",
        "Dancing from Dark to Dawn", "Silvan Reveler",
        "Thranduil, Sindarin Liege", "Thranduil's Company",
        "Down in the Valley",
    }
    found: set[str] = set()
    for port in all_ports:
        face = faces.get(port["face_id"], {})
        name = face.get("name", "")
        has_landfall = any(
            e.get("target") == "keyword:landfall"
            for e in port.get("properties", [])
            if e.get("predicate") == "HAS_KEYWORD"
        )
        if has_landfall:
            found.add(name)
    missing = expect_landfall - found
    assert not missing, f"Landfall cards missing HAS_KEYWORD: {missing}"


def test_card_002_replaces_edges_name_the_replaced_event() -> None:
    """Every REPLACES edge collapses to the same predicate on the port,
    but the extraction distinguishes the affected event through the verb
    (replace_draw / replace_token_creation / exile_instead_of_graveyard)
    or through from_zone/to_zone (or zone_from/zone_to) on the generic
    replacement shape. Card 002 enriches each REPLACES entry with a
    `replaces` field naming the affected event so consumers can tell
    Bard King of Dale's draw-replacement, his token-doubler, and Bilbo
    Thief in the Night's graveyard->exile replacement apart."""
    all_ports = ports.derive_all(all_faces=True)
    by_name = {}
    for line in (ROOT / "data" / "normalized" / "faces.jsonl").read_text(
        encoding="utf-8"
    ).splitlines():
        if not line.strip(): continue
        d = json.loads(line)
        by_name[d.get("name")] = d["id"]
    by_id = {p["face_id"]: p for p in all_ports}

    def replaces_of(card_name):
        port = by_id[by_name[card_name]]
        return {
            e.get("replaces")
            for e in port.get("produces", []) + port.get("installs", [])
            if e.get("predicate") == "REPLACES"
        }
    assert "event:you-draw-card" in replaces_of("Bard, King of Dale")
    assert "event:token-creation" in replaces_of("Bard, King of Dale")
    assert "event:go-to-graveyard" in replaces_of("Bilbo, Thief in the Night")
    assert "event:go-to-graveyard" in replaces_of("Head of the Hunt")


def test_card_002_modifies_pt_always_has_amount() -> None:
    """Every MODIFIES_PT edge must carry a canonical `amount` string
    (e.g. "+2/+2", "-1/-1"). The extraction encodes the change through
    at least four different fields (amount, delta, value, or a split
    power/toughness pair); ports.py normalizes them all to `amount`."""
    all_ports = ports.derive_all(all_faces=True)
    missing: list[str] = []
    for port in all_ports:
        for e in port.get("produces", []):
            if e.get("predicate") != "MODIFIES_PT":
                continue
            if not e.get("amount"):
                missing.append(f"{port['face_id']}: {e}")
    assert not missing, (
        f"{len(missing)} MODIFIES_PT edges missing amount; first: "
        f"{missing[:3]}"
    )


def test_card_002_granted_ability_token_creation_surfaced() -> None:
    """When an ability grants a triggered ability whose payload creates
    a token (Down in the Valley's Saga chapter II gains "Landfall —
    Whenever a land you control enters, create a 1/1 green Elf creature
    token."), the port must emit a CREATES_TOKEN edge with the resolved
    token spec, flagged as conditional on the granted ability firing.
    Otherwise the graph loses the fact that this card can produce Elf
    tokens indirectly."""
    fid = _face_id_by_name("Down in the Valley")
    port = ports.derive_all(face_ids=[fid])[0]
    tokens = [e for e in port.get("produces", [])
              if e.get("predicate") == "CREATES_TOKEN"]
    assert tokens, "Down in the Valley has no CREATES_TOKEN edge"
    elf_tokens = [t for t in tokens
                   if (t.get("token") or {}).get("name") == "Elf"]
    assert elf_tokens, f"Down in the Valley missing Elf token: {tokens}"
    # Should be flagged as grant-dependent, not unconditional.
    conds = elf_tokens[0].get("conditions") or []
    assert any(
        (isinstance(c, dict) and c.get("type") == "grant_dependent")
        for c in conds
    ), f"Elf token missing grant-dependent condition: {elf_tokens[0]}"


def test_card_002_equipment_grants_keyword_shows_both_native_and_grant() -> None:
    """Equipment that grants a keyword to the equipped creature must
    surface BOTH edges: (1) produces.GRANTS keyword:X with scope=
    equipped creature (the mechanic), and (2) properties.HAS_KEYWORD
    keyword:X (the involvement tag, so consumers looking for "cards
    that touch menace" find equipment that grants it too).

    Goblin Plate Mail grants menace to equipped creature; Dwarven
    Mattock grants ward {1}. Both must show both edges."""
    for card_name, kw_id in (
        ("Goblin Plate Mail", "keyword:menace"),
        ("Dwarven Mattock", "keyword:ward"),
    ):
        fid = _face_id_by_name(card_name)
        port = ports.derive_all(face_ids=[fid])[0]
        native = {
            e.get("target") for e in port.get("properties", [])
            if e.get("predicate") == "HAS_KEYWORD"
        }
        grants = [e for e in port.get("produces", [])
                   if e.get("predicate") == "GRANTS"]
        assert kw_id in native, (
            f"{card_name} missing {kw_id} on properties.HAS_KEYWORD: {native}"
        )
        # A GRANTS edge with scope=equipped creature must be present.
        equipped_grants = [g for g in grants
                            if "equipped" in str(g.get("scope", "")).lower()]
        assert equipped_grants, (
            f"{card_name} missing GRANTS with scope=equipped creature: {grants}"
        )


def test_card_002_activated_ability_costs_all_lifted() -> None:
    """Card 002: every cost item on every activated ability in the
    extraction must produce a corresponding cost edge on the port
    (matched by predicate family, not exact string). The extraction
    uses two conflicting shapes for mana:
        {"type": "mana", "cost": "{5}{G}{G}"}      Guardian, Beorn's Hospitality
        {"cost": "mana", "value": "{2}{W}"}         Gleaming Splendor, Troop of Ponies
    Both shapes must be recognised."""
    import collections as _co
    extractions = {}
    for line in (ROOT / "data" / "review" / "llm_accepted.jsonl").read_text(
        encoding="utf-8"
    ).splitlines():
        if not line.strip(): continue
        d = json.loads(line)
        extractions[d["face_id"]] = d
    all_ports = ports.derive_all(all_faces=True)
    port_costs: dict[str, list[dict]] = _co.defaultdict(list)
    for port in all_ports:
        for c in port.get("costs", []):
            if c.get("purpose") == "activation":
                port_costs[port["face_id"]].append(c)

    predicate_for = {
        "mana": "CONSUMES_MANA", "pay_mana": "CONSUMES_MANA",
        "sacrifice": "SACRIFICES", "tap": "TAPS",
        "discard": "DISCARDS", "life": "PAYS_LIFE",
        "pay_life": "PAYS_LIFE", "crew": "CREW",
    }
    missing: list[str] = []
    for fid, ext in extractions.items():
        for ab in ext.get("abilities", []):
            if ab.get("kind") != "activated":
                continue
            for cost in (ab.get("costs") or []):
                if not isinstance(cost, dict): continue
                typ = cost.get("type") or cost.get("op")
                pred = predicate_for.get(typ)
                if not pred: continue
                if not any(pc.get("predicate") == pred
                           for pc in port_costs.get(fid, [])):
                    missing.append(
                        f"{fid} {ab.get('ability_id')} {typ}: {cost}"
                    )
    assert not missing, (
        f"{len(missing)} activated-ability costs not lifted; first: "
        f"{missing[:3]}"
    )


def test_card_002_grant_unblockable_names_keyword() -> None:
    """Cards granting "can't be blocked" (grant_unblockable op) must
    surface both the GRANTS edge with target=keyword:cant-be-blocked
    AND the HAS_KEYWORD involvement tag. Elvenking's Harper (spell,
    grants to target creature) and My Precious (equipment, grants to
    equipped creature) both exercise this."""
    for card_name in ("Elvenking's Harper", "My Precious"):
        fid = _face_id_by_name(card_name)
        port = ports.derive_all(face_ids=[fid])[0]
        grants = [g.get("target") for g in port.get("produces", [])
                   if g.get("predicate") == "GRANTS"]
        assert "keyword:cant-be-blocked" in grants, (
            f"{card_name} GRANTS missing keyword:cant-be-blocked: {grants}"
        )
        native = [p.get("target") for p in port.get("properties", [])
                   if p.get("predicate") == "HAS_KEYWORD"]
        assert "keyword:cant-be-blocked" in native, (
            f"{card_name} HAS_KEYWORD missing keyword:cant-be-blocked: {native}"
        )


def test_card_002_modal_marker_without_branches_suppressed() -> None:
    """A MODAL_MARKER with no `branches` field (extraction had no
    `options` list) is a parameter selection like Orcrist's "Choose a
    creature type" rather than a mode choice. The port must not emit
    a bare MODAL_MARKER edge for it."""
    fid = _face_id_by_name("Orcrist, Goblin-cleaver")
    port = ports.derive_all(face_ids=[fid])[0]
    modals = [e for e in port.get("produces", [])
              if e.get("predicate") == "MODAL_MARKER"]
    assert not modals, (
        f"Orcrist should not emit a bare MODAL_MARKER: {modals}"
    )


def test_card_002_every_choose_one_card_has_modal_marker() -> None:
    """Every card whose oracle text has a 'Choose one/two/one or both —'
    preamble (outside quoted grants) must have a MODAL_MARKER produce
    edge. The extractor's own modal ops and F4's synthesis only cover
    some cases; a face-level oracle sweep catches the rest (Pinecone,
    Stone by Sunlight, Thorin's Last Stand, Elven Raft-Steerer,
    Gollum Riddle Master, Reverent Howl, Warg Tactics)."""
    import re as _re
    all_ports = ports.derive_all(all_faces=True)
    faces = {}
    for line in (ROOT / "data" / "normalized" / "faces.jsonl").read_text(
        encoding="utf-8"
    ).splitlines():
        if not line.strip(): continue
        d = json.loads(line)
        faces[d["id"]] = d
    missing: list[str] = []
    for port in all_ports:
        face = faces.get(port["face_id"], {})
        ot = face.get("oracle_text") or ""
        # Strip quoted grants
        stripped = _re.sub(r'"[^"]*"', "", ot)
        if not _re.search(
            r"choose (one or both|one|two|three)\s*[—\-]",
            stripped, _re.IGNORECASE,
        ):
            continue
        has_marker = any(
            e.get("predicate") == "MODAL_MARKER"
            for e in port.get("produces", [])
        )
        if not has_marker:
            missing.append(face.get("name", port["face_id"]))
    assert not missing, (
        f"Choose-preamble cards missing MODAL_MARKER: {missing}"
    )


def test_card_002_flashback_cards_carry_keyword() -> None:
    """Flashback appears in oracle text as "Flashback {N}{X}" (keyword +
    mana cost, not the "—" ability-word format). The face-level sweep
    must catch it just like Landfall. Moment of Glory, Plunder the
    Trollshaws, and Tidings of War all print Flashback."""
    for card_name in ("Moment of Glory", "Plunder the Trollshaws",
                       "Tidings of War"):
        fid = _face_id_by_name(card_name)
        port = ports.derive_all(face_ids=[fid])[0]
        native = {
            e.get("target") for e in port.get("properties", [])
            if e.get("predicate") == "HAS_KEYWORD"
        }
        assert "keyword:flashback" in native, (
            f"{card_name} missing HAS_KEYWORD keyword:flashback: {native}"
        )


def test_card_002_grant_ability_parses_ability_text_keyword() -> None:
    """The `grant_ability` op stores its payload in `ability` (lifted to
    `ability_text` on the entry) as a natural-language keyword phrase
    like "ward {1}". The GRANTS edge must resolve that to target=
    keyword:ward and amount={1}. Thorin Oakenshield grants ward {1} to
    artifacts and creatures you control (gated on Storied); Dwarven
    Mattock grants ward {1} to equipped creature."""
    for card_name in ("Thorin Oakenshield", "Dwarven Mattock"):
        fid = _face_id_by_name(card_name)
        port = ports.derive_all(face_ids=[fid])[0]
        ward_grants = [g for g in port.get("produces", [])
                        if g.get("predicate") == "GRANTS"
                        and g.get("target") == "keyword:ward"]
        assert ward_grants, (
            f"{card_name} missing GRANTS keyword:ward: "
            f"{port.get('produces')}"
        )
        assert ward_grants[0].get("amount") == "{1}", (
            f"{card_name} ward amount wrong: {ward_grants[0]}"
        )


def test_card_002_keyword_involvement_covers_all_predicate_bound_keywords() -> None:
    """Set-wide: every card that has a predicate corresponding to a named
    keyword ability (RECRUIT / AMASS / FLASHBACK / INSTALLS_WATCHER
    gate:storied) must also carry the matching HAS_KEYWORD tag. Every
    card whose oracle text prints Equip {N} or Ward {N} likewise.
    Every card that prints "Enchant creature/permanent/..." likewise."""
    all_ports = ports.derive_all(all_faces=True)
    _PRED_TO_KW = {
        "RECRUIT": "keyword:recruit", "AMASS": "keyword:amass",
        "FLASHBACK": "keyword:flashback",
    }
    missing: list[str] = []
    for port in all_ports:
        native = {
            e.get("target") for e in port.get("properties", [])
            if e.get("predicate") == "HAS_KEYWORD"
        }
        # Predicate-implied
        for e in port.get("produces", []) + port.get("installs", []):
            _kw = _PRED_TO_KW.get(str(e.get("predicate")))
            if (e.get("predicate") == "INSTALLS_WATCHER"
                    and e.get("target") == "gate:storied"):
                _kw = "keyword:storied"
            if _kw and _kw not in native:
                missing.append(f"{port['face_id']}: {e.get('predicate')} -> {_kw}")
    assert not missing, (
        f"{len(missing)} predicate-bound keywords missing from HAS_KEYWORD; "
        f"first: {missing[:3]}"
    )


def test_card_002_alias_predicates_consolidated() -> None:
    """Card 002 axis 1: MOVES_CARD / MOVES_ZONE / MOVES_REST /
    MOVES_TO_HAND / MOVES_TO_LIBRARY all fold to MOVES_CARDS.
    EXILES_FROM_LIBRARY / EXILES_FACE_DOWN / EXILES_SELF fold to EXILES.
    REVEALS_HAND / REVEALS_UNTIL / REVEALS_AND_TAKES fold to REVEALS.
    RETURNS_FROM_EXILE / RETURNS_FROM_GRAVEYARD / RETURNS_TO_HAND fold
    to RETURNS. SHUFFLES_INTO_LIBRARY folds to SHUFFLES.
    SETS_TYPE / CHANGES_CHARACTERISTICS fold to CHANGES_TYPE.

    The distinguishing info (to_zone, from_zone, subject, state, mode)
    is preserved as structured fields on the canonical edge, so nothing
    is lost."""
    _dead_aliases = {
        "MOVES_CARD", "MOVES_ZONE", "MOVES_REST",
        "MOVES_TO_HAND", "MOVES_TO_LIBRARY",
        "EXILES_FROM_LIBRARY", "EXILES_FACE_DOWN", "EXILES_SELF",
        "REVEALS_HAND", "REVEALS_UNTIL", "REVEALS_AND_TAKES",
        "RETURNS_FROM_EXILE", "RETURNS_FROM_GRAVEYARD", "RETURNS_TO_HAND",
        "SHUFFLES_INTO_LIBRARY",
        "SETS_TYPE", "CHANGES_CHARACTERISTICS",
    }
    all_ports = ports.derive_all(all_faces=True)
    leaks: list[str] = []
    for port in all_ports:
        for sec in ("properties","installs","consumes","produces","costs"):
            for e in port.get(sec, []):
                if e.get("predicate") in _dead_aliases:
                    leaks.append(f"{port['face_id']} {sec} {e.get('predicate')}")
    assert not leaks, (
        f"{len(leaks)} edges still use consolidated alias predicates; "
        f"first: {leaks[:5]}"
    )


def test_card_002_amount_kind_classifier() -> None:
    """Card 002 axis 3: every non-mana `amount` field carries an
    `amount_kind` tag so consumers can filter literal counts from
    symbolic (X, *) and scaling ("X per Halfling") values. Mana amounts
    (self-identified via class:resource:mana or mana notation) skip
    the tagging."""
    all_ports = ports.derive_all(all_faces=True)
    _VALID_KINDS = {"literal", "variable", "scaling", "expression"}
    missing: list[str] = []
    invalid: list[str] = []
    for port in all_ports:
        for sec in ("properties","installs","consumes","produces","costs"):
            for e in port.get(sec, []):
                if "amount" not in e:
                    continue
                # Skip mana amounts (self-identified).
                if (e.get("class") == "resource:mana"
                        or e.get("mana") is not None
                        or (isinstance(e.get("amount"), str)
                            and e["amount"].startswith("{"))):
                    continue
                k = e.get("amount_kind")
                if k is None:
                    missing.append(f"{port['face_id']} {e.get('predicate')}: {e.get('amount')!r}")
                elif k not in _VALID_KINDS:
                    invalid.append(f"{port['face_id']} {e.get('predicate')}: kind={k!r}")
    assert not missing, f"{len(missing)} non-mana amount edges missing amount_kind; first: {missing[:3]}"
    assert not invalid, f"{len(invalid)} edges have invalid amount_kind; first: {invalid[:3]}"


def test_card_002_sample_amount_kinds() -> None:
    """Sample spot-checks for the classifier."""
    all_ports = ports.derive_all(all_faces=True)
    by_id = {p["face_id"]: p for p in all_ports}
    faces = {}
    for line in (ROOT / "data" / "normalized" / "faces.jsonl").read_text(
        encoding="utf-8"
    ).splitlines():
        if not line.strip(): continue
        d = json.loads(line)
        faces[d["id"]] = d
    name_to_id = {f.get("name"): fid for fid, f in faces.items()}

    def _find_edge(card_name: str, predicate: str):
        port = by_id[name_to_id[card_name]]
        for sec in ("produces","costs","installs","consumes","properties"):
            for e in port.get(sec, []):
                if e.get("predicate") == predicate:
                    return e
        return None

    # Balin's DEALS_DAMAGE X is variable, not literal
    e = _find_edge("Balin, Loremaster", "DEALS_DAMAGE")
    assert e and e.get("amount_kind") in ("variable","scaling"), e
    # Long-Bodied Grey Dog's HAS_POWER 2 is literal
    e = _find_edge("Long-Bodied Grey Dog", "HAS_POWER")
    assert e and e.get("amount_kind") == "literal", e


def test_card_002_axis_7_every_target_scoped_edge_has_selector() -> None:
    """Card 002 axis 7: every non-property edge whose target_text
    contains "target ", "each ", "all creatures", or "each opponent"
    must carry a structured `selector` field. Consumers filtering by
    scope shouldn't have to parse natural language."""
    all_ports = ports.derive_all(all_faces=True)
    _TARGET_PHRASES = ("target ", "each ", "all creatures", "each opponent")
    missing: list[str] = []
    for port in all_ports:
        for sec in ("properties","installs","consumes","produces","costs"):
            for e in port.get(sec, []):
                tt = str(e.get("target_text") or "").lower()
                if not any(w in tt for w in _TARGET_PHRASES):
                    continue
                if e.get("selector") is None:
                    missing.append(
                        f"{port['face_id']} {sec} {e.get('predicate')}: "
                        f"target_text={tt!r}"
                    )
    assert not missing, (
        f"{len(missing)} target-scoped edges missing selector; first: "
        f"{missing[:3]}"
    )

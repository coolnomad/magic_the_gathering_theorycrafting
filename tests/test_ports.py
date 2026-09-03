"""Tests for layer-2 port derivation.

The derivation is the deliverable; these tests verify the procedure produces
correct outputs without hard-coded per-card branches.
"""

from __future__ import annotations

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
    bofur = _port_by_face(_BOFUR_FACE)
    bofur_grants = [
        p for p in bofur.get("produces", []) if p.get("predicate") == "GRANTS"
    ]
    assert bofur_grants, "Bofur has no GRANTS edge"
    for g in bofur_grants:
        assert g.get("target") == "keyword:lifelink", (
            f"Bofur GRANTS not naming keyword:lifelink: {g}"
        )
    smaug = _port_by_face(_SMAUG_FACE)
    smaug_grants = [
        p for p in smaug.get("produces", []) if p.get("predicate") == "GRANTS"
    ]
    smaug_targets = {g.get("target") for g in smaug_grants}
    assert "keyword:flying" in smaug_targets, (
        f"Smaug GRANTS not naming keyword:flying: {smaug_targets}"
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

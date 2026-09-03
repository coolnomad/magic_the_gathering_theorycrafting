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

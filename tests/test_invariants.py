"""Invariants over the real frozen HOB snapshot (in-memory; no files written)."""

import json

import pytest

from hobkg.mechanics import detect_mechanics
from hobkg.normalize import normalize_card
from hobkg.pipeline import RAW


@pytest.fixture(scope="module")
def normalized():
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    cards, faces = [], []
    for r in raw:
        c, fs = normalize_card(r)
        cards.append(c)
        faces.extend(fs)
    return raw, cards, faces


def test_card_count_and_uniqueness(normalized):
    _, cards, _ = normalized
    assert len(cards) == 193
    assert len({c.id for c in cards}) == 193
    assert len({c.oracle_id for c in cards}) == 193


def test_layout_counts(normalized):
    _, cards, _ = normalized
    from collections import Counter
    layouts = Counter(c.layout for c in cards)
    assert layouts["normal"] == 168
    assert layouts["adventure"] == 17
    assert layouts["saga"] == 8


def test_every_adventure_has_two_faces(normalized):
    _, cards, faces = normalized
    by_id = {}
    for f in faces:
        by_id.setdefault(f.card_id, []).append(f)
    for c in cards:
        if c.layout == "adventure":
            fs = by_id[c.id]
            assert len(fs) == 2
            roles = {f.role for f in fs}
            assert roles == {"primary", "adventure"}


def test_face_count(normalized):
    _, _, faces = normalized
    # 168 normal (1) + 17 adventure (2) + 8 saga (1) = 210
    assert len(faces) == 210


def test_named_mechanic_counts_match_phase0(normalized):
    # Phase 0 verified: 10 Recruit, 9 Storied, 2 hone Oracle texts.
    _, cards, faces = normalized
    by_mech = {}
    for f in faces:
        for d in detect_mechanics(f.id, f.card_id, f.oracle_text):
            by_mech.setdefault(d.mechanic, set()).add(f.card_id)
    assert len(by_mech.get("Recruit", set())) == 10
    assert len(by_mech.get("Storied", set())) == 9
    assert len(by_mech.get("Hone", set())) == 2


def test_blue_source_payment(normalized):
    # A HOB blue-mana producer must pay blue + generic but never a white pip.
    from hobkg.mana import payment_capabilities
    raw, _, _ = normalized
    blue = [r for r in raw if "U" in (r.get("produced_mana") or [])]
    assert blue, "expected at least one blue-mana producer in HOB"
    caps = payment_capabilities(["U"])
    assert "pip:U" in caps["U"] and "pip:W" not in caps["U"]

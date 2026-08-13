from hobkg.types import parse_type_line


def test_legendary_creature():
    p = parse_type_line("Legendary Creature — Dwarf Scout")
    assert p.supertypes == ["Legendary"]
    assert p.types == ["Creature"]
    assert p.subtypes == ["Dwarf", "Scout"]


def test_no_subtypes():
    p = parse_type_line("Instant")
    assert p.types == ["Instant"]
    assert p.subtypes == []


def test_saga():
    p = parse_type_line("Enchantment — Saga")
    assert p.types == ["Enchantment"]
    assert p.subtypes == ["Saga"]


def test_token_prefix_stripped():
    p = parse_type_line("Token Artifact — Treasure")
    assert p.types == ["Artifact"]
    assert p.subtypes == ["Treasure"]


def test_none_passthrough():
    assert parse_type_line(None) is None

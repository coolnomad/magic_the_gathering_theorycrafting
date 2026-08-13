from hobkg.normalize import extract_tokens, normalize_card

NORMAL = {
    "id": "sf-1", "oracle_id": "o-1", "name": "Test Dog", "set": "hob",
    "collector_number": "1", "layout": "normal", "rarity": "common",
    "color_identity": [], "colors": [], "cmc": 3.0, "keywords": ["Reach"],
    "type_line": "Creature — Dog", "mana_cost": "{3}", "oracle_text": "Reach",
    "power": "2", "toughness": "2",
    "all_parts": [
        {"object": "related_card", "id": "tk-1", "component": "token",
         "name": "Treasure", "type_line": "Token Artifact — Treasure"},
        {"object": "related_card", "id": "cp-1", "component": "combo_piece",
         "name": "Test Dog", "type_line": "Creature — Dog"},
    ],
}

ADVENTURE = {
    "id": "sf-2", "oracle_id": "o-2", "name": "Hero // Quest", "set": "hob",
    "collector_number": "2", "layout": "adventure", "rarity": "rare",
    "color_identity": ["W"], "colors": ["W"], "cmc": 1.0, "keywords": ["Lifelink"],
    "type_line": "Legendary Creature — Dwarf Scout // Instant — Adventure",
    "mana_cost": "{W} // {1}{W}",
    "card_faces": [
        {"name": "Hero", "type_line": "Legendary Creature — Dwarf Scout",
         "mana_cost": "{W}", "oracle_text": "Lifelink", "power": "1", "toughness": "1"},
        {"name": "Quest", "type_line": "Instant — Adventure",
         "mana_cost": "{1}{W}", "oracle_text": "Draw a card."},
    ],
}


def test_normal_card_single_primary_face():
    card, faces = normalize_card(NORMAL)
    assert card.id == "card:o-1"
    assert card.face_ids == ["face:o-1:0"]
    assert len(faces) == 1
    assert faces[0].role == "primary"
    assert faces[0].mana_cost.generic == 3


def test_adventure_two_faces_roles():
    card, faces = normalize_card(ADVENTURE)
    assert len(faces) == 2
    assert faces[0].role == "primary"
    assert faces[1].role == "adventure"
    assert faces[0].name != faces[1].name
    assert faces[0].mana_cost_raw != faces[1].mana_cost_raw


def test_tokens_only_from_token_component():
    toks = extract_tokens(NORMAL, "card:o-1")
    assert len(toks) == 1
    assert toks[0].id == "token:treasure"
    assert toks[0].produced_by_card_ids == ["card:o-1"]

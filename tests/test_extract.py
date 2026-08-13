from hobkg.extract_mechanical import extract_face


def _kinds(text):
    ex, un, co = extract_face("face:x:0", "card:x", text)
    return ex, un, co


def test_literal_operative_text_extracts_verbs():
    # Operative (non-reminder) text that literally states the operations.
    text = ("Draw a card, then discard a card. If you discarded a nonland card, "
            "create a 1/1 white Human Soldier creature token.")
    ex, un, co = _kinds(text)
    kinds = {e.kind for e in ex}
    assert {"draw", "discard", "create_token"} <= kinds
    assert next(e for e in ex if e.kind == "draw").quantity == 1
    assert next(e for e in ex if e.kind == "create_token").quantity == 1


def test_reminder_text_is_ignored():
    # The Recruit keyword: operative text is 'recruit'; the mechanics live in the
    # parenthetical reminder, which the syntactic pass must NOT extract (Phase 2
    # templates own that). Only the ETB trigger should be extracted here.
    text = ("When this creature enters, recruit. (Draw a card, then discard a card. "
            "If you discarded a nonland card, create a 1/1 white Human Soldier creature token.)")
    ex, un, co = _kinds(text)
    kinds = {e.kind for e in ex}
    assert "trigger_etb" in kinds
    assert "draw" not in kinds
    assert "discard" not in kinds
    assert "create_token" not in kinds
    # And no false unresolved signals should be raised from reminder text.
    assert un == []


def test_put_counter_type_captured():
    ex, _, _ = _kinds("Put a +1/+1 counter on target creature.")
    pc = next(e for e in ex if e.kind == "put_counter")
    assert pc.detail["counter_type"] == "+1/+1"
    assert pc.quantity == 1


def test_ambiguous_draw_is_unresolved_not_guessed():
    ex, un, _ = _kinds("Draw cards equal to the number of Dwarves you control.")
    assert not any(e.kind == "draw" for e in ex)
    assert any(u.signal == "draw" for u in un)


def test_draw_step_is_not_a_draw_signal():
    # 'after your draw step' must not be treated as a draw action.
    ex, un, _ = _kinds("At the beginning of your draw step, you gain 1 life.")
    assert not any(e.kind == "draw" for e in ex)
    assert not any(u.signal == "draw" for u in un)


def test_etb_trigger_and_qualifier():
    ex, _, _ = _kinds("When this creature enters, another target creature gets +1/+1.")
    etb = next(e for e in ex if e.kind == "trigger_etb")
    assert "another" in etb.qualifiers


def test_activated_ability_requires_real_cost():
    ex, _, _ = _kinds("{T}: Add {G}.")
    assert any(e.kind == "activated_ability" for e in ex)
    assert any(e.kind == "add_mana" for e in ex)


def test_only_once_each_turn_condition():
    _, _, co = _kinds("You may activate this ability only once each turn.")
    assert any(c.kind == "only_once_each_turn" for c in co)

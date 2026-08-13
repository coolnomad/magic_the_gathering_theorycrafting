from hobkg.mana import classify_symbol, parse_mana_cost, payment_capabilities


def test_generic_and_colored():
    mc = parse_mana_cost("{2}{W}")
    assert mc.generic == 2
    assert mc.pips == {"W": 1}
    assert [s.kind for s in mc.symbols] == ["generic", "colored"]


def test_empty_cost_is_none():
    assert parse_mana_cost("") is None
    assert parse_mana_cost(None) is None


def test_hybrid_variants():
    assert classify_symbol("W/U").kind == "hybrid"
    assert classify_symbol("W/U").colors == ["W", "U"]
    assert classify_symbol("2/W").kind == "hybrid_mono"
    assert classify_symbol("U/P").kind == "phyrexian"
    assert classify_symbol("U/P").phyrexian is True
    assert classify_symbol("X").kind == "variable"
    assert classify_symbol("C").kind == "colorless"


def test_payment_never_crosses_colors():
    # Spec invariant #9: blue mana pays blue pips and generic, never white pips.
    caps = payment_capabilities(["U"])
    assert "pip:U" in caps["U"]
    assert "generic" in caps["U"]
    assert "pip:W" not in caps["U"]


def test_colorless_payment():
    caps = payment_capabilities(["C"])
    assert caps["C"] == ["pip:C", "generic"]

"""Review pt1 COMMIT B: set-wide FIN sacrifice evaluation against the FROZEN parser.

The parser was frozen in commit A; this fixture (all 50 FIN faces containing "sacrif", adjudicated
outlet/non-outlet with per-clause structure) is added here and scored ONCE. These asserts pin the
honest, as-measured numbers — including the parser's known false positives (reminder text /
self-sacrifice consequences), the one false negative (subtype fodder 'a Frog'), and the imperfect
clauses — so a later slice that improves them must update this test on purpose.

Primary metric = clause-level exact match; per-field micro accuracy is secondary (inflated by easy
default fields). These are agent-authored reference annotations, NOT an independent human gold set.
"""

from hobkg import sac_schema as sx
from hobkg.pipeline import REPO, _load_dicts

FIX = "tests/fixtures/fin_sacrifice_setwide.jsonl"


def test_setwide_fixture_is_provenanced_and_complete():
    import io
    import json
    src = {c["id"]: c for c in json.load(io.open(REPO / "data/raw/fin/scryfall_fin.json", encoding="utf-8"))}
    cases = _load_dicts(REPO / FIX)
    assert len(cases) == 50                                  # every FIN face containing 'sacrif'
    for rec in cases:
        card = src[rec["id"]]
        if rec["name"] == card.get("name"):
            text = card.get("oracle_text", "")
        else:
            text = next(f["oracle_text"] for f in card["card_faces"] if f["name"] == rec["name"])
        assert rec["oracle_text"] == text                   # byte-identical to source
        assert "sacrif" in text.lower()


def test_setwide_detection_precision_recall():
    sw = sx.run_setwide()
    assert sw["available"] is True and sw["faces"] == 50
    # 27 adjudicated outlets, 23 non-outlets
    assert sw["tp"] == 26 and sw["fn"] == 1 and sw["fp"] == 4 and sw["tn"] == 19
    assert sw["precision"] == 0.8667 and sw["recall"] == 0.963
    # the one missed outlet is subtype fodder the parser cannot see ('Sacrifice a Frog')
    assert sw["fn_faces"] == ["Quina, Qu Gourmet"]
    # false positives are reminder text / self-sacrifice consequences, not real outlets
    assert set(sw["fp_faces"]) == {"Sleep Magic", "Undercity Dire Rat", "Tellah, Great Sage", "Magic Pot"}


def test_setwide_clause_exact_is_primary_metric():
    sw = sx.run_setwide()
    assert sw["clause_exact"] == 25 and sw["clause_total"] == 28   # primary metric
    assert sw["clause_exact_rate"] == 0.8929
    assert sw["field_accuracy"] == 0.9541                          # secondary/diagnostic (inflated)


def test_setwide_known_imperfect_clauses_are_pinned():
    sw = sx.run_setwide()
    # each imperfect face is a genuine, documented parser limit (backlog), not an adjudication slip
    assert set(sw["imperfect"]) == {
        "Sleep Magic",                 # imperative self-sac 'sacrifice this Aura' -> cost_context unsupported
        "Sephiroth, One-Winged Angel", # 'any number of OTHER creatures' -> 'other' not read as another
        "Undercity Dire Rat",          # Treasure reminder text parsed as an outlet
        "Quina, Qu Gourmet",           # subtype 'Frog' fodder not detected
        "Tellah, Great Sage",          # self-sac consequence parsed as an outlet
        "Magic Pot",                   # Treasure reminder text parsed as an outlet
        "Eden, Seat of the Sanctum",   # 'When you do' in an activated ability misread as a trigger
    }


def test_setwide_parser_is_frozen_multiclause_supported():
    # World Map has two distinct activated sacrifice abilities; extract_all returns both, and both
    # score exact -> the multi-clause API (review pt1 #3) works on real set-wide text.
    cases = {c["name"]: c for c in _load_dicts(REPO / FIX)}
    wm = cases["World Map"]
    got = sx.extract_all(wm["oracle_text"], wm["name"])
    assert len(got) == 2
    exp = wm["expected"]["clauses"]
    assert all(sx._clause_exact(exp[i], got[i]) for i in range(2))

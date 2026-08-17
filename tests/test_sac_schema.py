"""Portability tracer bullet #2 (+ review pt1 follow-up): the STRUCTURED sacrifice schema on real FIN.

Answers the pt1 review of commit 8e2d90a:
  * extract_all() returns EVERY clause on a face (not just the first)          — test_extract_all_*
  * each sacrifice cost atom carries its own selector                          — test_selector_on_atom
  * the three known parser errors are fixed, six pt#2 cases kept as regression — test_heldout_regression
  * the scorer is still non-tautological and fixture text is still provenanced — test_scorer_*, test_fixture_*
The set-wide precision/recall + clause-exact-match evaluation is exercised in test_setwide_* (which
tolerates the fixture being absent, so this parser can be committed and frozen BEFORE it is added).
"""

import io
import json

from hobkg import sac_schema as sx
from hobkg.pipeline import REPO, _load_dicts

DEV = "tests/fixtures/fin_sacrifice.jsonl"
HELD = "tests/fixtures/fin_sacrifice_heldout.jsonl"


def _src_text(card, face_name):
    if face_name is None or face_name == card.get("name"):
        return card.get("oracle_text", "")
    for f in card.get("card_faces", []):
        if f.get("name") == face_name:
            return f.get("oracle_text", "")
    return None


def test_parse_is_pure_oracle_text():
    r = sx.parse_structured("{2}, {T}, Sacrifice this creature: Draw a card.", "Whatever")
    assert r["cost_context"] == "activated_ability" and r["actor"] == "you"
    assert r["selector"]["self"] is True and r["ability_context"] == "activated"
    assert sx.parse_structured("Flying", "X") is None
    assert sx.parse_structured("Whenever you sacrifice a creature, draw a card.", "X") is None  # trigger


def test_extract_all_returns_every_clause():
    # a face with two distinct sacrifice outlets yields two records (review pt1 #3)
    two = "{1}, Sacrifice a creature: Draw a card.\nSacrifice an artifact: Add {C}."
    recs = sx.extract_all(two, "X")
    assert len(recs) == 2
    assert {r["selector"]["card_types"][0] for r in recs} == {"creature", "artifact"}
    assert sx.extract_all("Flying", "X") == []


def test_selector_is_attached_to_each_sacrifice_atom():
    # the sacrifice cost atom carries its own selector, not a bare {"sacrifice": True} (review pt1 #2)
    r = sx.parse_structured("{2}, Sacrifice a legendary creature: Draw.", "X")
    atoms = r["cost"]["alt"][0]["all"]
    sac = next(a["sacrifice"] for a in atoms if "sacrifice" in a)
    assert sac["card_types"] == ["creature"] and sac["supertypes"] == ["legendary"]


def test_edict_is_not_an_activated_cost():
    r = sx.parse_structured("Target opponent sacrifices a creature of their choice.", "X")
    assert r["cost_context"] == "resolution_effect" and r["actor"] == "target_opponent" and r["cost"] is None
    r2 = sx.parse_structured("When it enters, each player sacrifices a creature of their choice.", "X")
    assert r2["actor"] == "each_player" and r2["ability_context"] == "triggered_etb"


def test_the_three_known_errors_are_fixed():
    # 1) self "this creature" must NOT leak the type into the selector
    r = sx.parse_structured("{T}, Sacrifice this creature: Deal 2 damage.", "Bomb")
    assert r["selector"]["self"] is True and r["selector"]["card_types"] == []
    # 2) a dual 'enters or attacks' trigger is represented as such
    r2 = sx.parse_structured("Whenever this enters or attacks, you may sacrifice another creature. If you do, draw.", "X")
    assert r2["ability_context"] == "triggered_etb_or_attack"
    # 3) multi-symbol mana {1}{B} is one pay atom, not two
    r3 = sx.parse_structured("{1}{B}, Sacrifice another creature or artifact: Draw.", "X")
    pays = [a["pay"] for a in r3["cost"]["alt"][0]["all"] if "pay" in a]
    assert pays == ["{1}{B}"]


def test_scorer_is_not_tautological():
    expected = {"is_outlet": True, "cost_context": "activated_ability", "actor": "you",
                "sel_card_types": ["artifact"]}
    good = {"is_outlet": True, "cost_context": "activated_ability", "actor": "you",
            "selector": {"card_types": ["artifact"]}}
    bad = {"is_outlet": True, "cost_context": "resolution_effect", "actor": "each_player",
           "selector": {"card_types": ["creature"]}}
    sg = sx.score(expected, good)
    assert sg["fields_ok"] == sg["fields_total"] == 4
    sb = sx.score(expected, bad)
    assert sb["fields"]["cost_context"]["ok"] is False and sb["fields"]["actor"]["ok"] is False
    assert sb["fields"]["sel_card_types"]["ok"] is False and sb["fields"]["is_outlet"]["ok"] is True
    assert sx.score({"is_outlet": False}, None)["fields"]["is_outlet"]["ok"] is True


def test_fixture_oracle_text_is_byte_identical_to_source():
    src = {c["id"]: c for c in json.load(io.open(REPO / "data/raw/fin/scryfall_fin.json", encoding="utf-8"))}
    for fx in (DEV, HELD):
        for rec in _load_dicts(REPO / fx):
            assert rec["id"] in src, rec["id"]
            assert rec["oracle_text"] == _src_text(src[rec["id"]], rec["name"]), rec["name"]


def test_dev_and_heldout_regression_pass():
    # DEV is the tuning set; HELD-OUT is the six pt#2 cases with the three known errors now fixed.
    dev = sx.run_fin(fixture=DEV)
    assert dev["cases"] == 11 and dev["cards_fully_correct"] == 11 and dev["field_accuracy"] == 1.0
    held = sx.run_fin(fixture=HELD)
    assert held["cases"] == 6 and held["cards_fully_correct"] == 6 and held["field_accuracy"] == 1.0


def test_setwide_runner_contract():
    # the set-wide evaluator returns a well-formed result; if the (separately-committed) fixture is
    # present it exposes the primary metrics, otherwise it is explicitly pending.
    sw = sx.run_setwide()
    if sw.get("available"):
        for k in ("precision", "recall", "clause_precision", "clause_recall", "clause_f1",
                  "clause_predicted", "faces_exact", "field_accuracy"):
            assert k in sw
        assert 0.0 <= sw["clause_precision"] <= 1.0 and 0.0 <= sw["clause_f1"] <= 1.0
    else:
        assert sw == {"available": False}


def test_subtype_is_represented_but_quina_stays_pinned():
    # subtypes are a scored field now; the parser captures them WHEN a card type is also present…
    assert "sel_subtypes" in sx.SCORED_FIELDS
    r = sx.parse_structured("Sacrifice a Goblin creature: Draw.", "X")
    assert r["selector"]["subtypes"] == ["goblin"]
    # …but bare subtype fodder ("a Frog") is still not DETECTED — Quina remains the frozen miss.
    assert sx.parse_structured("{2}, Sacrifice a Frog: Draw.", "Quina") is None
    # a "non-God" qualifier does not leak "God" as a subtype
    assert sx.parse_structured("Each player sacrifices a non-God creature.", "X")["selector"]["subtypes"] == []


def test_report_written():
    out = sx.report()
    assert out["dev"]["field_accuracy"] == 1.0 and out["heldout"]["field_accuracy"] == 1.0
    assert (REPO / "reports/sac_schema_portability.md").exists()

"""Portability tracer bullet #2: the STRUCTURED sacrifice schema, validated on real FIN Oracle text.

These tests answer the review of tracer bullet #1 (commit c67fcc5):
  * the scorer is NON-tautological — it compares to adjudicated structured output field-by-field, so
    a deliberately-wrong record fails (test_scorer_is_not_tautological);
  * the fixture text is REAL and provenanced — byte-identical to data/raw/fin/scryfall_fin.json
    (test_fixture_oracle_text_is_byte_identical_to_source);
  * DEV is train-set accuracy; HELD-OUT is the honest portability number, and its known limits are
    pinned so they cannot be silently "adjudicated away" (test_heldout_*).
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
    # an activated self-sacrifice cost, parsed with no per-card branch
    r = sx.parse_structured("{2}, {T}, Sacrifice this creature: Draw a card.", "Whatever")
    assert r["cost_context"] == "activated_ability" and r["actor"] == "you"
    assert r["selector"]["self"] is True and r["ability_context"] == "activated"
    assert sx.parse_structured("Flying", "X") is None                 # no sacrifice clause
    assert sx.parse_structured("Whenever you sacrifice a creature, draw a card.", "X") is None  # trigger, not outlet


def test_edict_is_not_an_activated_cost():
    # the exact tracer-bullet-#1 bug: an edict must NOT default to a cost context
    r = sx.parse_structured("Target opponent sacrifices a creature of their choice.", "X")
    assert r["cost_context"] == "resolution_effect"     # not 'activated_cost'
    assert r["actor"] == "target_opponent" and r["cost"] is None
    r2 = sx.parse_structured("When it enters, each player sacrifices a creature of their choice.", "X")
    assert r2["actor"] == "each_player" and r2["ability_context"] == "triggered_etb"


def test_selector_or_vs_supertype_and_cost_alt():
    # selector-internal OR ("artifact or creature") is distinct from cost-level ALT ("or pay")
    r = sx.parse_structured("{3}, Sacrifice another creature or artifact: Draw a card.", "X")
    assert r["selector"]["card_types"] == ["artifact", "creature"] and r["selector"]["or_types"] is True
    assert r["selector"]["another"] is True
    # additional cast cost with a real ALT of branches: sacrifice(...) OR pay {2}
    r2 = sx.parse_structured("As an additional cost to cast this spell, sacrifice a legendary creature or pay {2}.", "X")
    assert r2["cost_context"] == "additional_cast_cost" and r2["selector"]["supertypes"] == ["legendary"]
    branches = sx._canon_cost(r2["cost"])
    assert any("pay={2}" in b for b in branches) and any("sacrifice=True" in b for b in branches)
    assert len(branches) == 2                             # two ALT branches (sacrifice | pay)


def test_scorer_is_not_tautological():
    # a CORRECT record scores full; a WRONG record fails exactly the wrong fields
    expected = {"is_outlet": True, "cost_context": "activated_ability", "actor": "you",
                "sel_card_types": ["artifact"]}
    good = {"is_outlet": True, "cost_context": "activated_ability", "actor": "you",
            "selector": {"card_types": ["artifact"]}}
    bad = {"is_outlet": True, "cost_context": "resolution_effect", "actor": "each_player",
           "selector": {"card_types": ["creature"]}}
    sg = sx.score(expected, good)
    assert sg["fields_ok"] == sg["fields_total"] == 4
    sb = sx.score(expected, bad)
    assert sb["fields"]["cost_context"]["ok"] is False
    assert sb["fields"]["actor"]["ok"] is False
    assert sb["fields"]["sel_card_types"]["ok"] is False
    assert sb["fields"]["is_outlet"]["ok"] is True        # this one still matches
    # a None parse (missed outlet) fails every value field, but matches is_outlet:False
    sn = sx.score({"is_outlet": False}, None)
    assert sn["fields"]["is_outlet"]["ok"] is True


def test_fixture_oracle_text_is_byte_identical_to_source():
    # provenance integrity: the fixtures copy real Scryfall text, never hand-typed
    src = {c["id"]: c for c in json.load(io.open(REPO / "data/raw/fin/scryfall_fin.json", encoding="utf-8"))}
    for fx in (DEV, HELD):
        for rec in _load_dicts(REPO / fx):
            assert rec["id"] in src, rec["id"]
            assert rec["oracle_text"] == _src_text(src[rec["id"]], rec["name"]), rec["name"]


def test_dev_split_is_fully_representable():
    # the schema can represent every dev clause (train-set: parser was tuned to these)
    dev = sx.run_fin(fixture=DEV)
    assert dev["cases"] == 11
    assert dev["cards_fully_correct"] == 11 and dev["field_accuracy"] == 1.0


def test_heldout_is_honest_portability_evidence():
    # parser is FROZEN vs these; the score is < 1.0 and the known limits fail (pinned so they
    # cannot be silently adjudicated away). If a future slice fixes one, update this test on purpose.
    held = sx.run_fin(fixture=HELD)
    assert held["cases"] == 6
    assert held["field_accuracy"] < 1.0                   # honest: not a reproduction demo
    by = {r["name"]: r["score"]["fields"] for r in held["results"]}
    # dual 'enters or attacks' trigger is not modelled yet
    assert by["Sephiroth, Fabled SOLDIER"]["ability_context"]["ok"] is False
    # multi-symbol mana {1}{B} is not coalesced yet
    assert by["Yiazmat, Ultimate Mark"]["cost"]["ok"] is False
    # self-by-"this creature" still leaks the type into the selector
    assert by["Blazing Bomb"]["sel_card_types"]["ok"] is False
    # but the Saga-chapter edicts (actor + quantity 2) ARE handled
    assert all(v["ok"] for v in by["Braska's Final Aeon"].values())


def test_report_written():
    out = sx.report()
    assert out["dev"]["field_accuracy"] == 1.0
    assert 0.0 < out["heldout"]["field_accuracy"] < 1.0
    assert (REPO / "reports/sac_schema_portability.md").exists()

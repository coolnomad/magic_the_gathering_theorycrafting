"""Portability tracer bullet: the deterministic sacrifice-clause extractor must reproduce the nine
accepted HOB records with NO card-specific hardcoding, and expose HOB assumptions on an adversarial
second-set fixture."""

from hobkg import sac_extract as sx
from hobkg.completeness import SAC_OUTLETS
from hobkg.pipeline import REPO, _load_dicts

_CORE = ("accepts", "another", "or_pay", "kind", "mana_cost")


def test_extract_is_pure_oracle_text():
    # the parser takes ONLY oracle text — no face id, no repo, no per-card branch
    r = sx.extract("{1}, Sacrifice another creature: Draw a card.")
    assert r["accepts"] == ["creature"] and r["another"] is True
    assert r["kind"] == "activated_cost" and r["mana_cost"] == "{1}"
    assert sx.extract("Flying") is None                     # no sacrifice clause


def test_reproduces_the_nine_hob_records_without_hardcoding():
    # every accepted HOB outlet is reproduced on the core fields; nothing spurious; no face-id logic
    r = sx.build_from_hob()
    assert r["expected"] == 9 and r["extracted"] == 9
    assert r["reproduced"] == 9 and r["reproduces_catalogue"] is True
    assert r["mismatches"] == [] and r["spurious"] == []
    # spot-check the parser output equals the hand-authored spec per outlet
    for fid, spec in SAC_OUTLETS.items():
        got = r["_extracted"][fid]
        assert all(got[k] == spec[k] for k in _CORE), (spec["name"], {k: (spec[k], got[k]) for k in _CORE})
    # the extractor source contains no HOB face-id / card-name hardcoding
    src = (REPO / "src/hobkg/sac_extract.py").read_text(encoding="utf-8")
    assert "SAC_OUTLETS" not in sx.extract.__code__.co_names   # extract() never consults the catalogue
    import re as _re
    assert not _re.search(r"[0-9a-f]{8}-[0-9a-f]{4}", sx.extract.__doc__ or "")


def test_span_improves_on_the_hand_authored_null():
    # the hand-authored catalogue had oracle_span: null; the extractor computes an exact span
    faces = {f["id"]: f for f in _load_dicts(REPO / "data/normalized/faces.jsonl")}
    for fid in SAC_OUTLETS:
        rec = sx.extract(faces[fid].get("oracle_text") or "")
        s, e = rec["oracle_span"]
        assert (faces[fid]["oracle_text"])[s:e] == rec["clause"]   # span is exact


def test_adversarial_fixture_exposes_hob_assumptions():
    adv = sx.run_adversarial()
    assert adv["cases"] >= 10
    # every fixture case genuinely defeats the HOB-tuned parser (a MISS or an INCOMPLETE record)
    for f in adv["findings"]:
        assert f["status"].startswith("MISS") or f["status"].startswith("INCOMPLETE")
    exposed = set(adv["assumptions_exposed"])
    # the key portability gaps must be surfaced
    for a in ("type_enum_only", "no_subtypes", "quantity_one", "no_self_sacrifice",
              "or_pay_mana_only", "or_not_and", "no_qualifiers", "controller_scope",
              "no_timing_restrictions", "quantity_variable"):
        assert a in exposed
    # every exposed assumption has a human-readable label in the report table
    for a in exposed:
        assert a in sx._ASSUMPTION_LABEL


def test_specific_adversarial_behaviours():
    # a non-mana OR alternative is dropped (or_pay stays None)
    assert sx.extract("As an additional cost to cast this spell, sacrifice a creature or discard a card.")["or_pay"] is None
    # 'two creatures' / 'this creature' / 'a Goblin' / 'a permanent' are all missed
    for o in ("Sacrifice two creatures: Draw two cards.",
              "Sacrifice this creature: Add one mana of any color.",
              "Sacrifice a Goblin: Deal 2 damage.",
              "Sacrifice a permanent: Add {C}."):
        assert sx.extract(o) is None


def test_report_written(tmp_path=None):
    s = sx.report()
    assert s["reproduces_catalogue"] is True and s["hob_reproduced"] == 9
    assert (REPO / "reports/sac_extract_portability.md").exists()
